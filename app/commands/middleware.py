"""Единый middleware: активность, антиспам, разбор команд, сессия БД."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from app.commands.context import CommandContext
from app.commands.executor import execute_command
from app.commands.parser import ParseConfig, parse_command
from app.core.logging import get_logger
from app.database.models import AuditLog, ChatSettings, User
from app.services.moderation import ModerationError

log = get_logger(__name__)

MAX_TEXT_FOR_AI = 1200


class IrisMiddleware(BaseMiddleware):
    """Обрабатывает каждое текстовое сообщение до роутеров.

    1. Регистрирует пользователя, группу и участника (реестр участников).
    2. Считает статистику и опыт.
    3. Проверяет антиспам/антифлуд; при срабатывании наказывает и останавливает поток.
    4. Разбирает команду и кладёт ``command_ctx`` в data.
    """

    def __init__(self, container) -> None:
        self.container = container

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or event.from_user is None:
            return await handler(event, data)
        if event.chat.type not in {"group", "supergroup", "private"}:
            return await handler(event, data)

        container = self.container
        session: AsyncSession = container.db.session()
        data["session"] = session
        data["container"] = container
        try:
            is_group = event.chat.type in {"group", "supergroup"}
            members = container.members(session)
            user = await members.ensure_user(
                user_id=event.from_user.id,
                username=event.from_user.username,
                first_name=event.from_user.first_name,
                last_name=event.from_user.last_name,
                language_code=event.from_user.language_code,
                is_bot=event.from_user.is_bot,
            )
            chat_row, settings = await container.chats.ensure(
                session,
                chat_id=event.chat.id,
                title=event.chat.title,
                chat_type=event.chat.type,
                username=event.chat.username,
            )

            is_admin = False
            if is_group:
                is_admin = await container.permissions(session).is_chat_admin(
                    event.chat.id, event.from_user.id
                )
                await self._touch_member(session, event, settings, is_admin)
                await self._track_join_leave(session, event)

            text = event.text or event.caption
            parsed = None
            spec = None
            if text:
                prefixes = list(settings.command_prefixes or [])
                triggers = list(settings.command_triggers or [])
                parsed = parse_command(
                    text,
                    known=container.commands.known_names(),
                    config=ParseConfig(
                        prefixes=prefixes,
                        triggers=triggers,
                        bot_username=container.settings.bot_username,
                        max_bare_length=container.settings.max_bare_length,
                        default_command="меню",
                    ),
                    allow_bare=bool(settings.bare_commands),
                )
                if parsed is not None:
                    spec = container.commands.get(parsed.name)
                    if parsed.trigger == "bare" and spec is not None and not spec.allow_bare:
                        parsed, spec = None, None

            if settings.antispam_enabled or settings.antiflood_enabled:
                verdict = await container.antispam(session).check(
                    event,
                    settings,
                    is_admin=is_admin,
                    is_new_member=await container.antispam(session).is_new_member(
                        event.chat.id, event.from_user.id
                    ),
                    # Содержимое команд не считаем спамом (иначе повторная
                    # команда «бонус» улетала бы в дубликаты), но флуд считаем.
                    is_command=parsed is not None,
                )
                if verdict is not None:
                    await self._punish(session, event, settings, verdict, is_admin)
                    await session.commit()
                    return None

            if parsed is not None and spec is not None:
                ctx = CommandContext(
                    message=event,
                    spec=spec,
                    parsed=parsed,
                    session=session,
                    container=container,
                    user=user,
                    chat_row=chat_row,
                    settings=settings,
                    locale=container.locale(settings),
                )
                data["command_ctx"] = ctx
                data["command_name"] = spec.name
                data["chat_settings"] = settings
                data["db_user"] = user

                await container.analytics(session).bump(event.chat.id, commands=1)
                session.add(
                    AuditLog(
                        chat_id=event.chat.id,
                        actor_id=event.from_user.id,
                        action="command",
                        payload={"command": spec.name},
                    )
                )
                await self._store_ai_context(session, event, settings, user)
                await execute_command(ctx)
                await session.commit()
                return None
            else:
                data["chat_settings"] = settings
                data["db_user"] = user
                await self._award_activity(session, event, settings, user, is_admin)
                await self._run_automation(session, event, settings, user, is_admin)
                await self._store_ai_context(session, event, settings, user)

            if is_group:
                await container.analytics(session).bump(event.chat.id, messages=1)

            result = await handler(event, data)
            await session.commit()
            return result
        finally:
            await session.close()

    # --- Внутренние шаги --------------------------------------------------
    async def _touch_member(
        self,
        session: AsyncSession,
        event: Message,
        settings: ChatSettings,
        is_admin: bool,
    ) -> None:
        if event.from_user is None:
            return
        status = "administrator" if is_admin else "member"
        await self.container.members(session).touch(
            chat_id=event.chat.id,
            user_id=event.from_user.id,
            username=event.from_user.username,
            full_name=event.from_user.full_name,
            is_bot=event.from_user.is_bot,
            status=status,
            message_increment=True,
            verified=not settings.captcha_enabled,
        )
        if not event.from_user.is_bot:
            await self.container.quests(session).bump(event.chat.id, event.from_user.id, "messages")

    async def _track_join_leave(self, session: AsyncSession, event: Message) -> None:
        if event.new_chat_members:
            for member in event.new_chat_members:
                if member.is_bot:
                    continue
                await self.container.members(session).touch(
                    chat_id=event.chat.id,
                    user_id=member.id,
                    username=member.username,
                    full_name=member.full_name,
                    status="member",
                    verified=False,
                )
                await self.container.analytics(session).bump(event.chat.id, joins=1)
        if event.left_chat_member and not event.left_chat_member.is_bot:
            await self.container.members(session).mark_left(
                event.chat.id, event.left_chat_member.id
            )
            await self.container.analytics(session).bump(event.chat.id, leaves=1)

    async def _award_activity(
        self,
        session: AsyncSession,
        event: Message,
        settings: ChatSettings,
        user: User,
        is_admin: bool,
    ) -> None:
        if not settings.levels_enabled or user.is_bot:
            return
        key = f"xp:{event.chat.id}:{user.id}"
        if await self.container.cache.get(key):
            return
        await self.container.cache.set(key, "1", ttl=60)

        levels = self.container.levels(session)
        result = await levels.award(event.chat.id, user.id)
        await self.container.quests(session).bump(event.chat.id, user.id, "xp", 5)
        await self.container.profiles(session).touch(user.id, messages=1)
        name = f'<a href="tg://user?id={user.id}">{user.display_name}</a>'

        if result.leveled_up:
            try:
                await event.answer(
                    self.container.texts.t(
                        settings.locale, "level_up", name=name, level=result.level
                    ),
                    parse_mode="HTML",
                )
            except Exception:  # noqa: BLE001
                pass

    async def _run_automation(
        self,
        session: AsyncSession,
        event: Message,
        settings: ChatSettings,
        user: User,
        is_admin: bool,
    ) -> None:
        if not settings.automation_enabled or is_admin or user.is_bot:
            return
        is_new = await self.container.antispam(session).is_new_member(event.chat.id, user.id)
        try:
            await self.container.automation(session).process(
                event, settings, user_name=user.display_name, is_new_member=is_new
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("Автоматизация упала", extra={"error": str(exc)})

    async def _store_ai_context(
        self,
        session: AsyncSession,
        event: Message,
        settings: ChatSettings,
        user: User,
    ) -> None:
        if not (settings.ai_enabled and settings.ai_history_enabled):
            return
        text = (event.text or event.caption or "").strip()
        if not text or len(text) > MAX_TEXT_FOR_AI:
            return
        await self.container.ai(session).store_chat_context(
            event.chat.id, user.id, user.display_name, text
        )

    async def _punish(
        self,
        session: AsyncSession,
        event: Message,
        settings: ChatSettings,
        verdict,
        is_admin: bool,
    ) -> None:
        if is_admin:
            return
        moderation = self.container.moderation(session, settings)
        locale = settings.locale
        try:
            await event.delete()
        except Exception:  # noqa: BLE001
            pass

        reason = {
            "flood": "антифлуд",
            "duplicate": "повтор сообщения",
            "mentions": "спам упоминаниями",
            "caps": "капс",
            "phishing": "фишинг",
            "link": "ссылки запрещены",
            "newbie_link": "ссылка от новичка",
            "stop_word": "запрещённое слово",
        }.get(verdict.reason, verdict.reason)

        try:
            if verdict.action == "mute":
                await moderation.mute(
                    event.chat.id,
                    event.from_user.id,
                    moderator_id=None,
                    seconds=max(60, verdict.mute_minutes * 60),
                    reason=reason,
                )
            elif verdict.action == "warn":
                await moderation.warn(
                    event.chat.id,
                    event.from_user.id,
                    moderator_id=None,
                    reason=reason,
                    limit=settings.max_warnings,
                    auto_action=settings.warn_action,
                    mute_minutes=settings.mute_minutes,
                )
            elif verdict.action == "ban":
                await moderation.ban(
                    event.chat.id, event.from_user.id, moderator_id=None, reason=reason
                )
        except ModerationError:
            log.warning("Не удалось применить наказание", extra={"verdict": verdict.reason})
        except Exception as exc:  # noqa: BLE001
            log.exception("Ошибка наказания", extra={"error": str(exc)})

        if verdict.action in {"mute", "ban"}:
            try:
                name = event.from_user.full_name
                text = (
                    f"🚫 {name}: {reason}. Действие: {verdict.action}."
                    if locale == "ru"
                    else f"🚫 {name}: {reason}. Action: {verdict.action}."
                )
                await event.answer(text, parse_mode=None)
            except Exception:  # noqa: BLE001
                pass
