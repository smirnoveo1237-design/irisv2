"""Аналитика: статистика группы, топы, статистика модерации."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select

from app.commands.context import CommandContext
from app.commands.registry import command
from app.container import Container
from app.core.texts import texts
from app.database.models import AuditLog
from app.modules.common import escape, mention
from app.ui.keyboards import back_keyboard, menu_with_rows
from app.ui.render import edit_or_send

router = Router(name="iris.analytics")


@command(
    "стата",
    aliases=("статистика", "stats", "stat"),
    module="analytics",
    category="analytics",
    description_ru="Статистика группы за неделю",
    description_en="Chat statistics for a week",
    usage="стата",
    cooldown=5,
    group_only=True,
)
async def stats(ctx: CommandContext) -> None:
    summary = await ctx.analytics.summary(ctx.chat_id)
    text = ctx.t("stats_title") + "\n\n" + ctx.t("stats_body", **summary)
    await ctx.reply(text, keyboard=menu_with_rows(ctx.locale, [[("🏆 Рейтинг", "menu:ratings")]]))


@command(
    "топ",
    aliases=("top", "лидеры"),
    module="analytics",
    category="analytics",
    description_ru="Топ активных участников",
    description_en="Top active members",
    usage="топ",
    cooldown=5,
    group_only=True,
)
async def top(ctx: CommandContext) -> None:
    rows = await ctx.analytics.top_members(ctx.chat_id, 10)
    if not rows:
        await ctx.reply(ctx.t("leaderboard_empty"))
        return
    lines = [f"🏆 <b>{'Топ участников' if ctx.locale == 'ru' else 'Top members'}</b>", ""]
    for index, row in enumerate(rows, start=1):
        lines.append(
            f"{index}. {mention(row.user_id, row.full_name)} — <b>{row.message_count}</b> сообщений"
        )
    await ctx.reply("\n".join(lines))


@command(
    "модстата",
    aliases=("modstats",),
    module="analytics",
    category="analytics",
    description_ru="Статистика модерации за неделю",
    description_en="Moderation statistics for a week",
    usage="модстата",
    permission="moderation",
    cooldown=5,
    group_only=True,
)
async def mod_stats(ctx: CommandContext) -> None:
    stats_data = await ctx.analytics.moderation_stats(ctx.chat_id, 7)
    economy = await ctx.analytics.economy_stats(ctx.chat_id)
    lines = ["🛡️ <b>Модерация за 7 дней</b>", ""]
    titles = {"ban": "Баны", "mute": "Муты", "warn": "Предупреждения", "kick": "Кики", "unban": "Разбаны", "unmute": "Размуты"}
    for action, count in stats_data.items():
        lines.append(f"• {titles.get(action, action)}: <b>{count}</b>")
    if not stats_data:
        lines.append("Наказаний не было — отличная атмосфера!")
    lines += [
        "",
        "💰 <b>Экономика</b>",
        f"• Кошельков: <b>{economy['wallets']}</b>",
        f"• В обороте: <b>{economy['balance']}</b>",
        f"• Всего заработано: <b>{economy['earned']}</b>",
    ]
    await ctx.reply("\n".join(lines))


@command(
    "журнал",
    aliases=("audit", "логи"),
    module="analytics",
    category="general",
    description_ru="Последние действия модераторов и команд",
    description_en="Recent moderation and command actions",
    usage="журнал",
    permission="settings",
    group_only=True,
    cooldown=3,
)
async def audit_log(ctx: CommandContext) -> None:
    rows = list(
        await ctx.session.scalars(
            select(AuditLog)
            .where(AuditLog.chat_id == ctx.chat_id)
            .order_by(AuditLog.id.desc())
            .limit(15)
        )
    )
    if not rows:
        await ctx.reply(ctx.t("audit_empty"))
        return
    lines = [ctx.t("audit_title"), ""]
    for row in rows:
        payload = row.payload or {}
        detail = payload.get("command") or payload.get("reason") or ""
        lines.append(
            f"• {row.created_at:%d.%m %H:%M} — <b>{escape(row.action)}</b> "
            f"{mention(row.actor_id) if row.actor_id else ''} {escape(str(detail))}".rstrip()
        )
    await ctx.reply("\n".join(lines))


@router.callback_query(F.data == "analytics:week")
async def cb_week(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.message is None:
        await callback.answer()
        return
    chat_id = callback.message.chat.id
    async with container.db.session_scope() as session:
        settings = await container.chats.settings(session, chat_id)
        locale = container.locale(settings)
        summary = await container.analytics(session).summary(chat_id)
        text = texts.t(locale, "stats_title") + "\n\n" + texts.t(locale, "stats_body", **summary)
    await edit_or_send(callback, text, back_keyboard(locale))
    await callback.answer()


__all__ = ["router", "stats", "top", "mod_stats"]
