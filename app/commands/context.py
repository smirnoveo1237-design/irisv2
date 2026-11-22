"""Контекст выполнения команды: всё, что нужно обработчику."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from aiogram.types import InlineKeyboardMarkup, Message, ReplyKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.commands.parser import ParsedCommand
from app.commands.registry import CommandSpec
from app.core.logging import get_logger
from app.database.models import Chat, ChatSettings, User

if TYPE_CHECKING:
    from app.container import Container

log = get_logger(__name__)


@dataclass(slots=True)
class Target:
    """Цель административного действия."""

    user_id: int
    username: str | None = None
    full_name: str | None = None
    member: Any | None = None

    @property
    def display(self) -> str:
        if self.full_name:
            return self.full_name
        return f"@{self.username}" if self.username else str(self.user_id)


@dataclass(slots=True)
class CommandContext:
    message: Message
    spec: CommandSpec
    parsed: ParsedCommand
    session: AsyncSession
    container: Container
    user: User
    chat_row: Chat | None = None
    settings: ChatSettings | None = None
    locale: str = "ru"
    extra: dict[str, Any] = field(default_factory=dict)

    # --- Идентификаторы -----------------------------------------------------
    @property
    def chat(self):
        return self.message.chat

    @property
    def chat_id(self) -> int:
        return self.message.chat.id

    @property
    def user_id(self) -> int:
        return self.message.from_user.id if self.message.from_user else 0

    @property
    def args(self) -> tuple[str, ...]:
        return self.parsed.args

    @property
    def args_text(self) -> str:
        return self.parsed.raw_args

    @property
    def is_group(self) -> bool:
        return self.message.chat.type in {"group", "supergroup"}

    @property
    def is_private(self) -> bool:
        return self.message.chat.type == "private"

    @property
    def bot(self):
        return self.container.bot

    # --- Сервисы (создаются на один запрос) ---------------------------------
    @property
    def economy(self):
        return self.container.economy(self.session)

    @property
    def members(self):
        return self.container.members(self.session)

    @property
    def permissions(self):
        return self.container.permissions(self.session)

    @property
    def levels(self):
        return self.container.levels(self.session)

    @property
    def moderation(self):
        return self.container.moderation(self.session, self.settings)

    @property
    def analytics(self):
        return self.container.analytics(self.session)

    @property
    def tickets(self):
        return self.container.tickets(self.session)

    @property
    def ai(self):
        return self.container.ai(self.session)

    # --- Ответы -------------------------------------------------------------
    async def reply(
        self,
        text: str,
        *,
        keyboard: InlineKeyboardMarkup | ReplyKeyboardMarkup | None = None,
        disable_preview: bool = True,
        **kwargs: Any,
    ) -> Message | None:
        try:
            return await self.message.answer(
                text,
                reply_markup=keyboard,
                parse_mode="HTML",
                disable_web_page_preview=disable_preview,
                **kwargs,
            )
        except Exception as exc:  # noqa: BLE001 - сеть/права Telegram
            log.warning(
                "Не удалось отправить ответ",
                extra={"chat_id": self.chat_id, "command": self.spec.name, "error": str(exc)},
            )
            return None

    async def reply_plain(self, text: str, **kwargs: Any) -> Message | None:
        try:
            return await self.message.answer(text, **kwargs)
        except Exception as exc:  # noqa: BLE001
            log.warning("Не удалось отправить ответ", extra={"error": str(exc)})
            return None

    async def delete_trigger(self) -> bool:
        try:
            await self.message.delete()
            return True
        except Exception:  # noqa: BLE001 - у бота может не быть прав
            return False

    # --- Права --------------------------------------------------------------
    async def is_admin(self, user_id: int | None = None) -> bool:
        return await self.permissions.is_chat_admin(self.chat_id, user_id or self.user_id)

    async def has_permission(self, permission: str) -> bool:
        return await self.permissions.has_permission(self.chat_id, self.user_id, permission)

    async def require_admin(self, permission: str | None = None) -> bool:
        allowed = await self.permissions.has_permission(
            self.chat_id, self.user_id, permission or self.spec.permission or "moderation"
        )
        if not allowed:
            await self.reply(self.container.texts.t(self.locale, "no_permission"))
        return allowed

    # --- Аргументы ----------------------------------------------------------
    def arg(self, index: int, default: str | None = None) -> str | None:
        try:
            return self.args[index]
        except IndexError:
            return default

    def int_arg(self, index: int) -> int | None:
        value = self.arg(index)
        if value is None:
            return None
        try:
            return int(value.replace(" ", "").replace("_", ""))
        except ValueError:
            return None

    # --- Цель действия ------------------------------------------------------
    async def resolve_target(self, *, index: int = 0, allow_self: bool = False) -> Target | None:
        """Reply → упоминание → @username → числовой ID → сохранённый ответ."""
        msg = self.message
        if msg.reply_to_message and msg.reply_to_message.from_user:
            reply_user = msg.reply_to_message.from_user
            if reply_user.is_bot and not allow_self:
                pass
            return Target(
                user_id=reply_user.id,
                username=reply_user.username,
                full_name=reply_user.full_name,
            )

        raw = self.arg(index)
        if not raw:
            return None

        if raw.startswith("@") or raw.lstrip("-").isdigit():
            member = await self.members.find_in_chat(self.chat_id, raw)
            if member is not None:
                return Target(user_id=member.user_id, username=member.username, full_name=member.full_name)
        if raw.startswith("@") and len(raw) > 1:
            return Target(user_id=0, username=raw[1:], full_name=raw)
        if raw.lstrip("-").isdigit():
            return Target(user_id=int(raw), full_name=raw)
        return None

    def t(self, key: str, **kwargs: Any) -> str:
        return self.container.texts.t(self.locale, key, **kwargs)
