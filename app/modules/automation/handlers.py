"""Автоматизация: список правил и управление ими."""

from __future__ import annotations

from aiogram import Router
from sqlalchemy import select

from app.commands.context import CommandContext
from app.commands.registry import command
from app.database.models import Automation
from app.services.automation import AutomationService
from app.ui.keyboards import menu_with_rows

router = Router(name="iris.automation")


def _format_rule(rule: Automation) -> str:
    conditions = ", ".join(f"{key}={value}" for key, value in (rule.conditions or {}).items())
    actions = ", ".join(
        f"{item.get('type')}" + (f"({item.get('text') or item.get('minutes') or item.get('amount')})" if len(item) > 1 else "")
        for item in (rule.actions or [])
    )
    state = "✅" if rule.is_active else "⏸️"
    return f"{state} <b>#{rule.id}</b> · {rule.event} · if: {conditions or '—'} → {actions} · срабатываний: {rule.trigger_count}"


@command(
    "авто",
    aliases=("auto", "автоматизация"),
    module="automation",
    category="automation",
    description_ru="Автоматизации группы: событие → условие → действие",
    description_en="Chat automations",
    usage="авто добавить слово=привет ответ=Здравствуйте, {user}!",
    permission="settings",
    group_only=True,
    cooldown=3,
)
async def automation(ctx: CommandContext) -> None:
    sub = (ctx.arg(0) or "").lower()

    if sub in {"добавить", "add", "+"}:
        raw = ctx.args_text.split(" ", 1)[1] if " " in ctx.args_text else ""
        parsed = AutomationService.parse_rule(raw)
        if parsed is None:
            await ctx.reply(ctx.t("auto_usage"))
            return
        conditions, actions = parsed
        name = str(conditions.get("word") or conditions.get("contains") or conditions.get("regex") or "правило")
        rule = Automation(
            chat_id=ctx.chat_id,
            name=name[:64],
            event="message",
            conditions=conditions,
            actions=actions,
            created_by=ctx.user_id,
        )
        ctx.session.add(rule)
        await ctx.session.flush()
        await ctx.reply(ctx.t("auto_created", id=rule.id))
        return

    if sub in {"удалить", "delete", "del"} and ctx.arg(1) and ctx.arg(1).isdigit():
        rule = await ctx.session.get(Automation, int(ctx.arg(1)))
        if rule is None or rule.chat_id != ctx.chat_id:
            await ctx.reply(ctx.t("auto_not_found"))
            return
        await ctx.session.delete(rule)
        await ctx.reply(ctx.t("auto_deleted"))
        return

    if sub in {"вкл", "on", "выкл", "off"} and ctx.arg(1) and ctx.arg(1).isdigit():
        rule = await ctx.session.get(Automation, int(ctx.arg(1)))
        if rule is None or rule.chat_id != ctx.chat_id:
            await ctx.reply(ctx.t("auto_not_found"))
            return
        rule.is_active = sub in {"вкл", "on"}
        await ctx.session.flush()
        await ctx.reply(ctx.t("auto_toggled", state="включена" if rule.is_active else "выключена"))
        return

    rules = list(
        await ctx.session.scalars(
            select(Automation).where(Automation.chat_id == ctx.chat_id).order_by(Automation.id)
        )
    )
    if not rules:
        await ctx.reply(ctx.t("auto_empty"), keyboard=menu_with_rows(ctx.locale, []))
        return
    lines = [ctx.t("auto_title"), ""] + [_format_rule(rule) for rule in rules]
    lines += [
        "",
        f"Добавить: <code>{ctx.spec.usage}</code>",
        "Удалить: <code>авто удалить 3</code> · вкл/выкл: <code>авто выкл 3</code>",
    ]
    await ctx.reply("\n".join(lines), keyboard=menu_with_rows(ctx.locale, []))


__all__ = ["router", "automation"]
