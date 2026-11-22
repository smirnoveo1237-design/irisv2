"""Модуль «Шипперим»: случайная пара без процентов."""

from __future__ import annotations

import random
import time

from aiogram import Router
from sqlalchemy import select

from app.commands.context import CommandContext
from app.commands.registry import command
from app.database.models import ShipperPair
from app.modules.shipper.service import Candidate, build_ship_message, choose_pair

router = Router(name="iris.shipper")

RECENT_LIMIT = 12
MAX_COOLDOWN = 86_400


async def collect_candidates(ctx: CommandContext) -> list[Candidate]:
    """Реальные участники из реестра плюс сам IrisV2 как участник шутки."""
    bot = ctx.container.bot
    bot_id = bot.id if bot else 0

    def to_candidates(rows) -> list[Candidate]:
        return [
            Candidate(
                user_id=member.user_id,
                name=member.full_name or f"id{member.user_id}",
                username=member.username,
                is_bot=member.is_bot,
            )
            for member in rows
            if not member.is_bot and (not bot_id or member.user_id != bot_id)
        ]

    members = await ctx.members.random_candidates(ctx.chat_id, limit=80)
    result = to_candidates(members)

    if len(result) < 2 and ctx.is_group:
        added = await ctx.members.sync_admins(bot, ctx.chat_id)
        if added:
            members = await ctx.members.random_candidates(ctx.chat_id, limit=80)
            result = to_candidates(members)

    username = ctx.container.settings.bot_username
    if username:
        result.append(
            Candidate(
                user_id=bot_id or 0,
                name="IrisV2",
                username=username,
                is_bot=True,
                is_self=True,
            )
        )

    unique: dict[int, Candidate] = {}
    for candidate in result:
        unique.setdefault(candidate.user_id, candidate)
    return list(unique.values())


async def recent_pairs(session, chat_id: int) -> set[frozenset[int]]:
    rows = await session.execute(
        select(ShipperPair.user_a, ShipperPair.user_b)
        .where(ShipperPair.chat_id == chat_id)
        .order_by(ShipperPair.created_at.desc())
        .limit(RECENT_LIMIT)
    )
    return {frozenset((a, b)) for a, b in rows.all()}


@command(
    "шипперим",
    aliases=("ship", "шипперить"),
    module="shipper",
    category="fun",
    description_ru="Случайная пара участников (без процентов)",
    description_en="Random pair of members",
    usage="шипперим",
    cooldown=1,
    examples=("шипперим", "ирис шипперим", "шипперим задержка 60"),
)
async def shipperim(ctx: CommandContext) -> None:
    if not ctx.is_group:
        await ctx.reply(ctx.t("group_only"))
        return

    sub = (ctx.arg(0) or "").casefold()
    if sub in {"задержка", "delay", "кулдаун", "cooldown"}:
        if not await ctx.has_permission("settings"):
            await ctx.reply(ctx.t("no_permission"))
            return
        current = ctx.settings.ship_cooldown if ctx.settings else 30
        if ctx.arg(1) is None:
            await ctx.reply(
                f"💘 Задержка «Шипперим»: <b>{current}</b> с.\n"
                "Изменить: <code>шипперим задержка 60</code> (0 — без задержки)."
            )
            return
        value = ctx.int_arg(1)
        if value is None or not 0 <= value <= MAX_COOLDOWN:
            await ctx.reply(
                "⏱️ Укажите целое число секунд от 0 до 86400: "
                "<code>шипперим задержка 60</code>"
            )
            return
        await ctx.container.chats.update(ctx.session, ctx.chat_id, ship_cooldown=value)
        await ctx.reply(f"✅ Задержка «Шипперим» теперь <b>{value}</b> с.")
        return

    cooldown = ctx.settings.ship_cooldown if ctx.settings else 30
    cache_key = f"ship_cd:{ctx.chat_id}"
    if cooldown:
        last = await ctx.container.cache.get(cache_key)
        if last is not None:
            try:
                elapsed = time.time() - float(last)
            except ValueError:
                elapsed = cooldown
            if elapsed < cooldown:
                wait = max(1, int(cooldown - elapsed) + 1)
                text = (
                    f"💘 Следующий шипперим через <b>{wait}</b> с."
                    if ctx.locale == "ru"
                    else f"💘 Next ship in <b>{wait}</b> s."
                )
                await ctx.reply(text)
                return

    rng = random.Random()
    candidates = await collect_candidates(ctx)
    if len(candidates) < 2:
        await ctx.reply(ctx.t("ship_not_enough"))
        return

    picked = choose_pair(
        candidates,
        initiator_id=ctx.user_id,
        recent_pairs=await recent_pairs(ctx.session, ctx.chat_id),
        rng=rng,
    )
    if picked is None:
        await ctx.reply(ctx.t("ship_not_enough"))
        return

    first, second, _repeated = picked
    ctx.session.add(
        ShipperPair(
            chat_id=ctx.chat_id,
            user_a=first.user_id,
            user_b=second.user_id,
            score=0,
        )
    )
    await ctx.session.flush()

    await ctx.reply(build_ship_message(first, second, rng))
    if cooldown:
        await ctx.container.cache.set(cache_key, str(time.time()), ttl=cooldown)


__all__ = ["router", "shipperim", "collect_candidates", "recent_pairs"]
