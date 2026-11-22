"""Модуль «Ирис кто»."""

from __future__ import annotations

import random

from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.commands.context import CommandContext
from app.commands.registry import command
from app.modules.common import escape
from app.modules.iris_who.service import Candidate, build_answer, pick_person

router = Router(name="iris.iris_who")

MAX_TEXT = 200
REROLL_TTL = 300


async def collect_candidates(ctx: CommandContext) -> list[Candidate]:
    bot_id = ctx.container.bot.id if ctx.container.bot else 0
    exclude = {bot_id} if bot_id else set()
    members = await ctx.members.random_candidates(ctx.chat_id, exclude=exclude, limit=80)
    result = [
        Candidate(user_id=member.user_id, name=member.full_name or f"id{member.user_id}")
        for member in members
    ]

    if not result and ctx.is_group and ctx.container.bot is not None:
        try:
            admins = await ctx.container.bot.get_chat_administrators(ctx.chat_id)
        except TelegramAPIError:
            admins = []
        for admin in admins:
            user = admin.user
            if user.is_bot or (bot_id and user.id == bot_id):
                continue
            result.append(Candidate(user_id=user.id, name=user.full_name))
    return result


def reroll_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔮 Ещё раз", callback_data="who:reroll")]
        ]
    )


@command(
    "кто",
    aliases=("who",),
    module="iris_who",
    category="fun",
    description_ru="Случайный участник в ответ на любой вопрос «кто ...»",
    description_en="Random member for any “who ...” question",
    usage="кто самый смешной",
    cooldown=2,
    examples=("ирис кто самый умный", "кто сегодня женится", "!кто главный мем", ".кто лидер"),
)
async def iris_who(ctx: CommandContext) -> None:
    if not ctx.is_group:
        await ctx.reply(ctx.t("group_only"))
        return

    candidates = await collect_candidates(ctx)
    bot_id = ctx.container.bot.id if ctx.container.bot else 0
    person = pick_person(candidates, exclude_ids={bot_id} if bot_id else set(), rng=random.Random())
    if person is None:
        await ctx.reply(ctx.t("who_not_enough"))
        return

    raw_text = ctx.args_text[:MAX_TEXT]
    answer = build_answer(person, raw_text, locale=ctx.locale)
    title = "🔮 <b>Ирис кто</b>" if ctx.locale == "ru" else "🔮 <b>Iris who</b>"
    await ctx.reply(f"{title}\n\n{answer}", keyboard=reroll_keyboard())

    key = f"who:{ctx.chat_id}:{ctx.user_id}"
    await ctx.container.cache.set(key, raw_text or ".", ttl=REROLL_TTL)


@router.callback_query(lambda call: call.data == "who:reroll")
async def who_reroll(callback, **kwargs) -> None:
    if callback.message is None or callback.from_user is None:
        return await callback.answer()
    chat_id = callback.message.chat.id
    container = kwargs.get("container")
    if container is None:
        await callback.answer()
        return

    key = f"who:{chat_id}:{callback.from_user.id}"
    text = await container.cache.get(key)
    async with container.db.session_scope() as session:
        members = await container.members(session).random_candidates(chat_id, limit=80)
        bot_id = container.bot.id if container.bot else 0
        candidates = [
            Candidate(user_id=member.user_id, name=member.full_name or f"id{member.user_id}")
            for member in members
            if not member.is_bot and (not bot_id or member.user_id != bot_id)
        ]
        person = pick_person(candidates, exclude_ids={bot_id} if bot_id else set())
        if person is None:
            await callback.answer("Нет участников", show_alert=False)
            return
        locale = (await container.chats.settings(session, chat_id)).locale  # type: ignore[union-attr]
        answer = build_answer(person, text if text != "." else None, locale=locale)

    try:
        await callback.message.edit_text(
            f"🔮 <b>{'Ирис кто' if not locale.startswith('en') else 'Iris who'}</b>\n\n{answer}",
            reply_markup=reroll_keyboard(),
        )
    except Exception:  # noqa: BLE001 - сообщение могло не измениться
        pass
    await callback.answer()


__all__ = ["router", "iris_who", "collect_candidates", "escape"]
