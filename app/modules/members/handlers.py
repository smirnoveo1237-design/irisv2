"""Реестр участников: события статусов и команда «участники»."""

from __future__ import annotations

from aiogram import Router
from aiogram.types import ChatMemberUpdated

from app.commands.context import CommandContext
from app.commands.registry import command
from app.container import Container
from app.core.logging import get_logger
from app.core.texts import texts
from app.ui.keyboards import main_menu

router = Router(name="iris.members")
log = get_logger(__name__)

LEFT_STATUSES = {"left", "kicked"}


@router.my_chat_member()
async def on_my_chat_member(event: ChatMemberUpdated, container: Container | None = None) -> None:
    """Бота добавили в чат или удалили: регистрируем чат и подтягиваем админов."""
    if container is None:
        return
    bot_id = container.bot.id if container.bot else 0
    if bot_id and event.new_chat_member.user.id != bot_id:
        return

    async with container.db.session_scope() as session:
        chat, settings = await container.chats.ensure(
            session,
            chat_id=event.chat.id,
            title=event.chat.title,
            chat_type=event.chat.type,
            username=event.chat.username,
        )
        if event.new_chat_member.status in LEFT_STATUSES:
            chat.is_active = False
            return
        chat.is_active = True
        added = await container.members(session).sync_admins(container.bot, event.chat.id)
        log.info(
            "Бот добавлен в чат",
            extra={"chat_id": event.chat.id, "admins_added": added},
        )

    if container.bot is not None:
        try:
            await container.bot.send_message(
                event.chat.id,
                texts.t(settings.locale, "menu_title"),
                reply_markup=main_menu(settings.locale),
            )
        except Exception as exc:  # noqa: BLE001 - бот мог быть добавлен без прав писать
            log.warning("Не удалось отправить приветствие", extra={"error": str(exc)})


@router.chat_member()
async def on_chat_member(event: ChatMemberUpdated, container: Container | None = None) -> None:
    """Любое изменение статуса участника: вход, выход, бан, повышение."""
    if container is None:
        return
    user = event.new_chat_member.user
    if user.is_bot:
        return

    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status

    async with container.db.session_scope() as session:
        await container.chats.ensure(
            session,
            chat_id=event.chat.id,
            title=event.chat.title,
            chat_type=event.chat.type,
            username=event.chat.username,
        )
        members = container.members(session)
        await members.ensure_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            language_code=user.language_code,
            is_bot=False,
        )

        if new_status in LEFT_STATUSES:
            await members.mark_left(
                event.chat.id, user.id, kicked=new_status == "kicked"
            )
        else:
            status = "creator" if new_status == "creator" else (
                "administrator" if new_status == "administrator" else "member"
            )
            await members.touch(
                chat_id=event.chat.id,
                user_id=user.id,
                username=user.username,
                full_name=user.full_name,
                status=status,
                verified=True,
            )
            if old_status in LEFT_STATUSES:
                await container.analytics(session).bump(event.chat.id, joins=1)
        if old_status not in LEFT_STATUSES and new_status in LEFT_STATUSES:
            await container.analytics(session).bump(event.chat.id, leaves=1)


@command(
    "участники",
    aliases=("реестр", "members"),
    module="members",
    category="general",
    description_ru="Кто известен реестру и синхронизация администраторов",
    description_en="Registry stats and admin sync",
    usage="участники",
    permission="moderation",
    group_only=True,
    cooldown=3,
)
async def members_command(ctx: CommandContext) -> None:
    sub = (ctx.arg(0) or "").casefold()
    if sub in {"синхро", "sync", "обновить"}:
        added = await ctx.members.sync_admins(ctx.container.bot, ctx.chat_id)
        await ctx.reply(
            f"🔄 Синхронизация администраторов: добавлено <b>{added}</b>.\n"
            "Остальных участников Telegram не отдаёт — они появятся, когда напишут "
            "или изменят статус."
        )
        return

    stats = await ctx.members.stats(ctx.chat_id)
    text = (
        "👥 <b>Реестр участников</b>\n\n"
        f"Известно всего: <b>{stats['total']}</b>\n"
        f"Активных: <b>{stats['active']}</b>\n"
        f"Администраторов: <b>{stats['admins']}</b>\n"
        f"Подтверждённых: <b>{stats['verified']}</b>\n\n"
        "<i>Telegram Bot API не отдаёт полный список участников. Реестр пополняется "
        "сообщениями, входами/выходами и изменениями статусов. Администраторов можно "
        "подтянуть командой</i> <code>участники синхро</code>."
    )
    await ctx.reply(text)


__all__ = ["router", "on_my_chat_member", "on_chat_member", "members_command"]
