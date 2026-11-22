"""ИИ-модуль: вопросы, объяснение команд, изложение обсуждения."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.types import Message

from app.commands.context import CommandContext
from app.commands.registry import CommandSpec, command
from app.container import Container
from app.core.logging import get_logger
from app.core.texts import escape_html
from app.modules.common import escape
from app.services.ai import AIUnavailable

router = Router(name="iris.ai")
log = get_logger(__name__)

MAX_PROMPT = 1500
MAX_ANSWER = 3800


def _slice(text: str) -> str:
    text = text.strip()
    return text if len(text) <= MAX_ANSWER else text[:MAX_ANSWER] + "…"


async def _ask(ctx: CommandContext, prompt: str, *, respect_chat_setting: bool = True) -> None:
    if (
        respect_chat_setting
        and ctx.settings is not None
        and not ctx.settings.ai_enabled
    ):
        await ctx.reply(ctx.t("ai_disabled"))
        return
    service = ctx.container.ai(ctx.session)
    if not service.configured:
        await ctx.reply(ctx.t("ai_unavailable"))
        return
    thinking = await ctx.reply(ctx.t("ai_thinking"))
    try:
        answer = await service.ask(prompt, chat_id=ctx.chat_id, user_id=ctx.user_id)
    except AIUnavailable as exc:
        log.warning("ИИ недоступен", extra={"error": str(exc)})
        if thinking is not None:
            try:
                await thinking.edit_text(ctx.t("ai_unavailable"))
            except Exception:  # noqa: BLE001
                pass
        return
    if thinking is not None:
        try:
            await thinking.edit_text(escape_html(_slice(answer)), reply_markup=None)
            return
        except Exception:  # noqa: BLE001
            pass
    await ctx.reply(escape_html(_slice(answer)))


@command(
    "ии",
    aliases=("ai", "ирисai"),
    module="ai",
    category="ai",
    description_ru="Спросить Ирис AI",
    description_en="Ask Iris AI",
    usage="ии как включить капчу?",
    cooldown=3,
)
async def ask_ai(ctx: CommandContext) -> None:
    prompt = ctx.args_text.strip()
    if not prompt:
        await ctx.reply(ctx.t("ai_hint"))
        return
    if len(prompt) > MAX_PROMPT:
        await ctx.reply(ctx.t("ai_too_long", limit=MAX_PROMPT))
        return
    await _ask(ctx, prompt)


@command(
    "gpt",
    aliases=("гпт", "ask", "спроси"),
    module="general",
    category="ai",
    description_ru="Задать вопрос ИИ: .gpt вопрос",
    description_en="Ask the AI: .gpt your question",
    usage="gpt как настроить капчу?",
    cooldown=2,
    examples=(".gpt кто ты?", "gpt как включить капчу", "ирис как дела?"),
)
async def gpt(ctx: CommandContext) -> None:
    prompt = ctx.args_text.strip()
    if not prompt:
        await ctx.reply(ctx.t("ai_hint"))
        return
    if len(prompt) > MAX_PROMPT:
        await ctx.reply(ctx.t("ai_too_long", limit=MAX_PROMPT))
        return
    # Явная команда работает независимо от переключателя ИИ в конкретном чате.
    await _ask(ctx, prompt, respect_chat_setting=False)


def _fallback_prompt(prompt: str, settings) -> str:
    context = []
    if settings is not None:
        context.append(
            "Настройки чата: "
            f"антифлуд={'вкл' if settings.antiflood_enabled else 'выкл'}, "
            f"антиспам={'вкл' if settings.antispam_enabled else 'выкл'}, "
            f"капча={'вкл' if settings.captcha_enabled else 'выкл'}, "
            f"приветствие={'вкл' if settings.welcome_enabled else 'выкл'}, "
            f"уровни={'вкл' if settings.levels_enabled else 'выкл'}, "
            f"экономика={'вкл' if settings.economy_enabled else 'выкл'}"
        )
    return "\n".join(context) + f"\n\nВопрос пользователя: {prompt}"


@command(
    "объясни",
    aliases=("explain",),
    module="ai",
    category="ai",
    description_ru="Объяснить команду IrisV2",
    description_en="Explain an IrisV2 command",
    usage="объясни шипперим",
    cooldown=3,
)
async def explain(ctx: CommandContext) -> None:
    name = (ctx.arg(0) or "").lstrip("!/.").casefold()
    if not name:
        await ctx.reply(ctx.t("not_enough_args", usage=ctx.spec.usage))
        return
    spec: CommandSpec | None = ctx.container.commands.get(name)
    if spec is None:
        await ctx.reply("🤔 Такой команды нет. Список: <code>команды</code>")
        return
    description = spec.description_ru if ctx.locale == "ru" else spec.description_en
    service = ctx.container.ai(ctx.session)
    if not (service.configured and (ctx.settings is None or ctx.settings.ai_enabled)):
        await ctx.reply(
            f"📖 <b>{spec.name}</b>\n\n{description}\n\n"
            f"Использование: <code>{spec.usage}</code>\n"
            + ("Примеры: " + ", ".join(f"<code>{item}</code>" for item in spec.examples) if spec.examples else "")
        )
        return
    thinking = await ctx.reply(ctx.t("ai_thinking"))
    try:
        answer = await service.explain_command(spec.name, spec.usage, description)
    except AIUnavailable:
        answer = f"{description}\n\n<code>{spec.usage}</code>"
    if thinking is not None:
        try:
            await thinking.edit_text(escape_html(_slice(answer)))
            return
        except Exception:  # noqa: BLE001
            pass
    await ctx.reply(escape_html(_slice(answer)))


@command(
    "итоги",
    aliases=("summary", "саммари"),
    module="ai",
    category="ai",
    description_ru="Краткое изложение обсуждения (нужна история ИИ)",
    description_en="Summarise the discussion (AI history required)",
    usage="итоги",
    cooldown=30,
    group_only=True,
)
async def summary(ctx: CommandContext) -> None:
    if ctx.settings is None or not ctx.settings.ai_history_enabled:
        await ctx.reply(
            "🤖 История обсуждения выключена. Включите: <code>настройки</code> → ИИ-история."
            if ctx.locale == "ru"
            else "🤖 AI history is disabled in this chat."
        )
        return
    service = ctx.container.ai(ctx.session)
    if not service.configured:
        await ctx.reply(ctx.t("ai_unavailable"))
        return
    try:
        text = await service.summarize(ctx.chat_id)
    except AIUnavailable:
        await ctx.reply(ctx.t("ai_summary_empty"))
        return
    await ctx.reply(ctx.t("ai_summary_title", text=escape_html(_slice(text))))


@router.message(F.text)
async def ai_fallback(message: Message, container: Container | None = None) -> None:
    """Отвечает, только если к боту обратились напрямую. Иначе — следующий роутер."""
    if container is None or message.from_user is None or message.from_user.is_bot:
        raise SkipHandler
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        raise SkipHandler

    bot = container.bot
    bot_id = bot.id if bot else 0
    username = (container.settings.bot_username or "").lstrip("@").casefold()
    lowered = text.casefold()

    addressed = message.chat.type == "private"
    if message.reply_to_message and message.reply_to_message.from_user:
        addressed = addressed or message.reply_to_message.from_user.id == bot_id
    if username and f"@{username}" in lowered:
        addressed = True
    triggers = [item.casefold() for item in container.settings.command_triggers]
    if any(lowered.startswith(f"{trigger} ") for trigger in triggers):
        addressed = True

    if not addressed:
        raise SkipHandler

    async with container.db.session_scope() as session:
        settings = await container.chats.settings(session, message.chat.id)
        if settings is None or not settings.ai_enabled:
            raise SkipHandler
        service = container.ai(session)
        if not service.configured:
            locale = container.locale(settings)
            await message.answer(container.texts.t(locale, "ai_unavailable"))
            return
        key = f"ai_cd:{message.chat.id}:{message.from_user.id}"
        if await container.cache.get(key):
            raise SkipHandler
        await container.cache.set(key, "1", ttl=3)
        prompt = _fallback_prompt(text[:MAX_PROMPT], settings)
        try:
            answer = await service.ask(
                prompt, chat_id=message.chat.id, user_id=message.from_user.id
            )
        except AIUnavailable:
            locale = container.locale(settings)
            await message.answer(container.texts.t(locale, "ai_unavailable"))
            return
    await message.answer(escape_html(_slice(answer)))


__all__ = ["router", "ask_ai", "explain", "summary", "ai_fallback", "escape"]
