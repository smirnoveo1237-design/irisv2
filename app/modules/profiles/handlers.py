"""Профили, описание и репутация."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.commands.context import CommandContext
from app.commands.registry import command
from app.container import Container
from app.core.texts import texts
from app.modules.common import mention
from app.services.profiles import BIO_LIMIT, ProfileService
from app.ui.keyboards import back_keyboard, menu_with_rows
from app.ui.render import answer_alert, edit_or_send

router = Router(name="iris.profiles")


def _target_from_args(ctx: CommandContext):
    return ctx.args[0] if ctx.args else None


@command(
    "профиль",
    aliases=("profile", "me"),
    module="profiles",
    category="profiles",
    description_ru="Ваш профиль: уровень, опыт, баланс, репутация",
    description_en="Your profile: level, XP, balance, reputation",
    usage="профиль",
    cooldown=2,
    examples=("профиль", "!профиль", ".профиль", "ирис профиль"),
)
async def profile(ctx: CommandContext) -> None:
    card = await ProfileService(ctx.session, ctx.container).card(ctx.chat_id, ctx.user_id, ctx.locale)
    keyboard = menu_with_rows(
        ctx.locale,
        [
            [("🎒 Инвентарь", "eco:inventory"), ("💎 Репутация", "profile:rep_top")],
        ],
    )
    await ctx.reply(ctx.t("profile_title") + "\n\n" + card, keyboard=keyboard)


@command(
    "био",
    aliases=("bio", "описание"),
    module="profiles",
    category="profiles",
    description_ru="Изменить описание профиля",
    description_en="Change your profile bio",
    usage="био Люблю котиков и Python",
    cooldown=3,
)
async def bio(ctx: CommandContext) -> None:
    text = ctx.args_text.strip()
    if not text:
        current = await ProfileService(ctx.session, ctx.container).bio_of(ctx.user_id)
        await ctx.reply(
            f"📝 {'Ваше описание' if ctx.locale == 'ru' else 'Your bio'}: "
            f"{current or '—'}\n\n<code>{ctx.spec.usage}</code>"
        )
        return
    if len(text) > BIO_LIMIT:
        await ctx.reply(ctx.t("profile_bio_too_long", limit=BIO_LIMIT))
        return
    await ProfileService(ctx.session, ctx.container).set_bio(ctx.user_id, text)
    await ctx.reply(ctx.t("profile_bio_set"))


@command(
    "реп",
    aliases=("rep", "репутация"),
    module="profiles",
    category="profiles",
    description_ru="Повысить репутацию участника (раз в 24 часа)",
    description_en="Give reputation to a member (once per 24h)",
    usage="реп @username",
    cooldown=2,
)
async def reputation(ctx: CommandContext) -> None:
    target = await ctx.resolve_target()
    if target is None or not target.user_id:
        await ctx.reply(ctx.t("no_target"))
        return
    if target.user_id == ctx.user_id:
        await ctx.reply(ctx.t("reputation_self"))
        return
    service = ProfileService(ctx.session, ctx.container)
    result = await service.give_reputation(ctx.chat_id, ctx.user_id, target.user_id)
    if result is False:
        await ctx.reply(ctx.t("reputation_cooldown"))
        return
    await ctx.reply(
        ctx.t("reputation_given", target=mention(target.user_id, target.display), value=result)
    )


@router.callback_query(F.data == "profile:rep_top")
async def cb_rep_top(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.message is None:
        await callback.answer()
        return
    async with container.db.session_scope() as session:
        settings = await container.chats.settings(session, callback.message.chat.id)
        locale = container.locale(settings)
        top = await ProfileService(session, container).reputation_top(10)
    lines = []
    for index, (profile, user) in enumerate(top, start=1):
        name = user.display_name if user else str(profile.user_id)
        lines.append(f"{index}. {mention(profile.user_id, name)} — <b>{profile.reputation}</b>")
    text = f"💎 <b>{'Топ по репутации' if locale == 'ru' else 'Reputation top'}</b>\n\n" + (
        "\n".join(lines) if lines else texts.t(locale, "leaderboard_empty")
    )
    await edit_or_send(callback, text, back_keyboard(locale))
    await callback.answer()


@router.callback_query(F.data.startswith("profile:level"))
async def cb_level(callback: CallbackQuery) -> None:
    await answer_alert(callback, "Уровень растёт за сообщения: +5 XP за сообщение (раз в минуту).")


__all__ = ["router", "profile", "bio", "reputation"]
