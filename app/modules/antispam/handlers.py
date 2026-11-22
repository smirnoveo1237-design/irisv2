"""Антиспам: приветствие, CAPTCHA для новичков, фильтры слов и ссылок."""

from __future__ import annotations

import random

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from app.commands.context import CommandContext
from app.commands.registry import command
from app.container import Container
from app.core.timeutil import now_utc
from app.database.models import Filter
from app.services.moderation import FULL_PERMISSIONS
from app.ui.keyboards import back_keyboard, menu_with_rows
from app.ui.render import answer_alert, edit_or_send

router = Router(name="iris.antispam")

MAX_CAPTCHA_ATTEMPTS = 3


def captcha_keyboard(chat_id: int, user_id: int, answer: int) -> InlineKeyboardMarkup:
    options = {answer}
    while len(options) < 4:
        options.add(max(2, answer + random.randint(-4, 4)))
    values = sorted(options)
    random.shuffle(values)
    rows = []
    for index in range(0, 4, 2):
        rows.append(
            [
                InlineKeyboardButton(
                    text=str(value), callback_data=f"cap:{chat_id}:{user_id}:{value}"
                )
                for value in values[index : index + 2]
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.new_chat_members)
async def on_join(message: Message, container: Container | None = None) -> None:
    if container is None or not message.new_chat_members:
        return
    async with container.db.session_scope() as session:
        settings = await container.chats.settings(session, message.chat.id)
        if settings is None:
            return
        locale = container.locale(settings)
        members_count = await container.members(session).count(message.chat.id)

        for member in message.new_chat_members:
            if member.is_bot:
                continue
            await container.members(session).touch(
                chat_id=message.chat.id,
                user_id=member.id,
                username=member.username,
                full_name=member.full_name,
                verified=not settings.captcha_enabled,
            )

            if settings.captcha_enabled:
                answer = random.randint(3, 9) + random.randint(2, 9)
                try:
                    await container.bot.restrict_chat_member(
                        message.chat.id,
                        member.id,
                        permissions=ChatPermissions(can_send_messages=False),
                    )
                except TelegramAPIError:
                    pass
                await container.cache.set(
                    f"captcha:{message.chat.id}:{member.id}", str(answer), ttl=settings.captcha_timeout
                )
                await container.cache.set(
                    f"captcha_tries:{message.chat.id}:{member.id}", "0", ttl=settings.captcha_timeout
                )
                await container.scheduler.schedule(
                    session,
                    chat_id=message.chat.id,
                    kind="captcha_kick",
                    run_at=now_utc() + __import__("datetime").timedelta(
                        seconds=settings.captcha_timeout
                    ),
                    payload={"chat_id": message.chat.id, "user_id": member.id},
                )
                text = container.texts.t(
                    locale,
                    "captcha_join",
                    name=f'<a href="tg://user?id={member.id}">{member.full_name}</a>',
                    chat=message.chat.title or "",
                    answer=answer,
                    minutes=max(1, settings.captcha_timeout // 60),
                )
                await message.answer(
                    text, reply_markup=captcha_keyboard(message.chat.id, member.id, answer)
                )
                continue

            if settings.welcome_enabled:
                template = settings.welcome_text or container.texts.t(locale, "welcome_default")
                text = template.format(
                    user=f'<a href="tg://user?id={member.id}">{member.full_name}</a>',
                    chat=message.chat.title or "",
                    count=members_count + 1,
                )
                await message.answer(text)


@router.message(F.left_chat_member)
async def on_leave(message: Message, container: Container | None = None) -> None:
    if container is None or message.left_chat_member is None:
        return
    async with container.db.session_scope() as session:
        settings = await container.chats.settings(session, message.chat.id)
        if settings is None or not settings.goodbye_enabled:
            return
        user = message.left_chat_member
        template = settings.goodbye_text or "👋 {user} покинул чат."
        await message.answer(
            template.format(
                user=f'<a href="tg://user?id={user.id}">{user.full_name}</a>',
                chat=message.chat.title or "",
            )
        )


@router.callback_query(F.data.startswith("cap:"))
async def captcha_answer(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    try:
        _, chat_raw, user_raw, value_raw = callback.data.split(":")
        chat_id, expected_user, value = int(chat_raw), int(user_raw), int(value_raw)
    except ValueError:
        await callback.answer()
        return

    if callback.from_user.id != expected_user:
        await answer_alert(callback, "🙃 Это не ваша проверка.")
        return

    key = f"captcha:{chat_id}:{expected_user}"
    expected = await container.cache.get(key)
    tries_key = f"captcha_tries:{chat_id}:{expected_user}"
    tries = int(await container.cache.get(tries_key) or 0)

    async with container.db.session_scope() as session:
        settings = await container.chats.settings(session, chat_id)
        locale = container.locale(settings)

        if expected is None:
            await answer_alert(callback, "⌛ Время проверки истекло.")
            return

        if str(value) == expected:
            await container.cache.delete(key, tries_key)
            try:
                await container.bot.restrict_chat_member(
                    chat_id, expected_user, permissions=FULL_PERMISSIONS
                )
            except TelegramAPIError:
                pass
            await container.members(session).mark_verified(chat_id, expected_user)
            try:
                await callback.message.delete()
            except TelegramAPIError:
                pass
            await answer_alert(callback, container.texts.t(locale, "captcha_ok"))
            return

        tries += 1
        await container.cache.set(tries_key, str(tries), ttl=settings.captcha_timeout if settings else 300)
        if tries >= MAX_CAPTCHA_ATTEMPTS:
            try:
                await container.bot.ban_chat_member(chat_id, expected_user)
                await container.bot.unban_chat_member(chat_id, expected_user, only_if_banned=True)
            except TelegramAPIError:
                pass
            await container.cache.delete(key, tries_key)
            try:
                await callback.message.delete()
            except TelegramAPIError:
                pass
            await answer_alert(callback, "🚫 Проверка не пройдена.")
            return

        await answer_alert(
            callback,
            container.texts.t(locale, "captcha_fail") + f" ({MAX_CAPTCHA_ATTEMPTS - tries})",
        )


# --- Фильтры --------------------------------------------------------------
@command(
    "фильтр",
    aliases=("filter",),
    module="antispam",
    category="moderation",
    description_ru="Фильтры слов и ссылок: список, добавление, удаление",
    description_en="Word/link filters",
    usage="фильтр добавить реклама",
    permission="filters",
    group_only=True,
)
async def filters(ctx: CommandContext) -> None:
    sub = (ctx.arg(0) or "").lower()
    if sub in {"добавить", "add"} and ctx.arg(1):
        pattern = ctx.arg(1)
        action = (ctx.arg(2) or "delete").lower()
        if action not in {"delete", "mute", "warn", "ban"}:
            action = "delete"
        kind = "regex" if sub == "regex" else "word"
        item = Filter(
            chat_id=ctx.chat_id,
            kind=kind,
            pattern=pattern[:255],
            action=action,
            mute_minutes=ctx.settings.mute_minutes if ctx.settings else 60,
            created_by=ctx.user_id,
        )
        ctx.session.add(item)
        await ctx.session.flush()
        await ctx.reply(f"✅ Фильтр <b>#{item.id}</b> добавлен: <code>{pattern}</code> → {action}")
        return

    if sub in {"удалить", "delete", "del"} and ctx.arg(1) and ctx.arg(1).isdigit():
        item = await ctx.session.get(Filter, int(ctx.arg(1)))
        if item is not None and item.chat_id == ctx.chat_id:
            await ctx.session.delete(item)
            await ctx.reply("🗑️ Фильтр удалён.")
            return
        await ctx.reply("🔍 Фильтр не найден.")
        return

    items = list(
        await ctx.session.scalars(
            select(Filter).where(Filter.chat_id == ctx.chat_id).order_by(Filter.id)
        )
    )
    stop_words = ", ".join(ctx.settings.stop_words or []) if ctx.settings else ""
    lines = ["🧹 <b>Фильтры группы</b>", ""]
    for item in items:
        lines.append(
            f"#{item.id} <code>{item.pattern}</code> · {item.kind} · {item.action} · срабатываний: {item.hits}"
        )
    if not items:
        lines.append("Пока нет фильтров.")
    lines.append(f"\n🚫 Стоп-слова: {stop_words or '—'}")
    lines.append(
        "\nДобавить: <code>фильтр добавить реклама</code>\n"
        "Regex: <code>фильтр добавить (?:казино|ставки)</code> после <code>фильтр regex</code>\n"
        "Стоп-слово: <code>стопслово реклама</code> (повторно — удалить)"
    )
    await ctx.reply("\n".join(lines))


@command(
    "стопслово",
    aliases=("stopword",),
    module="antispam",
    category="moderation",
    description_ru="Добавить или убрать стоп-слово",
    description_en="Add or remove a stop word",
    usage="стопслово реклама",
    permission="filters",
    group_only=True,
)
async def stop_word(ctx: CommandContext) -> None:
    word = ctx.arg(0)
    if not word:
        await ctx.reply(ctx.t("not_enough_args", usage=ctx.spec.usage))
        return
    words = list(ctx.settings.stop_words or []) if ctx.settings else []
    lowered = [item.casefold() for item in words]
    if word.casefold() in lowered:
        words = [item for item in words if item.casefold() != word.casefold()]
        message = f"🗑️ Стоп-слово «{word}» удалено."
    else:
        words.append(word)
        message = f"✅ Стоп-слово «{word}» добавлено."
    await ctx.container.chats.update(ctx.session, ctx.chat_id, stop_words=words)
    await ctx.reply(message)


@router.callback_query(F.data == "anti:panel")
async def cb_panel(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.message is None:
        await callback.answer()
        return
    async with container.db.session_scope() as session:
        settings = await container.chats.settings(session, callback.message.chat.id)
        locale = container.locale(settings)
    text = (
        "🧹 <b>Антиспам</b>\n\n"
        f"Антифлуд: {'✅' if settings and settings.antiflood_enabled else '❌'} "
        f"({settings.flood_limit if settings else 7} сообщений / {settings.flood_window if settings else 10} с)\n"
        f"Антиспам: {'✅' if settings and settings.antispam_enabled else '❌'}\n"
        f"Антиссылки: {'✅' if settings and settings.antilink_enabled else '❌'}\n"
        f"Антифишинг: {'✅' if settings and settings.antiphishing_enabled else '❌'}\n"
        f"CAPTCHA: {'✅' if settings and settings.captcha_enabled else '❌'}"
    )
    await edit_or_send(callback, text, menu_with_rows(locale, [[("⚙️ Настройки", "menu:settings")]]))
    await callback.answer()


__all__ = ["router", "on_join", "on_leave", "captcha_answer", "filters", "stop_word", "back_keyboard"]
