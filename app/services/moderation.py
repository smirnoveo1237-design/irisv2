"""Модерация: баны, муты, предупреждения, удаление, журналирование."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from aiogram.exceptions import TelegramAPIError
from aiogram.types import ChatPermissions
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.timeutil import human_duration, now_utc
from app.database.models import Ban, ChatSettings, ChatStat, ModerationLog, Warning

if TYPE_CHECKING:
    from app.container import Container

log = get_logger(__name__)

FULL_PERMISSIONS = ChatPermissions(
    can_send_messages=True,
    can_send_audios=True,
    can_send_documents=True,
    can_send_photos=True,
    can_send_videos=True,
    can_send_video_notes=True,
    can_send_voice_notes=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
    can_change_info=False,
    can_invite_users=True,
    can_pin_messages=False,
)

MUTED_PERMISSIONS = ChatPermissions(can_send_messages=False)


class ModerationError(Exception):
    """Ошибка модерации с человекочитаемой причиной."""


@dataclass(slots=True)
class WarnResult:
    count: int
    limit: int
    auto_action: str | None = None


class ModerationService:
    def __init__(self, container: Container, session: AsyncSession, settings: ChatSettings | None) -> None:
        self.container = container
        self.session = session
        self.settings = settings

    @property
    def bot(self):
        return self.container.bot

    @property
    def locale(self) -> str:
        return self.settings.locale if self.settings else self.container.settings.default_locale

    # --- Telegram ---------------------------------------------------------
    async def ensure_right(self, chat_id: int, right: str) -> None:
        allowed = await self.container.permissions(self.session).bot_can(chat_id, right)
        if not allowed:
            raise ModerationError("no_bot_rights")

    async def send_log(self, chat_id: int, text: str) -> None:
        if not self.bot or not self.settings or not self.settings.log_channel_id:
            return
        try:
            await self.bot.send_message(self.settings.log_channel_id, text, parse_mode="HTML")
        except TelegramAPIError:
            log.warning("Не удалось отправить сообщение в лог-канал", extra={"chat_id": chat_id})

    async def _log_action(
        self,
        chat_id: int,
        action: str,
        *,
        user_id: int | None,
        moderator_id: int | None,
        reason: str | None,
        duration: int | None = None,
        meta: dict | None = None,
    ) -> None:
        self.session.add(
            ModerationLog(
                chat_id=chat_id,
                user_id=user_id,
                moderator_id=moderator_id,
                action=action,
                reason=reason,
                duration=duration,
                meta=meta,
            )
        )
        # суточный счётчик наказаний
        from app.database.utils import upsert as db_upsert

        today = now_utc().date()
        await db_upsert(
            self.session,
            ChatStat,
            {"chat_id": chat_id, "day": today, "moderated": 1},
            index_elements=["chat_id", "day"],
            update_values={"moderated": ChatStat.moderated + 1},
        )
        await self.session.flush()

    # --- Бан --------------------------------------------------------------
    async def ban(
        self,
        chat_id: int,
        user_id: int,
        *,
        moderator_id: int | None,
        reason: str | None = None,
        seconds: int | None = None,
    ) -> datetime | None:
        await self.ensure_right(chat_id, "can_restrict_members")
        until = now_utc() + timedelta(seconds=seconds) if seconds else None
        try:
            await self.bot.ban_chat_member(chat_id, user_id, until_date=until)
        except TelegramAPIError as exc:
            raise ModerationError("telegram_api") from exc

        existing = await self.session.scalar(
            select(Ban).where(Ban.chat_id == chat_id, Ban.user_id == user_id)
        )
        if existing is None:
            self.session.add(
                Ban(
                    chat_id=chat_id,
                    user_id=user_id,
                    moderator_id=moderator_id or 0,
                    reason=reason,
                    until=until,
                )
            )
        else:
            existing.is_active = True
            existing.until = until
            existing.reason = reason
            existing.moderator_id = moderator_id or 0
        await self._log_action(
            chat_id,
            "ban",
            user_id=user_id,
            moderator_id=moderator_id,
            reason=reason,
            duration=seconds,
        )
        await self.container.members(self.session).mark_left(chat_id, user_id, kicked=True)
        return until

    async def unban(self, chat_id: int, user_id: int, *, moderator_id: int | None, reason: str | None = None) -> None:
        await self.ensure_right(chat_id, "can_restrict_members")
        try:
            await self.bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
        except TelegramAPIError as exc:
            raise ModerationError("telegram_api") from exc
        await self._close_ban(chat_id, user_id)
        await self._log_action(
            chat_id, "unban", user_id=user_id, moderator_id=moderator_id, reason=reason
        )

    async def _close_ban(self, chat_id: int, user_id: int) -> None:
        await self.session.execute(
            update(Ban)
            .where(Ban.chat_id == chat_id, Ban.user_id == user_id, Ban.is_active.is_(True))
            .values(is_active=False)
        )

    # --- Мут --------------------------------------------------------------
    async def mute(
        self,
        chat_id: int,
        user_id: int,
        *,
        moderator_id: int | None,
        seconds: int,
        reason: str | None = None,
    ) -> datetime | None:
        await self.ensure_right(chat_id, "can_restrict_members")
        until = now_utc() + timedelta(seconds=seconds) if seconds else None
        try:
            await self.bot.restrict_chat_member(
                chat_id, user_id, permissions=MUTED_PERMISSIONS, until_date=until
            )
        except TelegramAPIError as exc:
            raise ModerationError("telegram_api") from exc
        await self._log_action(
            chat_id,
            "mute",
            user_id=user_id,
            moderator_id=moderator_id,
            reason=reason,
            duration=seconds,
        )
        return until

    async def unmute(
        self, chat_id: int, user_id: int, *, moderator_id: int | None, reason: str | None = None
    ) -> None:
        await self.ensure_right(chat_id, "can_restrict_members")
        try:
            await self.bot.restrict_chat_member(
                chat_id, user_id, permissions=FULL_PERMISSIONS
            )
        except TelegramAPIError as exc:
            raise ModerationError("telegram_api") from exc
        await self._log_action(
            chat_id, "unmute", user_id=user_id, moderator_id=moderator_id, reason=reason
        )

    async def kick(self, chat_id: int, user_id: int, *, moderator_id: int | None, reason: str | None = None) -> None:
        await self.ensure_right(chat_id, "can_restrict_members")
        try:
            await self.bot.ban_chat_member(chat_id, user_id)
            await self.bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
        except TelegramAPIError as exc:
            raise ModerationError("telegram_api") from exc
        await self._log_action(
            chat_id, "kick", user_id=user_id, moderator_id=moderator_id, reason=reason
        )
        await self.container.members(self.session).mark_left(chat_id, user_id, kicked=True)

    # --- Предупреждения ---------------------------------------------------
    async def warn(
        self,
        chat_id: int,
        user_id: int,
        *,
        moderator_id: int | None,
        reason: str | None,
        limit: int,
        auto_action: str = "mute",
        mute_minutes: int = 60,
    ) -> WarnResult:
        await self._expire_warnings(chat_id, user_id)
        self.session.add(
            Warning(
                chat_id=chat_id,
                user_id=user_id,
                moderator_id=moderator_id or 0,
                reason=reason,
                expires_at=now_utc() + timedelta(days=7),
            )
        )
        await self.session.flush()
        count = await self.active_warning_count(chat_id, user_id)
        await self._log_action(
            chat_id, "warn", user_id=user_id, moderator_id=moderator_id, reason=reason
        )

        auto: str | None = None
        if limit and count >= limit:
            auto = auto_action
            if auto_action == "ban":
                await self.ban(
                    chat_id,
                    user_id,
                    moderator_id=moderator_id,
                    reason="Лимит предупреждений",
                )
            elif auto_action == "kick":
                await self.kick(
                    chat_id, user_id, moderator_id=moderator_id, reason="Лимит предупреждений"
                )
            else:
                await self.mute(
                    chat_id,
                    user_id,
                    moderator_id=moderator_id,
                    seconds=max(60, mute_minutes * 60),
                    reason="Лимит предупреждений",
                )
            await self.clear_warnings(chat_id, user_id)
            count = 0
        return WarnResult(count=count, limit=limit, auto_action=auto)

    async def _expire_warnings(self, chat_id: int, user_id: int) -> None:
        await self.session.execute(
            update(Warning)
            .where(
                Warning.chat_id == chat_id,
                Warning.user_id == user_id,
                Warning.is_active.is_(True),
                Warning.expires_at.is_not(None),
                Warning.expires_at < now_utc(),
            )
            .values(is_active=False)
        )

    async def active_warning_count(self, chat_id: int, user_id: int) -> int:
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(Warning)
                .where(
                    Warning.chat_id == chat_id,
                    Warning.user_id == user_id,
                    Warning.is_active.is_(True),
                )
            )
            or 0
        )

    async def list_warnings(self, chat_id: int, user_id: int) -> list[Warning]:
        rows = await self.session.scalars(
            select(Warning)
            .where(
                Warning.chat_id == chat_id,
                Warning.user_id == user_id,
                Warning.is_active.is_(True),
            )
            .order_by(Warning.created_at.desc())
        )
        return list(rows)

    async def clear_warnings(self, chat_id: int, user_id: int) -> int:
        result = await self.session.execute(
            update(Warning)
            .where(
                Warning.chat_id == chat_id,
                Warning.user_id == user_id,
                Warning.is_active.is_(True),
            )
            .values(is_active=False)
        )
        return int(result.rowcount or 0)

    # --- Удаление и история ----------------------------------------------
    async def delete_range(self, chat_id: int, message_ids: list[int]) -> int:
        deleted = 0
        for message_id in message_ids:
            try:
                await self.bot.delete_message(chat_id, message_id)
                deleted += 1
            except TelegramAPIError:
                continue
        return deleted

    async def history(self, chat_id: int, user_id: int, limit: int = 10) -> list[ModerationLog]:
        rows = await self.session.scalars(
            select(ModerationLog)
            .where(ModerationLog.chat_id == chat_id, ModerationLog.user_id == user_id)
            .order_by(ModerationLog.created_at.desc())
            .limit(limit)
        )
        return list(rows)

    def duration_label(self, seconds: int | None) -> str:
        return human_duration(seconds or 0, self.locale)
