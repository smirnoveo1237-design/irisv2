"""Поддержка: тикеты между пользователем и чатом поддержки."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.exceptions import TelegramAPIError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.texts import escape_html
from app.core.timeutil import now_utc
from app.database.models import Ticket, TicketMessage

if TYPE_CHECKING:
    from app.container import Container

log = get_logger(__name__)


class TicketError(Exception):
    pass


class TicketService:
    def __init__(self, session: AsyncSession, container: Container) -> None:
        self.session = session
        self.container = container

    @property
    def support_chat_id(self) -> int | None:
        return self.container.settings.support_chat_id

    async def open_ticket(
        self, user_id: int, subject: str, *, chat_id: int | None = None
    ) -> Ticket:
        ticket = Ticket(user_id=user_id, chat_id=chat_id, subject=subject[:255])
        self.session.add(ticket)
        await self.session.flush()
        self.session.add(
            TicketMessage(ticket_id=ticket.id, author_id=user_id, content=subject, is_staff=False)
        )

        if self.support_chat_id and self.container.bot is not None:
            text = (
                f"📩 <b>Тикет #{ticket.id}</b>\n"
                f"👤 <code>{user_id}</code>\n"
                f"📝 {escape_html(subject[:3500])}\n\n"
                f"Ответ: <code>ирис ответ {ticket.id} текст</code>"
            )
            try:
                message = await self.container.bot.send_message(self.support_chat_id, text)
                ticket.support_message_id = message.message_id
            except TelegramAPIError:
                log.warning("Не удалось отправить тикет в чат поддержки", extra={"ticket_id": ticket.id})
        await self.session.flush()
        return ticket

    async def add_message(self, ticket: Ticket, author_id: int, content: str, *, is_staff: bool) -> None:
        self.session.add(
            TicketMessage(ticket_id=ticket.id, author_id=author_id, content=content, is_staff=is_staff)
        )
        ticket.updated_at = now_utc()
        await self.session.flush()

    async def reply_from_staff(self, ticket_id: int, text: str) -> Ticket:
        ticket = await self.session.get(Ticket, ticket_id)
        if ticket is None:
            raise TicketError("ticket not found")
        if ticket.status == "closed":
            raise TicketError("ticket closed")

        await self.add_message(ticket, author_id=0, content=text, is_staff=True)
        if self.container.bot is None:
            raise TicketError("bot is not configured")
        try:
            await self.container.bot.send_message(
                ticket.user_id,
                f"📩 <b>Ответ по тикету #{ticket.id}</b>\n\n{escape_html(text)}",
            )
        except TelegramAPIError as exc:
            raise TicketError("user unreachable") from exc
        return ticket

    async def close(self, ticket_id: int) -> Ticket:
        ticket = await self.session.get(Ticket, ticket_id)
        if ticket is None:
            raise TicketError("ticket not found")
        ticket.status = "closed"
        await self.session.flush()
        return ticket

    async def active_for_user(self, user_id: int) -> Ticket | None:
        return await self.session.scalar(
            select(Ticket)
            .where(Ticket.user_id == user_id, Ticket.status == "open")
            .order_by(Ticket.id.desc())
        )

    async def by_support_message(self, support_message_id: int) -> Ticket | None:
        return await self.session.scalar(
            select(Ticket).where(Ticket.support_message_id == support_message_id)
        )
