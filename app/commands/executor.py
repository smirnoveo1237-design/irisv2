"""Выполнение команды: проверки прав, кулдаун, вызов обработчика."""

from __future__ import annotations

from app.commands.context import CommandContext
from app.core.logging import get_logger

log = get_logger(__name__)


async def execute_command(ctx: CommandContext) -> None:
    spec = ctx.spec
    text = ctx.container.texts
    locale = ctx.locale

    if spec.private_only and not ctx.is_private:
        await ctx.reply(text.t(locale, "private_only"))
        return
    if spec.group_only and not ctx.is_group:
        await ctx.reply(text.t(locale, "group_only"))
        return

    if spec.owner and not ctx.permissions.is_owner(ctx.user_id):
        await ctx.reply(text.t(locale, "owner_only"))
        return

    if spec.admin or spec.permission:
        permission = spec.permission or "moderation"
        if not await ctx.permissions.has_permission(ctx.chat_id, ctx.user_id, permission):
            await ctx.reply(text.t(locale, "no_permission"))
            return

    if ctx.settings is not None and not ctx.container.chats.module_enabled(
        ctx.settings, spec.module
    ):
        await ctx.reply(text.t(locale, "module_disabled"))
        return

    if spec.cooldown:
        key = f"cmd_cd:{ctx.chat_id}:{ctx.user_id}:{spec.name}"
        if await ctx.container.cache.get(key):
            return
        await ctx.container.cache.set(key, "1", ttl=spec.cooldown)

    log.info(
        "Команда",
        extra={
            "command": spec.name,
            "module_name": spec.module,
            "chat_id": ctx.chat_id,
            "user_id": ctx.user_id,
            "cmd_args": ctx.args_text[:120],
        },
    )

    try:
        await spec.handler(ctx)
    except Exception as exc:  # noqa: BLE001 - одна команда не должна ронять апдейт
        log.exception(
            "Ошибка выполнения команды",
            extra={"command": spec.name, "chat_id": ctx.chat_id, "error": str(exc)},
        )
        await ctx.session.rollback()
        await ctx.reply(text.t(locale, "error"))
