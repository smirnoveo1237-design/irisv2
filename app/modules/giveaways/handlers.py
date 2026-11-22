"""Розыгрыши и голосования."""

from __future__ import annotations

import random
from datetime import timedelta

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.commands.context import CommandContext
from app.commands.registry import command
from app.container import Container
from app.core.texts import texts
from app.core.timeutil import format_datetime, now_utc
from app.database.models import Giveaway, GiveawayMember, Poll, PollVote
from app.modules.common import escape, mention
from app.ui.keyboards import menu_with_rows
from app.ui.render import answer_alert

router = Router(name="iris.giveaways")


@command(
    "розыгрыш",
    aliases=("giveaway", "конкурс"),
    module="giveaways",
    category="games",
    description_ru="Запустить розыгрыш: приз | минуты",
    description_en="Start a giveaway: prize | minutes",
    usage="розыгрыш 100 Ирисок | 60",
    permission="giveaway",
    group_only=True,
    cooldown=5,
)
async def giveaway(ctx: CommandContext) -> None:
    raw = ctx.args_text.strip()
    if "|" not in raw:
        await ctx.reply(ctx.t("giveaway_usage"))
        return
    prize, _, tail = raw.partition("|")
    prize = prize.strip()[:200]
    minutes_raw = tail.strip().split()[0] if tail.strip() else "60"
    try:
        minutes = max(1, min(int(minutes_raw), 60 * 24 * 30))
    except ValueError:
        minutes = 60
    winners = 1
    parts = tail.strip().split()
    if len(parts) > 1 and parts[1].isdigit():
        winners = max(1, min(int(parts[1]), 20))

    ends_at = now_utc() + timedelta(minutes=minutes)
    row = Giveaway(
        chat_id=ctx.chat_id,
        prize=prize,
        winner_count=winners,
        ends_at=ends_at,
        created_by=ctx.user_id,
    )
    ctx.session.add(row)
    await ctx.session.flush()
    text = ctx.t(
        "giveaway_created",
        prize=escape(prize),
        winners=winners,
        ends=format_datetime(ends_at, ctx.container.settings.timezone),
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🎁 Участвовать", callback_data=f"gw:join:{row.id}")]]
    )
    sent = await ctx.reply(text, keyboard=keyboard)
    if sent is not None:
        row.message_id = sent.message_id
    await ctx.session.flush()


@router.callback_query(F.data.startswith("gw:join:"))
async def join_giveaway(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    giveaway_id = int(callback.data.split(":")[2])
    async with container.db.session_scope() as session:
        row = await session.get(Giveaway, giveaway_id)
        settings = await container.chats.settings(session, callback.message.chat.id)
        locale = container.locale(settings)
        if row is None or row.status != "active" or row.ends_at <= now_utc():
            await answer_alert(callback, "⌛ Розыгрыш уже завершён.")
            return
        session.add(GiveawayMember(giveaway_id=row.id, user_id=callback.from_user.id))
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            await answer_alert(callback, texts.t(locale, "giveaway_joined_already"))
            return
        count = int(
            await session.scalar(
                select(func.count())
                .select_from(GiveawayMember)
                .where(GiveawayMember.giveaway_id == row.id)
            )
            or 0
        )
    await answer_alert(callback, f"{texts.t(locale, 'giveaway_join')} Участников: {count}")


@command(
    "розыгрыши",
    aliases=("giveaways",),
    module="giveaways",
    category="games",
    description_ru="Активные розыгрыши",
    description_en="Active giveaways",
    usage="розыгрыши",
    cooldown=5,
    group_only=True,
)
async def giveaway_list(ctx: CommandContext) -> None:
    rows = list(
        await ctx.session.scalars(
            select(Giveaway)
            .where(Giveaway.chat_id == ctx.chat_id, Giveaway.status == "active")
            .order_by(Giveaway.ends_at)
        )
    )
    if not rows:
        await ctx.reply(ctx.t("giveaway_none"))
        return
    lines = ["🎁 <b>Активные розыгрыши</b>", ""]
    for row in rows:
        count = int(
            await ctx.session.scalar(
                select(func.count())
                .select_from(GiveawayMember)
                .where(GiveawayMember.giveaway_id == row.id)
            )
            or 0
        )
        lines.append(
            f"<b>#{row.id}</b> {row.prize} · до {format_datetime(row.ends_at, ctx.container.settings.timezone)} · "
            f"участников: {count}"
        )
    await ctx.reply("\n".join(lines))


# --- Голосования ----------------------------------------------------------
@command(
    "голосование",
    aliases=("poll", "опрос"),
    module="giveaways",
    category="games",
    description_ru="Создать голосование: вопрос | вариант | вариант",
    description_en="Create a poll: question | option | option",
    usage="голосование Пицца или суши? | Пицца | Суши",
    permission="giveaway",
    group_only=True,
    cooldown=5,
)
async def create_poll(ctx: CommandContext) -> None:
    parts = [part.strip() for part in ctx.args_text.split("|") if part.strip()]
    if len(parts) < 3:
        await ctx.reply(ctx.t("poll_usage"))
        return
    question, options = parts[0][:290], parts[1:9]
    row = Poll(
        chat_id=ctx.chat_id,
        question=question,
        options=options,
        created_by=ctx.user_id,
    )
    ctx.session.add(row)
    await ctx.session.flush()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=option[:60], callback_data=f"poll:{row.id}:{index}")]
            for index, option in enumerate(options)
        ]
    )
    sent = await ctx.reply(
        f"🗳️ <b>{escape(question)}</b>\n\n"
        + "\n".join(f"{i + 1}. {escape(opt)}" for i, opt in enumerate(options)),
        keyboard=keyboard,
    )
    if sent is not None:
        row.message_id = sent.message_id
    await ctx.session.flush()


@router.callback_query(F.data.startswith("poll:"))
async def vote(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    _, raw_poll, raw_option = callback.data.split(":")
    poll_id, option = int(raw_poll), int(raw_option)
    async with container.db.session_scope() as session:
        poll = await session.get(Poll, poll_id)
        settings = await container.chats.settings(session, callback.message.chat.id)
        locale = container.locale(settings)
        if poll is None or poll.is_closed:
            await answer_alert(callback, texts.t(locale, "poll_closed"))
            return
        existing = await session.scalar(
            select(PollVote).where(
                PollVote.poll_id == poll_id, PollVote.user_id == callback.from_user.id
            )
        )
        if existing is None:
            session.add(PollVote(poll_id=poll_id, user_id=callback.from_user.id, option_index=option))
        else:
            existing.option_index = option
        await session.flush()

        counts = {index: 0 for index in range(len(poll.options))}
        rows = await session.execute(
            select(PollVote.option_index, func.count())
            .where(PollVote.poll_id == poll_id)
            .group_by(PollVote.option_index)
        )
        for index, count in rows.all():
            counts[int(index)] = int(count)
        total = sum(counts.values()) or 1
        lines = []
        for index, text_option in enumerate(poll.options):
            count = counts.get(index, 0)
            bar = "█" * round(count / total * 10)
            lines.append(f"{index + 1}. {escape(text_option)} — <b>{count}</b> ({count / total:.0%}) {bar}")
        text = texts.t(locale, "poll_results", question=escape(poll.question), lines="\n".join(lines))

    try:
        await callback.message.edit_text(text, reply_markup=callback.message.reply_markup)
    except Exception:  # noqa: BLE001
        pass
    await callback.answer(texts.t(locale, "poll_vote_ok"))


__all__ = ["router", "giveaway", "giveaway_list", "create_poll", "vote", "random", "mention", "menu_with_rows"]
