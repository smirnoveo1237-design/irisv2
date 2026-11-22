"""Меню IrisV2 и обзорные экраны."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.commands.context import CommandContext
from app.commands.registry import command
from app.container import Container
from app.core.texts import texts
from app.core.timeutil import format_datetime, now_utc
from app.modules.common import escape, mention, progress_bar
from app.services.levels import LevelService
from app.services.profiles import ProfileService
from app.ui.keyboards import back_keyboard, main_menu, menu_with_rows

router = Router(name="iris.menu")


def _locale(ctx: CommandContext) -> str:
    return ctx.locale


@command(
    "меню",
    aliases=("menu", "старт", "start", "помощь", "help", "ирис"),
    module="menu",
    category="general",
    description_ru="Главное меню и список команд",
    description_en="Main menu and command list",
    usage="меню",
    examples=("меню", "ирис", "!помощь"),
)
async def menu_command(ctx: CommandContext) -> None:
    locale = _locale(ctx)
    text = ctx.t("menu_title")
    if ctx.is_group:
        text += "\n\n" + _commands_brief(ctx)
    await ctx.reply(text, keyboard=main_menu(locale))


def _commands_brief(ctx: CommandContext) -> str:
    groups: dict[str, list[str]] = {}
    for spec in ctx.container.commands.all():
        if spec.hidden or spec.module in {"menu"}:
            continue
        groups.setdefault(spec.category, []).append(spec.name)
    lines = []
    titles = {
        "general": "⚙️ Общее",
        "moderation": "🛡️ Модерация",
        "economy": "💰 Экономика",
        "profiles": "👤 Профили",
        "social": "💞 Социальное",
        "games": "🎮 Игры",
        "fun": "🔮 Развлечения",
        "analytics": "📊 Аналитика",
        "automation": "⚙️ Автоматизация",
        "ai": "🤖 ИИ",
        "support": "📩 Поддержка",
    }
    for category, names in sorted(groups.items()):
        title = titles.get(category, category)
        lines.append(f"{title}: " + ", ".join(f"<code>{name}</code>" for name in sorted(names)[:14]))
    return "\n".join(lines[:8])


@command(
    "команды",
    aliases=("commands", "список"),
    module="menu",
    category="general",
    description_ru="Полный список команд по категориям",
    description_en="Full command list by category",
    usage="команды",
    cooldown=3,
)
async def commands_list(ctx: CommandContext) -> None:
    locale = ctx.locale
    by_category = ctx.container.commands.by_category()
    titles = {
        "general": "⚙️ Общее",
        "moderation": "🛡️ Модерация",
        "economy": "💰 Экономика",
        "profiles": "👤 Профили",
        "social": "💞 Социальное",
        "games": "🎮 Игры",
        "fun": "🔮 Развлечения",
        "analytics": "📊 Аналитика",
        "automation": "⚙️ Автоматизация",
        "ai": "🤖 ИИ",
        "support": "📩 Поддержка",
    }
    blocks: list[str] = ["📚 <b>Команды IrisV2</b>"]
    for category, specs in by_category.items():
        visible = [spec for spec in specs if not spec.hidden]
        if not visible:
            continue
        lines = [titles.get(category, f"• {category}")]
        for spec in visible:
            description = spec.description_ru if locale == "ru" else spec.description_en
            lines.append(f"/{spec.name} — {description or spec.usage}")
        blocks.append("\n".join(lines))
    blocks.append(
        "💡 Команды работают без «/»: <code>профиль</code>, <code>!профиль</code>, "
        "<code>.профиль</code>, <code>ирис профиль</code>."
        if locale == "ru"
        else "💡 Commands work without “/”: <code>profile</code>, <code>!profile</code>, <code>iris profile</code>."
    )
    text = "\n\n".join(blocks)
    if len(text) > 3800:
        text = text[:3800] + "…"
    await ctx.reply(text, keyboard=main_menu(locale))


@router.callback_query(F.data == "menu:main")
async def show_main(callback: CallbackQuery, container: Container | None = None) -> None:
    locale = "ru"
    if callback.message is not None and container is not None:
        async with container.db.session_scope() as session:
            settings = await container.chats.settings(session, callback.message.chat.id)
            locale = container.locale(settings)
    if callback.message:
        try:
            await callback.message.edit_text(
                texts.t(locale, "menu_title"), reply_markup=main_menu(locale)
            )
        except Exception:  # noqa: BLE001
            await callback.message.answer(texts.t(locale, "menu_title"), reply_markup=main_menu(locale))
    await callback.answer()


@router.callback_query(F.data == "menu:close")
async def close_menu(callback: CallbackQuery) -> None:
    if callback.message:
        try:
            await callback.message.delete()
        except Exception:  # noqa: BLE001
            pass
    await callback.answer()


@router.callback_query(F.data == "menu:profile")
async def show_profile(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    chat_id = callback.message.chat.id
    async with container.db.session_scope() as session:
        settings = await container.chats.settings(session, chat_id)
        locale = container.locale(settings)
        card = await ProfileService(session, container).card(chat_id, callback.from_user.id, locale)
    keyboard = menu_with_rows(
        locale,
        [
            [("🎒 Инвентарь", "eco:inventory"), ("💎 Репутация", "profile:rep_top")],
        ],
    )
    await _edit(callback, f"👤 <b>{'Профиль' if locale == 'ru' else 'Profile'}</b>\n\n{card}", keyboard)
    await callback.answer()


@router.callback_query(F.data == "menu:economy")
async def show_economy(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    chat_id = callback.message.chat.id
    async with container.db.session_scope() as session:
        settings = await container.chats.settings(session, chat_id)
        locale = container.locale(settings)
        wallet = await container.economy(session).ensure_wallet(chat_id, callback.from_user.id)
        text = texts.t(
            locale,
            "balance",
            name=escape(callback.from_user.full_name),
            balance=wallet.balance,
            currency=texts.t(locale, "currency"),
            earned=wallet.total_earned,
            spent=wallet.total_spent,
        )
    keyboard = menu_with_rows(
        locale,
        [
            [("🎁 Бонус", "eco:daily"), ("🛍️ Магазин", "eco:shop")],
            [("🧾 История", "eco:history"), ("🎒 Инвентарь", "eco:inventory")],
        ],
    )
    await _edit(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "menu:ratings")
async def show_ratings(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.message is None:
        await callback.answer()
        return
    chat_id = callback.message.chat.id
    async with container.db.session_scope() as session:
        settings = await container.chats.settings(session, chat_id)
        locale = container.locale(settings)
        levels = await LevelService(session, container).top(chat_id, 10)
        lines = []
        for index, row in enumerate(levels, start=1):
            member = await container.members(session).get(chat_id, row.user_id)
            name = member.full_name if member else str(row.user_id)
            lines.append(f"{index}. {mention(row.user_id, name)} — <b>{row.level}</b> ур., {row.xp} XP")
        text = f"🏆 <b>{'Рейтинг' if locale == 'ru' else 'Leaderboard'}</b>\n\n" + (
            "\n".join(lines) if lines else texts.t(locale, "leaderboard_empty")
        )
    keyboard = menu_with_rows(
        locale,
        [
            [("💰 Богачи", "eco:top")],
            [("💎 Репутация", "profile:rep_top")],
        ],
    )
    await _edit(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "menu:stats")
async def show_stats(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.message is None:
        await callback.answer()
        return
    chat_id = callback.message.chat.id
    async with container.db.session_scope() as session:
        settings = await container.chats.settings(session, chat_id)
        locale = container.locale(settings)
        summary = await container.analytics(session).summary(chat_id)
        text = texts.t(locale, "stats_title") + "\n\n" + texts.t(locale, "stats_body", **summary)
    await _edit(callback, text, back_keyboard(locale))
    await callback.answer()


@router.callback_query(F.data == "menu:moderation")
async def show_moderation(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    chat_id = callback.message.chat.id
    async with container.db.session_scope() as session:
        settings = await container.chats.settings(session, chat_id)
        locale = container.locale(settings)
        allowed = await container.permissions(session).is_chat_admin(chat_id, callback.from_user.id)
    if not allowed:
        await callback.answer(texts.t(locale, "no_permission"), show_alert=True)
        return
    text = (
        "🛡️ <b>Модерация</b>\n\n"
        "Наказания (ответом на сообщение или с @username):\n"
        "<code>бан @user 1д причина</code>\n<code>мут @user 30м спам</code>\n"
        "<code>кик @user</code>\n<code>пред @user причина</code>\n"
        "<code>снятьпред @user</code>\n<code>преды @user</code>\n"
        "<code>очистить 20</code> — удалить последние сообщения\n"
        "<code>история @user</code> — история наказаний\n\n"
        "Автоматика: <code>фильтр слово привет</code>, <code>антифлуд вкл</code>."
    )
    if locale.startswith("en"):
        text = (
            "🛡️ <b>Moderation</b>\n\n"
            "Punishments (reply or @username):\n"
            "<code>ban @user 1d reason</code>\n<code>mute @user 30m spam</code>\n"
            "<code>kick @user</code>\n<code>warn @user reason</code>\n"
            "<code>unwarn @user</code>\n<code>warns @user</code>\n"
            "<code>clear 20</code> — delete recent messages\n"
            "<code>history @user</code> — punishment history"
        )
    keyboard = menu_with_rows(
        locale,
        [
            [("⚠️ Предупреждения", "mod:warns_help")],
            [("🚨 Открытые жалобы", "mod:reports")],
        ],
    )
    await _edit(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "menu:games")
async def show_games(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.message is None:
        await callback.answer()
        return
    chat_id = callback.message.chat.id
    async with container.db.session_scope() as session:
        settings = await container.chats.settings(session, chat_id)
        locale = container.locale(settings)
    text = (
        "🎮 <b>Развлечения</b>\n\n"
        "<code>викторина</code> — вопрос с вариантами\n"
        "<code>загадка</code> — загадка с подсказкой\n"
        "<code>угадай</code> — угадать число 1–100\n"
        "<code>кнб</code> — камень, ножницы, бумага\n"
        "<code>дуэль @user 50</code> — дуэль на Ириски\n"
        "<code>квесты</code> — ежедневные задания\n"
        "<code>турнир</code> — турнир недели\n\n"
        "💘 <code>шипперим</code> · 🔮 <code>кто самый смешной</code>"
    )
    if locale.startswith("en"):
        text = (
            "🎮 <b>Games</b>\n\n"
            "<code>quiz</code> · <code>riddle</code> · <code>guess</code>\n"
            "<code>rps</code> · <code>duel @user 50</code>\n"
            "<code>quests</code> · <code>tournament</code>\n\n"
            "💘 <code>ship</code> · 🔮 <code>who is the funniest</code>"
        )
    await _edit(callback, text, back_keyboard(locale))
    await callback.answer()


@router.callback_query(F.data == "menu:ai")
async def show_ai(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.message is None:
        await callback.answer()
        return
    async with container.db.session_scope() as session:
        settings = await container.chats.settings(session, callback.message.chat.id)
        locale = container.locale(settings)
    await _edit(callback, texts.t(locale, "ai_title") + "\n\n" + texts.t(locale, "ai_hint"), back_keyboard(locale))
    await callback.answer()


@router.callback_query(F.data == "menu:support")
async def show_support(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.message is None:
        await callback.answer()
        return
    async with container.db.session_scope() as session:
        settings = await container.chats.settings(session, callback.message.chat.id)
        locale = container.locale(settings)
    await _edit(callback, texts.t(locale, "support_title") + "\n\n" + texts.t(locale, "support_hint"), back_keyboard(locale))
    await callback.answer()


@router.callback_query(F.data.startswith("menu:noop"))
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()


async def _edit(callback: CallbackQuery, text: str, keyboard) -> None:
    if callback.message is None:
        return
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, disable_web_page_preview=True)
    except Exception:  # noqa: BLE001 - «message is not modified» и права
        try:
            await callback.message.answer(text, reply_markup=keyboard, disable_web_page_preview=True)
        except Exception:  # noqa: BLE001
            pass


__all__ = ["router", "menu_command", "commands_list", "progress_bar", "format_datetime", "now_utc", "Message"]
