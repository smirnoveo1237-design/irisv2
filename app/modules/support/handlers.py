"""Поддержка: тикеты пользователей и ответы команды."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.types import Message
from sqlalchemy import select

from app.commands.context import CommandContext
from app.commands.registry import command
from app.container import Container
from app.core.texts import texts
from app.database.models import Ticket, TicketMessage
from app.modules.common import escape, mention
from app.services.tickets import TicketError

router = Router(name="iris.support")


@command(
    "поддержка",
    aliases=("support", "тикет"),
    module="support",
    category="support",
    description_ru="Создать обращение в поддержку",
    description_en="Open a support ticket",
    usage="поддержка не работает капча",
    cooldown=20,
)
async def support(ctx: CommandContext) -> None:
    subject = ctx.args_text.strip()
    if len(subject) < 5:
        await ctx.reply(ctx.t("support_hint"))
        return
    ticket = await ctx.tickets.open_ticket(ctx.user_id, subject, chat_id=ctx.chat_id)
    await ctx.reply(ctx.t("support_created", ticket_id=ticket.id))
    if not ctx.container.settings.support_chat_id:
        await ctx.reply(ctx.t("support_no_chat"))


@command(
    "ответ",
    aliases=("reply_ticket", "ответить"),
    module="support",
    category="support",
    description_ru="Ответить пользователю по тикету (команда поддержки)",
    description_en="Reply to a ticket (support staff)",
    usage="ответ 5 Ваш вопрос решён",
    owner=True,
    cooldown=2,
)
async def reply_ticket(ctx: CommandContext) -> None:
    ticket_id = ctx.int_arg(0)
    text = " ".join(ctx.args[1:]).strip()
    if ticket_id is None or not text:
        await ctx.reply(ctx.t("not_enough_args", usage=ctx.spec.usage))
        return
    try:
        await ctx.tickets.reply_from_staff(ticket_id, text[:3500])
    except TicketError as exc:
        if str(exc) == "user unreachable":
            await ctx.reply("⚠️ Пользователь закрыл личные сообщения — ответ не доставлен.")
        elif str(exc) == "ticket closed":
            await ctx.reply("🔒 Тикет уже закрыт.")
        else:
            await ctx.reply("🔍 Тикет не найден.")
        return
    await ctx.reply(f"✅ Ответ по тикету <b>#{ticket_id}</b> отправлен.")


@command(
    "закрыть",
    aliases=("closeticket",),
    module="support",
    category="support",
    description_ru="Закрыть тикет",
    description_en="Close a ticket",
    usage="закрыть 5",
    owner=True,
    cooldown=2,
)
async def close_ticket(ctx: CommandContext) -> None:
    ticket_id = ctx.int_arg(0)
    if ticket_id is None:
        await ctx.reply(ctx.t("not_enough_args", usage=ctx.spec.usage))
        return
    try:
        ticket = await ctx.tickets.close(ticket_id)
    except TicketError:
        await ctx.reply("🔍 Тикет не найден.")
        return
    await ctx.reply(ctx.t("support_closed", ticket_id=ticket.id))
    if ctx.container.bot is not None:
        try:
            await ctx.container.bot.send_message(
                ticket.user_id, texts.t("ru", "support_closed", ticket_id=ticket.id)
            )
        except Exception:  # noqa: BLE001
            pass


@router.message(F.chat.type == "private", F.text)
async def private_ticket(message: Message, container: Container | None = None) -> None:
    """Продолжение переписки в личке: сообщение уходит в чат поддержки."""
    if container is None or message.from_user is None or message.text is None:
        raise SkipHandler
    if message.text.startswith("/"):
        raise SkipHandler

    async with container.db.session_scope() as session:
        ticket = await container.tickets(session).active_for_user(message.from_user.id)
        if ticket is None:
            raise SkipHandler
        await container.tickets(session).add_message(
            ticket, message.from_user.id, message.text[:3500], is_staff=False
        )
        support_chat = container.settings.support_chat_id
        if support_chat and container.bot is not None:
            await container.bot.send_message(
                support_chat,
                f"📩 <b>Тикет #{ticket.id}</b> · сообщение от {mention(message.from_user.id, message.from_user.full_name)}\n\n"
                f"{escape(message.text[:3000])}\n\nОтвет: <code>ирис ответ {ticket.id} текст</code>",
            )
        await message.answer(f"✅ Сообщение добавлено в тикет <b>#{ticket.id}</b>.")


__all__ = ["router", "support", "reply_ticket", "close_ticket", "private_ticket", "select", "Ticket", "TicketMessage"]
