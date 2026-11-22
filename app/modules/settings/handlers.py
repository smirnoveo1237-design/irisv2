"""Настройки группы: панель, переключатели, префиксы, язык, приветствие."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.commands.context import CommandContext
from app.commands.registry import command
from app.container import Container
from app.core.texts import texts
from app.database.models import ChatSettings
from app.ui.keyboards import back_keyboard, menu_with_rows
from app.ui.render import answer_alert, edit_or_send

router = Router(name="iris.settings")

TOGGLES = {
    "antiflood_enabled": "antiflood_enabled",
    "antispam_enabled": "antispam_enabled",
    "antilink_enabled": "antilink_enabled",
    "captcha_enabled": "captcha_enabled",
    "welcome_enabled": "welcome_enabled",
    "levels_enabled": "levels_enabled",
    "economy_enabled": "economy_enabled",
    "games_enabled": "games_enabled",
    "ai_enabled": "ai_enabled",
    "ai_history_enabled": "ai_history_enabled",
    "bare_commands": "bare_commands",
}


def _mark(value: bool) -> str:
    return "✅" if value else "❌"


def build_settings_view(settings: ChatSettings, locale: str) -> tuple[str, InlineKeyboardMarkup]:
    text = texts.t(locale, "settings_title") + "\n\n" + texts.t(
        locale,
        "settings_body",
        antiflood=_mark(settings.antiflood_enabled),
        antispam=_mark(settings.antispam_enabled),
        antilink=_mark(settings.antilink_enabled),
        captcha=_mark(settings.captcha_enabled),
        welcome=_mark(settings.welcome_enabled),
        levels=_mark(settings.levels_enabled),
        economy=_mark(settings.economy_enabled),
        games=_mark(settings.games_enabled),
        ai=_mark(settings.ai_enabled),
        lang=settings.locale,
        prefixes=" ".join(settings.command_prefixes or []) or "—",
        triggers=" ".join(settings.command_triggers or []),
        max_warnings=settings.max_warnings,
        mute=settings.mute_minutes,
    )
    text += "\n" + texts.t(locale, "settings_ship_cooldown", seconds=settings.ship_cooldown)
    rows: list[list[tuple[str, str]]] = [
        [
            (f"{_mark(settings.antiflood_enabled)} Антифлуд", "set:t:antiflood_enabled"),
            (f"{_mark(settings.antispam_enabled)} Антиспам", "set:t:antispam_enabled"),
        ],
        [
            (f"{_mark(settings.antilink_enabled)} Антиссылки", "set:t:antilink_enabled"),
            (f"{_mark(settings.captcha_enabled)} CAPTCHA", "set:t:captcha_enabled"),
        ],
        [
            (f"{_mark(settings.welcome_enabled)} Приветствие", "set:t:welcome_enabled"),
            (f"{_mark(settings.levels_enabled)} Уровни", "set:t:levels_enabled"),
        ],
        [
            (f"{_mark(settings.economy_enabled)} Экономика", "set:t:economy_enabled"),
            (f"{_mark(settings.games_enabled)} Игры", "set:t:games_enabled"),
        ],
        [
            (f"{_mark(settings.ai_enabled)} ИИ", "set:t:ai_enabled"),
            (f"{_mark(settings.ai_history_enabled)} История ИИ", "set:t:ai_history_enabled"),
        ],
        [
            (f"{_mark(settings.bare_commands)} Команды без префикса", "set:t:bare_commands"),
            ("🌐 Язык: " + ("RU" if settings.locale == "ru" else "EN"), "set:locale"),
        ],
        [("✍️ Текст приветствия", "set:welcome"), ("⌨️ Префиксы", "set:prefixes")],
    ]
    return text, menu_with_rows(locale, rows)


@command(
    "настройки",
    aliases=("settings", "конфиг"),
    module="settings",
    category="general",
    description_ru="Панель настроек группы",
    description_en="Group settings panel",
    usage="настройки",
    permission="settings",
    group_only=True,
    cooldown=2,
)
async def settings_panel(ctx: CommandContext) -> None:
    if ctx.settings is None:
        await ctx.reply(ctx.t("error"))
        return
    text, keyboard = build_settings_view(ctx.settings, ctx.locale)
    await ctx.reply(text, keyboard=keyboard)


@router.callback_query(F.data == "menu:settings")
async def show_settings(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    chat = callback.message.chat
    async with container.db.session_scope() as session:
        _chat_row, settings = await container.chats.ensure(
            session,
            chat_id=chat.id,
            title=chat.title,
            chat_type=chat.type,
            username=chat.username,
        )
        locale = container.locale(settings)
        if chat.type == "private":
            await answer_alert(callback, texts.t(locale, "menu_private_note"))
            return
        if not await container.permissions(session).has_permission(
            chat.id, callback.from_user.id, "settings"
        ):
            await answer_alert(callback, texts.t(locale, "no_permission"))
            return
        text, keyboard = build_settings_view(settings, locale)
    await edit_or_send(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("set:t:"))
async def toggle_setting(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    field = callback.data.split(":", 2)[2]
    chat_id = callback.message.chat.id
    async with container.db.session_scope() as session:
        settings = await container.chats.settings(session, chat_id)
        locale = container.locale(settings)
        if not await container.permissions(session).has_permission(
            chat_id, callback.from_user.id, "settings"
        ):
            await answer_alert(callback, texts.t(locale, "no_permission"))
            return
        if field not in TOGGLES or settings is None:
            await answer_alert(callback, texts.t(locale, "error"))
            return
        new_value = not bool(getattr(settings, field))
        await container.chats.update(session, chat_id, **{field: new_value})
        settings = await container.chats.settings(session, chat_id)
        assert settings is not None
        text, keyboard = build_settings_view(settings, locale)
    await edit_or_send(callback, text, keyboard)
    await callback.answer("✅" if new_value else "❌")


@router.callback_query(F.data == "set:locale")
async def toggle_locale(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    chat_id = callback.message.chat.id
    async with container.db.session_scope() as session:
        settings = await container.chats.settings(session, chat_id)
        locale = container.locale(settings)
        if not await container.permissions(session).has_permission(
            chat_id, callback.from_user.id, "settings"
        ):
            await answer_alert(callback, texts.t(locale, "no_permission"))
            return
        new_locale = "en" if (settings and settings.locale == "ru") else "ru"
        await container.chats.update(session, chat_id, locale=new_locale)
        settings = await container.chats.settings(session, chat_id)
        assert settings is not None
        text, keyboard = build_settings_view(settings, new_locale)
    await edit_or_send(callback, text, keyboard)
    await callback.answer("EN" if new_locale == "en" else "RU")


@router.callback_query(F.data == "set:welcome")
async def welcome_help(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.message is None:
        await callback.answer()
        return
    async with container.db.session_scope() as session:
        settings = await container.chats.settings(session, callback.message.chat.id)
        locale = container.locale(settings)
    await edit_or_send(callback, texts.t(locale, "settings_welcome_help"), back_keyboard(locale, "menu:settings"))
    await callback.answer()


@router.callback_query(F.data == "set:prefixes")
async def prefixes_help(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.message is None:
        await callback.answer()
        return
    async with container.db.session_scope() as session:
        settings = await container.chats.settings(session, callback.message.chat.id)
        locale = container.locale(settings)
        current = " ".join(settings.command_prefixes) if settings else ""
    text = (
        f"⌨️ Текущие префиксы: <code>{current}</code>\n\n"
        "Изменить: <code>ирис префиксы ! . $</code>\n"
        "Пустой список = только вызовы через «ирис»."
    )
    await edit_or_send(callback, text, back_keyboard(locale, "menu:settings"))
    await callback.answer()


@command(
    "префиксы",
    aliases=("prefixes",),
    module="settings",
    category="general",
    description_ru="Настроить префиксы команд в группе",
    description_en="Configure command prefixes",
    usage="префиксы ! . $",
    permission="settings",
    group_only=True,
)
async def set_prefixes(ctx: CommandContext) -> None:
    if not ctx.args:
        current = " ".join(ctx.settings.command_prefixes) if ctx.settings else ""
        await ctx.reply(
            f"⌨️ Префиксы: <code>{current}</code>\n\n"
            f"Изменить: <code>{ctx.spec.usage}</code> (без пробелов-разделителей)"
        )
        return
    prefixes = [part for part in ctx.args if len(part) <= 3]
    if not prefixes:
        await ctx.reply(ctx.t("settings_prefix_bad"))
        return
    await ctx.container.chats.update(ctx.session, ctx.chat_id, command_prefixes=prefixes)
    await ctx.reply(ctx.t("settings_prefix_set", prefixes=" ".join(prefixes)))


@command(
    "язык",
    aliases=("language", "lang"),
    module="settings",
    category="general",
    description_ru="Язык интерфейса группы: ru или en",
    description_en="Chat locale: ru or en",
    usage="язык ru",
    permission="settings",
    group_only=True,
)
async def set_locale(ctx: CommandContext) -> None:
    value = (ctx.arg(0) or "").lower()
    if value not in {"ru", "en"}:
        await ctx.reply(ctx.t("not_enough_args", usage=ctx.spec.usage))
        return
    await ctx.container.chats.update(ctx.session, ctx.chat_id, locale=value)
    await ctx.reply(ctx.t("settings_locale_set", lang=value))


@command(
    "приветствие",
    aliases=("welcome",),
    module="settings",
    category="general",
    description_ru="Текст приветствия новых участников",
    description_en="Welcome message text",
    usage="приветствие 👋 {user}, добро пожаловать в {chat}!",
    permission="settings",
    group_only=True,
)
async def set_welcome(ctx: CommandContext) -> None:
    text = ctx.args_text.strip()
    if not text:
        current = (ctx.settings.welcome_text if ctx.settings else None) or ctx.t("welcome_default")
        await ctx.reply(
            f"✍️ Текущее приветствие:\n\n{current}\n\n"
            f"Изменить: <code>{ctx.spec.usage}</code>\n"
            "Переменные: {user}, {chat}, {count}. Выключить: <code>приветствие выкл</code>"
        )
        return
    if text.lower() in {"выкл", "off", "нет"}:
        await ctx.container.chats.update(ctx.session, ctx.chat_id, welcome_enabled=False)
        await ctx.reply(ctx.t("settings_saved"))
        return
    if len(text) > 1500:
        await ctx.reply("✍️ Слишком длинный текст (максимум 1500 символов).")
        return
    await ctx.container.chats.update(
        ctx.session, ctx.chat_id, welcome_text=text, welcome_enabled=True
    )
    await ctx.reply(ctx.t("settings_welcome_set"))


@command(
    "капча",
    aliases=("captcha",),
    module="settings",
    category="general",
    description_ru="Включить или выключить CAPTCHA для новых участников",
    description_en="Toggle CAPTCHA for new members",
    usage="капча вкл",
    permission="settings",
    group_only=True,
)
async def captcha_setting(ctx: CommandContext) -> None:
    value = (ctx.arg(0) or "").lower()
    enabled = value in {"вкл", "on", "1", "да", "yes"}
    if value in {"выкл", "off", "0", "нет", "no"}:
        enabled = False
    elif not enabled:
        await ctx.reply(ctx.t("not_enough_args", usage="капча вкл"))
        return
    await ctx.container.chats.update(ctx.session, ctx.chat_id, captcha_enabled=enabled)
    await ctx.reply(ctx.t("settings_saved"))


@command(
    "антифлуд",
    aliases=("antiflood",),
    module="settings",
    category="general",
    description_ru="Включить или выключить антифлуд",
    description_en="Toggle antiflood",
    usage="антифлуд вкл",
    permission="settings",
    group_only=True,
)
async def antiflood_setting(ctx: CommandContext) -> None:
    value = (ctx.arg(0) or "").lower()
    if value not in {"вкл", "on", "выкл", "off"}:
        await ctx.reply(ctx.t("not_enough_args", usage="антифлуд вкл"))
        return
    enabled = value in {"вкл", "on"}
    await ctx.container.chats.update(ctx.session, ctx.chat_id, antiflood_enabled=enabled)
    await ctx.reply(ctx.t("settings_saved"))


__all__ = ["router", "settings_panel", "build_settings_view", "InlineKeyboardButton"]
