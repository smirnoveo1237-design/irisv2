"""Модерация: команды бана, мута, кика, предупреждений и очистки."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.commands.context import CommandContext, Target
from app.commands.registry import command
from app.container import Container
from app.core.timeutil import human_duration, parse_duration
from app.modules.common import escape, mention
from app.services.moderation import ModerationError
from app.services.permissions import PERMISSIONS
from app.ui.keyboards import menu_with_rows
from app.ui.render import edit_or_send

router = Router(name="iris.moderation")


async def _guard(ctx: CommandContext) -> Target | None:
    """Проверяет цель: не себя, не бота, не администратора."""
    target = await ctx.resolve_target()
    if target is None or not target.user_id:
        await ctx.reply(ctx.t("no_target"))
        return None
    if target.user_id == ctx.user_id:
        await ctx.reply(ctx.t("mod_self"))
        return None
    bot_id = ctx.container.bot.id if ctx.container.bot else 0
    if bot_id and target.user_id == bot_id:
        await ctx.reply(ctx.t("mod_bot_target"))
        return None
    member = await ctx.members.get(ctx.chat_id, target.user_id)
    if member is not None and member.is_bot:
        await ctx.reply(ctx.t("mod_bot_target"))
        return None
    if await ctx.permissions.is_chat_admin(ctx.chat_id, target.user_id) and not ctx.permissions.is_owner(ctx.user_id):
        await ctx.reply(ctx.t("mod_admin_target"))
        return None
    return target


def _args_without_target(ctx: CommandContext) -> list[str]:
    args = list(ctx.args)
    if ctx.message.reply_to_message and ctx.message.reply_to_message.from_user:
        return args
    return args[1:] if args else []


async def _handle_error(ctx: CommandContext, exc: ModerationError) -> None:
    if str(exc) == "no_bot_rights":
        await ctx.reply(ctx.t("mod_no_rights"))
    else:
        await ctx.reply(ctx.t("error"))


async def _notify_log(ctx: CommandContext, action: str, target: Target, reason: str) -> None:
    if ctx.settings and ctx.settings.log_channel_id:
        text = ctx.t(
            "mod_log",
            action=action,
            target=mention(target.user_id, target.display),
            moderator=mention(ctx.user_id, ctx.message.from_user.full_name if ctx.message.from_user else None),
            reason=escape(reason) or "—",
        )
        await ctx.moderation.send_log(ctx.chat_id, text)


@command(
    "бан",
    aliases=("ban",),
    module="moderation",
    category="moderation",
    description_ru="Забанить участника (можно на срок: 10м, 2ч, 1д)",
    description_en="Ban a member (optionally for a duration)",
    usage="бан @user 1д причина",
    permission="ban",
    group_only=True,
    cooldown=1,
)
async def ban(ctx: CommandContext) -> None:
    target = await _guard(ctx)
    if target is None:
        return
    args = _args_without_target(ctx)
    seconds = None
    if args:
        parsed = parse_duration(args[0])
        if parsed is not None:
            seconds = parsed
            args = args[1:]
    reason = " ".join(args) or "не указана"
    try:
        until = await ctx.moderation.ban(
            ctx.chat_id, target.user_id, moderator_id=ctx.user_id, reason=reason, seconds=seconds
        )
    except ModerationError as exc:
        await _handle_error(ctx, exc)
        return
    until_text = f"\n⏳ До: {until:%d.%m.%Y %H:%M}" if until else ""
    await ctx.reply(
        ctx.t(
            "mod_banned",
            target=mention(target.user_id, target.display),
            moderator=mention(ctx.user_id),
            reason=escape(reason),
            until=until_text,
        )
    )
    await _notify_log(ctx, "бан", target, reason)


@command(
    "разбан",
    aliases=("unban",),
    module="moderation",
    category="moderation",
    description_ru="Разбанить участника",
    description_en="Unban a member",
    usage="разбан @user",
    permission="ban",
    group_only=True,
)
async def unban(ctx: CommandContext) -> None:
    target = await _guard(ctx)
    if target is None:
        return
    try:
        await ctx.moderation.unban(
            ctx.chat_id, target.user_id, moderator_id=ctx.user_id, reason=" ".join(_args_without_target(ctx))
        )
    except ModerationError as exc:
        await _handle_error(ctx, exc)
        return
    await ctx.reply(ctx.t("mod_unbanned", target=mention(target.user_id, target.display)))
    await _notify_log(ctx, "разбан", target, "")


@command(
    "мут",
    aliases=("mute",),
    module="moderation",
    category="moderation",
    description_ru="Заглушить участника на срок (по умолчанию из настроек)",
    description_en="Mute a member",
    usage="мут @user 30м причина",
    permission="mute",
    group_only=True,
    cooldown=1,
)
async def mute(ctx: CommandContext) -> None:
    target = await _guard(ctx)
    if target is None:
        return
    args = _args_without_target(ctx)
    default_seconds = (ctx.settings.mute_minutes if ctx.settings else 60) * 60
    seconds = default_seconds
    if args:
        parsed = parse_duration(args[0])
        if parsed is not None:
            seconds = parsed or default_seconds
            args = args[1:]
    reason = " ".join(args) or "не указана"
    try:
        await ctx.moderation.mute(
            ctx.chat_id, target.user_id, moderator_id=ctx.user_id, seconds=seconds, reason=reason
        )
    except ModerationError as exc:
        await _handle_error(ctx, exc)
        return
    await ctx.reply(
        ctx.t(
            "mod_muted",
            target=mention(target.user_id, target.display),
            duration=human_duration(seconds, ctx.locale),
            reason=escape(reason),
        )
    )
    await _notify_log(ctx, "мут", target, reason)


@command(
    "размут",
    aliases=("unmute",),
    module="moderation",
    category="moderation",
    description_ru="Снять мут",
    description_en="Unmute a member",
    usage="размут @user",
    permission="mute",
    group_only=True,
)
async def unmute(ctx: CommandContext) -> None:
    target = await _guard(ctx)
    if target is None:
        return
    try:
        await ctx.moderation.unmute(ctx.chat_id, target.user_id, moderator_id=ctx.user_id)
    except ModerationError as exc:
        await _handle_error(ctx, exc)
        return
    await ctx.reply(ctx.t("mod_unmuted", target=mention(target.user_id, target.display)))


@command(
    "кик",
    aliases=("kick",),
    module="moderation",
    category="moderation",
    description_ru="Исключить участника (может вернуться)",
    description_en="Kick a member",
    usage="кик @user",
    permission="kick",
    group_only=True,
)
async def kick(ctx: CommandContext) -> None:
    target = await _guard(ctx)
    if target is None:
        return
    reason = " ".join(_args_without_target(ctx)) or "не указана"
    try:
        await ctx.moderation.kick(ctx.chat_id, target.user_id, moderator_id=ctx.user_id, reason=reason)
    except ModerationError as exc:
        await _handle_error(ctx, exc)
        return
    await ctx.reply(ctx.t("mod_kicked", target=mention(target.user_id, target.display)))
    await _notify_log(ctx, "кик", target, reason)


@command(
    "пред",
    aliases=("варн", "warn"),
    module="moderation",
    category="moderation",
    description_ru="Выдать предупреждение",
    description_en="Warn a member",
    usage="пред @user причина",
    permission="moderation",
    group_only=True,
)
async def warn(ctx: CommandContext) -> None:
    target = await _guard(ctx)
    if target is None:
        return
    reason = " ".join(_args_without_target(ctx)) or "не указана"
    settings = ctx.settings
    result = await ctx.moderation.warn(
        ctx.chat_id,
        target.user_id,
        moderator_id=ctx.user_id,
        reason=reason,
        limit=settings.max_warnings if settings else 3,
        auto_action=settings.warn_action if settings else "mute",
        mute_minutes=settings.mute_minutes if settings else 60,
    )
    text = ctx.t(
        "mod_warned",
        target=mention(target.user_id, target.display),
        count=result.count,
        limit=result.limit,
        reason=escape(reason),
    )
    if result.auto_action:
        text += "\n" + ctx.t("mod_warn_auto", action=result.auto_action)
    await ctx.reply(text)
    await _notify_log(ctx, "предупреждение", target, reason)


@command(
    "снятьпред",
    aliases=("unwarn", "снятьпреды"),
    module="moderation",
    category="moderation",
    description_ru="Снять активные предупреждения",
    description_en="Clear active warnings",
    usage="снятьпред @user",
    permission="moderation",
    group_only=True,
)
async def unwarn(ctx: CommandContext) -> None:
    target = await _guard(ctx)
    if target is None:
        return
    await ctx.moderation.clear_warnings(ctx.chat_id, target.user_id)
    await ctx.reply(ctx.t("mod_warns_cleared", target=mention(target.user_id, target.display)))


@command(
    "преды",
    aliases=("warns", "варны"),
    module="moderation",
    category="moderation",
    description_ru="Показать предупреждения участника",
    description_en="Show member warnings",
    usage="преды @user",
    permission="moderation",
    group_only=True,
)
async def warns(ctx: CommandContext) -> None:
    target = await ctx.resolve_target()
    if target is None or not target.user_id:
        await ctx.reply(ctx.t("no_target"))
        return
    items = await ctx.moderation.list_warnings(ctx.chat_id, target.user_id)
    if not items:
        await ctx.reply(ctx.t("mod_no_warns", target=mention(target.user_id, target.display)))
        return
    lines = [
        f"• {item.created_at:%d.%m %H:%M} — {escape(item.reason or '—')} (мод. {item.moderator_id})"
        for item in items
    ]
    await ctx.reply(
        ctx.t(
            "mod_warns_list",
            target=mention(target.user_id, target.display),
            items="\n".join(lines),
        )
    )


@command(
    "очистить",
    aliases=("clear", "purge"),
    module="moderation",
    category="moderation",
    description_ru="Удалить последние N сообщений",
    description_en="Delete last N messages",
    usage="очистить 20",
    permission="delete",
    group_only=True,
    cooldown=3,
)
async def clear(ctx: CommandContext) -> None:
    count = ctx.int_arg(0) or 10
    count = max(1, min(count, 100))
    reply = ctx.message.reply_to_message
    if reply is not None:
        ids = list(range(reply.message_id, reply.message_id + count))
    else:
        end = ctx.message.message_id
        ids = list(range(max(1, end - count + 1), end + 1))
    deleted = await ctx.moderation.delete_range(ctx.chat_id, ids)
    await ctx.reply(ctx.t("mod_deleted", count=deleted))


@command(
    "история",
    aliases=("history", "наказания"),
    module="moderation",
    category="moderation",
    description_ru="История наказаний участника",
    description_en="Member punishment history",
    usage="история @user",
    permission="moderation",
    group_only=True,
)
async def history(ctx: CommandContext) -> None:
    target = await ctx.resolve_target()
    if target is None or not target.user_id:
        await ctx.reply(ctx.t("no_target"))
        return
    items = await ctx.moderation.history(ctx.chat_id, target.user_id, limit=10)
    if not items:
        await ctx.reply(ctx.t("mod_history_empty"))
        return
    lines = [
        f"• {item.created_at:%d.%m.%Y %H:%M} — <b>{item.action}</b> "
        f"({escape(item.reason or '—')}, мод. {item.moderator_id})"
        for item in items
    ]
    await ctx.reply(
        ctx.t("mod_history_title")
        + f"\n\n{mention(target.user_id, target.display)}\n"
        + "\n".join(lines)
    )


@command(
    "роль",
    aliases=("роли", "role"),
    module="moderation",
    category="moderation",
    description_ru="Роли IrisV2 и права модераторов",
    description_en="IrisV2 roles and moderator permissions",
    usage="роль выдать @user Модератор",
    permission="roles",
    group_only=True,
    cooldown=2,
)
async def role_command(ctx: CommandContext) -> None:
    sub = (ctx.arg(0) or "").lower()
    service = ctx.container.permissions(ctx.session)
    available = ", ".join(sorted(PERMISSIONS))

    if sub in {"создать", "create"}:
        name = (ctx.arg(1) or "").strip()
        raw = ctx.arg(2) or ""
        items = [item.strip() for item in raw.replace(" ", ",").split(",") if item.strip()]
        invalid = [item for item in items if item not in PERMISSIONS and item != "*"]
        if not name or not items or invalid:
            await ctx.reply(
                "✍️ Формат: <code>роль создать Модератор ban,mute,warn</code>\n"
                f"Доступные права: <code>{available}</code>"
            )
            return
        if await service.get_role(ctx.chat_id, name) is not None:
            await ctx.reply("🔍 Роль с таким названием уже есть.")
            return
        role = await service.create_role(ctx.chat_id, name[:64], items)
        await ctx.reply(f"✅ Роль <b>{escape(role.name)}</b> создана: {', '.join(items)}")
        return

    if sub in {"выдать", "grant", "дать", "снять", "revoke", "забрать"}:
        if ctx.message.reply_to_message and ctx.message.reply_to_message.from_user:
            target = await ctx.resolve_target()
            role_name = " ".join(ctx.args[1:]).strip()
        else:
            target = await ctx.resolve_target(index=1)
            role_name = " ".join(ctx.args[2:]).strip()
        if target is None or not target.user_id:
            await ctx.reply(ctx.t("no_target"))
            return
        role = await service.get_role(ctx.chat_id, role_name)
        if role is None:
            await ctx.reply("🔍 Роль не найдена. Список: <code>роль</code>")
            return
        if sub in {"выдать", "grant", "дать"}:
            await service.grant_role(ctx.chat_id, target.user_id, role)
            await ctx.reply(f"✅ {mention(target.user_id, target.display)} получил роль <b>{escape(role.name)}</b>.")
        else:
            removed = await service.revoke_role(ctx.chat_id, target.user_id, role)
            await ctx.reply(
                f"✅ Роль <b>{escape(role.name)}</b> снята."
                if removed
                else "ℹ️ У участника не было этой роли."
            )
        return

    roles = await service.list_roles(ctx.chat_id)
    if not roles:
        await ctx.reply(
            "🧩 Ролей пока нет.\n\n"
            f"Создать: <code>роль создать Модератор ban,mute,warn</code>\n"
            f"Доступные права: <code>{available}</code>"
        )
        return
    lines = ["🧩 <b>Роли группы</b>", ""]
    for role in roles:
        lines.append(f"• <b>{escape(role.name)}</b> ({role.id}) — {', '.join(role.permissions) or '—'}")
    lines.append("\nВыдать: <code>роль выдать @user Название</code> · снять: <code>роль снять @user Название</code>")
    await ctx.reply("\n".join(lines))


@router.callback_query(F.data == "mod:warns_help")
async def cb_warns_help(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.message is None:
        await callback.answer()
        return
    async with container.db.session_scope() as session:
        settings = await container.chats.settings(session, callback.message.chat.id)
        locale = container.locale(settings)
    text = (
        "⚠️ <b>Предупреждения</b>\n\n"
        f"Лимит: <b>{settings.max_warnings if settings else 3}</b>. После лимита применяется "
        f"<b>{settings.warn_action if settings else 'mute'}</b>.\n\n"
        "<code>пред @user причина</code> — выдать\n"
        "<code>преды @user</code> — посмотреть\n"
        "<code>снятьпред @user</code> — снять все"
    )
    await edit_or_send(callback, text, menu_with_rows(locale, [[("⬅️ Меню", "menu:main")]]))
    await callback.answer()


@router.callback_query(F.data == "mod:reports")
async def cb_reports(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.message is None:
        await callback.answer()
        return
    from sqlalchemy import func, select

    from app.database.models import Report

    async with container.db.session_scope() as session:
        settings = await container.chats.settings(session, callback.message.chat.id)
        locale = container.locale(settings)
        count = int(
            await session.scalar(
                select(func.count())
                .select_from(Report)
                .where(Report.chat_id == callback.message.chat.id, Report.status == "open")
            )
            or 0
        )
    text = f"🚨 Открытых жалоб: <b>{count}</b>\n\n<code>ирис жалобы</code> — список и решения."
    if locale.startswith("en"):
        text = f"🚨 Open reports: <b>{count}</b>\n\n<code>iris reports</code> — list and resolve."
    await edit_or_send(callback, text, menu_with_rows(locale, [[("⬅️ Назад", "menu:moderation")]]))
    await callback.answer()


__all__ = ["router", "ban", "unban", "mute", "unmute", "kick", "warn", "unwarn", "warns", "clear", "history"]
