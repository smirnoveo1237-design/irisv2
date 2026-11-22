"""Жалобы и апелляции."""

from __future__ import annotations

from aiogram import Router
from sqlalchemy import select

from app.commands.context import CommandContext
from app.commands.registry import command
from app.core.timeutil import now_utc
from app.database.models import Report
from app.modules.common import escape, mention
from app.services.moderation import ModerationError
from app.ui.keyboards import menu_with_rows

router = Router(name="iris.reports")


@command(
    "жалоба",
    aliases=("report", "репорт"),
    module="reports",
    category="support",
    description_ru="Пожаловаться на сообщение или участника",
    description_en="Report a message or member",
    usage="жалоба спам ссылками",
    cooldown=10,
    group_only=True,
)
async def report(ctx: CommandContext) -> None:
    reason = ctx.args_text.strip()
    if len(reason) < 4:
        await ctx.reply(ctx.t("not_enough_args", usage=ctx.spec.usage))
        return
    target = await ctx.resolve_target()
    target_id = target.user_id if target else None
    reply = ctx.message.reply_to_message
    row = Report(
        chat_id=ctx.chat_id,
        kind="report",
        reporter_id=ctx.user_id,
        target_id=target_id,
        message_id=reply.message_id if reply else None,
        reason=reason[:1000],
    )
    ctx.session.add(row)
    await ctx.session.flush()

    text = ctx.t(
        "report_title",
        report_id=row.id,
        target=mention(target_id, target.display) if target_id else "—",
        reporter=mention(ctx.user_id),
        reason=escape(reason[:500]),
    )
    await ctx.reply(ctx.t("report_created", report_id=row.id))
    if ctx.settings and ctx.settings.log_channel_id:
        await ctx.moderation.send_log(ctx.chat_id, text)
    else:
        await ctx.reply(text)


@command(
    "апелляция",
    aliases=("appeal",),
    module="reports",
    category="support",
    description_ru="Обжаловать наказание",
    description_en="Appeal a punishment",
    usage="апелляция я не спамил, это была цитата",
    cooldown=30,
)
async def appeal(ctx: CommandContext) -> None:
    reason = ctx.args_text.strip()
    if len(reason) < 5:
        await ctx.reply(ctx.t("not_enough_args", usage=ctx.spec.usage))
        return
    row = Report(
        chat_id=ctx.chat_id,
        kind="appeal",
        reporter_id=ctx.user_id,
        reason=reason[:1000],
    )
    ctx.session.add(row)
    await ctx.session.flush()
    await ctx.reply(ctx.t("appeal_created"))

    target_chat = ctx.container.settings.support_chat_id or (
        ctx.settings.log_channel_id if ctx.settings else None
    )
    if target_chat and ctx.container.bot is not None:
        text = ctx.t(
            "appeal_title",
            report_id=row.id,
            reporter=mention(ctx.user_id),
            reason=escape(reason[:500]),
        )
        try:
            await ctx.container.bot.send_message(target_chat, text)
        except Exception:  # noqa: BLE001
            pass


@command(
    "жалобы",
    aliases=("reports",),
    module="reports",
    category="support",
    description_ru="Открытые жалобы группы",
    description_en="Open reports",
    usage="жалобы",
    permission="moderation",
    group_only=True,
)
async def reports(ctx: CommandContext) -> None:
    rows = list(
        await ctx.session.scalars(
            select(Report)
            .where(Report.chat_id == ctx.chat_id, Report.status == "open")
            .order_by(Report.id)
            .limit(15)
        )
    )
    if not rows:
        await ctx.reply(ctx.t("report_none"))
        return
    lines = ["🚨 <b>Открытые жалобы</b>", ""]
    for row in rows:
        who = mention(row.target_id) if row.target_id else "—"
        lines.append(
            f"<b>#{row.id}</b> · {row.kind} · на {who}\n"
            f"   от {mention(row.reporter_id)}: {escape(row.reason[:160])}"
        )
    lines.append(
        "\nРешить: <code>решить 1 ban</code> · <code>решить 1 mute 60</code> · <code>решить 1 decline</code>"
    )
    await ctx.reply("\n".join(lines), keyboard=menu_with_rows(ctx.locale, []))


@command(
    "решить",
    aliases=("resolve",),
    module="reports",
    category="support",
    description_ru="Закрыть жалобу: ban, mute, decline",
    description_en="Resolve a report: ban, mute, decline",
    usage="решить 1 ban",
    permission="moderation",
    group_only=True,
)
async def resolve(ctx: CommandContext) -> None:
    report_id = ctx.int_arg(0)
    action = (ctx.arg(1) or "").lower()
    if report_id is None or action not in {"ban", "mute", "decline", "отклонить"}:
        await ctx.reply(ctx.t("not_enough_args", usage=ctx.spec.usage))
        return
    row = await ctx.session.get(Report, report_id)
    if row is None or row.chat_id != ctx.chat_id or row.status != "open":
        await ctx.reply("🔍 Жалоба не найдена или уже закрыта.")
        return

    resolution = action
    if action in {"ban", "mute"} and row.target_id:
        try:
            if action == "ban":
                await ctx.moderation.ban(
                    ctx.chat_id, row.target_id, moderator_id=ctx.user_id, reason=f"Жалоба #{row.id}"
                )
            else:
                seconds = (ctx.int_arg(2) or 60) * 60
                await ctx.moderation.mute(
                    ctx.chat_id,
                    row.target_id,
                    moderator_id=ctx.user_id,
                    seconds=seconds,
                    reason=f"Жалоба #{row.id}",
                )
        except ModerationError as exc:
            await ctx.reply(ctx.t("mod_no_rights") if str(exc) == "no_bot_rights" else ctx.t("error"))
            return

    row.status = "resolved"
    row.resolver_id = ctx.user_id
    row.resolution = resolution
    row.resolved_at = now_utc()
    await ctx.session.flush()
    await ctx.reply(f"✅ Жалоба <b>#{row.id}</b> закрыта: {resolution}")


__all__ = ["router", "report", "appeal", "reports", "resolve"]
