"""Социальные функции: друзья, браки, семьи, питомцы, подарки."""

from __future__ import annotations

import random

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import and_, or_, select

from app.commands.context import CommandContext
from app.commands.registry import command
from app.container import Container
from app.core.texts import texts
from app.core.timeutil import as_utc, format_datetime, now_utc
from app.database.models import (
    Family,
    FamilyMember,
    Friendship,
    Gift,
    Marriage,
    Pet,
    User,
)
from app.modules.common import escape, mention
from app.services.economy import EconomyError, InsufficientFunds
from app.ui.keyboards import back_keyboard, menu_with_rows
from app.ui.render import answer_alert, edit_or_send

router = Router(name="iris.social")

PET_PRICE = 300
PET_FOOD_PRICE = 20
GIFT_PRICE = 10
PET_SPECIES = {
    "кот": ("🐱", "кот"),
    "cat": ("🐱", "кот"),
    "пёс": ("🐶", "пёс"),
    "пес": ("🐶", "пёс"),
    "dog": ("🐶", "пёс"),
    "дракон": ("🐲", "дракон"),
    "dragon": ("🐲", "дракон"),
    "лиса": ("🦊", "лиса"),
    "fox": ("🦊", "лиса"),
}


async def _accepted_friends(session, chat_id: int, user_id: int) -> list[Friendship]:
    return list(
        await session.scalars(
            select(Friendship).where(
                Friendship.chat_id == chat_id,
                Friendship.status == "accepted",
                or_(
                    Friendship.requester_id == user_id,
                    Friendship.addressee_id == user_id,
                ),
            )
        )
    )


@command(
    "друг",
    aliases=("friend", "друзья"),
    module="social",
    category="social",
    description_ru="Добавить друга или показать список друзей",
    description_en="Add a friend or list friends",
    usage="друг @username",
    cooldown=3,
)
async def friend(ctx: CommandContext) -> None:
    target = await ctx.resolve_target()
    if target is None or not target.user_id:
        rows = await _accepted_friends(ctx.session, ctx.chat_id, ctx.user_id)
        if not rows:
            await ctx.reply(ctx.t("friends_empty"))
            return
        names = []
        for row in rows:
            other = row.addressee_id if row.requester_id == ctx.user_id else row.requester_id
            member = await ctx.members.get(ctx.chat_id, other)
            names.append("• " + mention(other, member.full_name if member else None))
        await ctx.reply(ctx.t("friends_list", items="\n".join(names)))
        return

    if target.user_id == ctx.user_id:
        await ctx.reply(ctx.t("friend_self"))
        return

    existing = await ctx.session.scalar(
        select(Friendship).where(
            Friendship.chat_id == ctx.chat_id,
            or_(
                and_(
                    Friendship.requester_id == ctx.user_id,
                    Friendship.addressee_id == target.user_id,
                ),
                and_(
                    Friendship.requester_id == target.user_id,
                    Friendship.addressee_id == ctx.user_id,
                ),
            ),
        )
    )
    if existing is not None and existing.status == "accepted":
        await ctx.reply(ctx.t("friend_exists"))
        return
    if existing is not None and existing.status == "pending":
        await ctx.reply("⏳ Заявка уже отправлена и ждёт ответа.")
        return

    row = Friendship(
        chat_id=ctx.chat_id,
        requester_id=ctx.user_id,
        addressee_id=target.user_id,
        status="pending",
    )
    ctx.session.add(row)
    await ctx.session.flush()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Принять", callback_data=f"friend:a:{row.id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"friend:d:{row.id}"),
            ]
        ]
    )
    await ctx.reply(
        f"🤝 {mention(ctx.user_id)} предлагает дружбу {mention(target.user_id, target.display)}.",
        keyboard=keyboard,
    )


@router.callback_query(F.data.startswith("friend:"))
async def friend_callback(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    _, action, raw_id = callback.data.split(":")
    async with container.db.session_scope() as session:
        row = await session.get(Friendship, int(raw_id))
        settings = await container.chats.settings(session, callback.message.chat.id)
        locale = container.locale(settings)
        if row is None or row.status != "pending":
            await answer_alert(callback, "⌛ Заявка уже неактуальна.")
            return
        if row.addressee_id != callback.from_user.id:
            await answer_alert(callback, "🙃 Ответить может только адресат заявки.")
            return
        if action == "a":
            row.status = "accepted"
            text = texts.t(locale, "friend_accepted", name=callback.from_user.full_name)
            try:
                await container.bot.send_message(
                    row.requester_id,
                    texts.t(locale, "friend_accepted", name=callback.from_user.full_name),
                )
            except TelegramAPIError:
                pass
        else:
            row.status = "declined"
            text = texts.t(locale, "friend_declined")
    await edit_or_send(callback, text, None)
    await callback.answer()


# --- Брак -----------------------------------------------------------------
@command(
    "брак",
    aliases=("marry", "жениться", "выйти"),
    module="social",
    category="social",
    description_ru="Предложить брак участнику",
    description_en="Propose marriage",
    usage="брак @username",
    cooldown=5,
    group_only=True,
)
async def marry(ctx: CommandContext) -> None:
    target = await ctx.resolve_target()
    if target is None or not target.user_id:
        # Без аргумента — показать текущие отношения.
        await couple(ctx)
        return
    if target.user_id == ctx.user_id:
        await ctx.reply(ctx.t("mod_self"))
        return
    active = await ctx.session.scalar(
        select(Marriage).where(
            Marriage.chat_id == ctx.chat_id,
            Marriage.status == "active",
            or_(
                Marriage.user1_id.in_([ctx.user_id, target.user_id]),
                Marriage.user2_id.in_([ctx.user_id, target.user_id]),
            ),
        )
    )
    if active is not None:
        await ctx.reply(ctx.t("marriage_exists"))
        return

    await ctx.container.cache.set(
        f"marry:{ctx.chat_id}:{ctx.user_id}:{target.user_id}", "1", ttl=300
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💍 Принять", callback_data=f"marry:y:{ctx.user_id}:{target.user_id}"
                ),
                InlineKeyboardButton(text="❌ Отклонить", callback_data="marry:n"),
            ]
        ]
    )
    await ctx.reply(
        texts.t(
            ctx.locale,
            "marriage_proposed",
            name=mention(ctx.user_id, ctx.message.from_user.full_name if ctx.message.from_user else None),
        )
        + f"\n\n{mention(target.user_id, target.display)}",
        keyboard=keyboard,
    )


@router.callback_query(F.data.startswith("marry:"))
async def marry_callback(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    parts = callback.data.split(":")
    async with container.db.session_scope() as session:
        settings = await container.chats.settings(session, callback.message.chat.id)
        locale = container.locale(settings)
        if parts[1] == "n":
            await edit_or_send(callback, texts.t(locale, "cancelled"), None)
            await callback.answer()
            return
        from_id, to_id = int(parts[2]), int(parts[3])
        if callback.from_user.id != to_id:
            await answer_alert(callback, "🙃 Ответить может только адресат предложения.")
            return
        if not await container.cache.get(f"marry:{callback.message.chat.id}:{from_id}:{to_id}"):
            await answer_alert(callback, "⌛ Предложение устарело.")
            return
        await container.cache.delete(f"marry:{callback.message.chat.id}:{from_id}:{to_id}")

        exists = await session.scalar(
            select(Marriage).where(
                Marriage.chat_id == callback.message.chat.id,
                Marriage.status == "active",
                or_(
                    Marriage.user1_id.in_([from_id, to_id]),
                    Marriage.user2_id.in_([from_id, to_id]),
                ),
            )
        )
        if exists is not None:
            await answer_alert(callback, texts.t(locale, "marriage_exists"))
            return
        session.add(
            Marriage(
                chat_id=callback.message.chat.id,
                user1_id=from_id,
                user2_id=to_id,
                status="active",
            )
        )
        await session.flush()
        a = await session.get(User, from_id)
        b = await session.get(User, to_id)
        text = texts.t(
            locale,
            "marriage_created",
            a=mention(from_id, a.display_name if a else None),
            b=mention(to_id, b.display_name if b else None),
        )
    await edit_or_send(callback, text, None)
    await callback.answer("💍")


@command(
    "развод",
    aliases=("divorce",),
    module="social",
    category="social",
    description_ru="Расторгнуть брак",
    description_en="Divorce",
    usage="развод",
    cooldown=5,
    group_only=True,
)
async def divorce(ctx: CommandContext) -> None:
    row = await ctx.session.scalar(
        select(Marriage).where(
            Marriage.chat_id == ctx.chat_id,
            Marriage.status == "active",
            or_(Marriage.user1_id == ctx.user_id, Marriage.user2_id == ctx.user_id),
        )
    )
    if row is None:
        await ctx.reply(ctx.t("marriage_none"))
        return
    row.status = "divorced"
    row.ended_at = now_utc()
    partner_id = row.user2_id if row.user1_id == ctx.user_id else row.user1_id
    await ctx.session.flush()
    await ctx.reply(ctx.t("marriage_divorced"))
    if ctx.container.bot is not None:
        try:
            await ctx.container.bot.send_message(partner_id, "💔 Ваш брак расторгнут. Мур.")
        except Exception:  # noqa: BLE001 - у партнёра может быть закрыт ЛС
            pass


async def _marriage_of(session, chat_id: int, user_id: int) -> Marriage | None:
    return await session.scalar(
        select(Marriage).where(
            Marriage.chat_id == chat_id,
            Marriage.status == "active",
            or_(Marriage.user1_id == user_id, Marriage.user2_id == user_id),
        )
    )


@command(
    "пара",
    aliases=("отношения", "любовь", "партнёр", "partner"),
    module="social",
    category="social",
    description_ru="Показать вашу пару и сколько вы вместе",
    description_en="Show your partner and relationship length",
    usage="пара",
    cooldown=3,
    group_only=True,
)
async def couple(ctx: CommandContext) -> None:
    row = await _marriage_of(ctx.session, ctx.chat_id, ctx.user_id)
    if row is None:
        await ctx.reply(ctx.t("profile_no_partner"))
        return
    partner_id = row.user2_id if row.user1_id == ctx.user_id else row.user1_id
    partner = await ctx.session.get(User, partner_id)
    partner_name = partner.display_name if partner else str(partner_id)
    days = max(0, (now_utc() - (as_utc(row.created_at) or now_utc())).days)
    if ctx.locale == "ru":
        text = (
            "💞 <b>Отношения</b>\n\n"
            f"{mention(ctx.user_id, ctx.message.from_user.full_name if ctx.message.from_user else None)} "
            f"+ {mention(partner_id, partner_name)}\n"
            f"📅 Вместе: <b>{days}</b> дн.\n"
            f"💍 Со дня: {format_datetime(row.created_at, ctx.container.settings.timezone)}"
        )
    else:
        text = (
            "💞 <b>Relationships</b>\n\n"
            f"{mention(ctx.user_id, ctx.message.from_user.full_name if ctx.message.from_user else None)} "
            f"+ {mention(partner_id, partner_name)}\n"
            f"📅 Together: <b>{days}</b> days"
        )
    await ctx.reply(text)


@command(
    "браки",
    aliases=("пары", "couples"),
    module="social",
    category="social",
    description_ru="Список пар группы",
    description_en="Couples in this chat",
    usage="браки",
    cooldown=5,
    group_only=True,
)
async def marriages_list(ctx: CommandContext) -> None:
    rows = list(
        await ctx.session.scalars(
            select(Marriage)
            .where(Marriage.chat_id == ctx.chat_id, Marriage.status == "active")
            .order_by(Marriage.created_at)
            .limit(10)
        )
    )
    if not rows:
        await ctx.reply("💔 В группе пока нет браков. Начните первым: <code>брак @user</code>")
        return
    lines = ["💍 <b>Пары группы</b>", ""]
    for row in rows:
        first = await ctx.session.get(User, row.user1_id)
        second = await ctx.session.get(User, row.user2_id)
        days = max(0, (now_utc() - (as_utc(row.created_at) or now_utc())).days)
        lines.append(
            f"• {mention(row.user1_id, first.display_name if first else None)} + "
            f"{mention(row.user2_id, second.display_name if second else None)} — {days} дн."
        )
    await ctx.reply("\n".join(lines))


# --- Семья ----------------------------------------------------------------
@command(
    "семья",
    aliases=("family",),
    module="social",
    category="social",
    description_ru="Создать семью, вступить или посмотреть информацию",
    description_en="Family: create, join, info",
    usage="семья создать Котики",
    cooldown=3,
    group_only=True,
)
async def family(ctx: CommandContext) -> None:
    sub = (ctx.arg(0) or "").lower()

    if sub in {"создать", "create"}:
        name = " ".join(ctx.args[1:]).strip()
        if not name:
            await ctx.reply(ctx.t("not_enough_args", usage="семья создать Котики"))
            return
        exists = await ctx.session.scalar(
            select(Family).where(Family.chat_id == ctx.chat_id, Family.name == name)
        )
        if exists is not None:
            await ctx.reply(ctx.t("family_exists"))
            return
        in_family = await ctx.session.scalar(
            select(FamilyMember).where(
                FamilyMember.chat_id == ctx.chat_id, FamilyMember.user_id == ctx.user_id
            )
        )
        if in_family is not None:
            await ctx.reply(ctx.t("family_in_other"))
            return
        row = Family(chat_id=ctx.chat_id, name=name[:64], owner_id=ctx.user_id)
        ctx.session.add(row)
        await ctx.session.flush()
        ctx.session.add(
            FamilyMember(
                family_id=row.id, chat_id=ctx.chat_id, user_id=ctx.user_id, role="owner"
            )
        )
        await ctx.session.flush()
        await ctx.reply(ctx.t("family_created", name=name))
        return

    if sub in {"вступить", "join"}:
        name = " ".join(ctx.args[1:]).strip()
        row = await ctx.session.scalar(
            select(Family).where(Family.chat_id == ctx.chat_id, Family.name == name)
        )
        if row is None:
            await ctx.reply(ctx.t("family_not_found"))
            return
        in_family = await ctx.session.scalar(
            select(FamilyMember).where(
                FamilyMember.chat_id == ctx.chat_id, FamilyMember.user_id == ctx.user_id
            )
        )
        if in_family is not None:
            await ctx.reply(ctx.t("family_in_other"))
            return
        ctx.session.add(
            FamilyMember(family_id=row.id, chat_id=ctx.chat_id, user_id=ctx.user_id)
        )
        await ctx.session.flush()
        await ctx.reply(ctx.t("family_joined", name=row.name))
        return

    if sub in {"выйти", "leave"}:
        row = await ctx.session.scalar(
            select(FamilyMember).where(
                FamilyMember.chat_id == ctx.chat_id, FamilyMember.user_id == ctx.user_id
            )
        )
        if row is None:
            await ctx.reply(ctx.t("family_not_found"))
            return
        family_row = await ctx.session.get(Family, row.family_id)
        await ctx.session.delete(row)
        await ctx.session.flush()
        if family_row is not None and family_row.owner_id == ctx.user_id:
            others = await ctx.session.scalar(
                select(FamilyMember).where(FamilyMember.family_id == family_row.id)
            )
            if others is None:
                await ctx.session.delete(family_row)
            else:
                family_row.owner_id = others.user_id
                others.role = "owner"
        await ctx.reply("👋 Вы вышли из семьи.")
        return

    member = await ctx.session.scalar(
        select(FamilyMember).where(
            FamilyMember.chat_id == ctx.chat_id, FamilyMember.user_id == ctx.user_id
        )
    )
    if member is None:
        families = list(
            await ctx.session.scalars(select(Family).where(Family.chat_id == ctx.chat_id).limit(10))
        )
        lines = ["👨‍👩‍👧 <b>Семьи группы</b>", ""]
        lines += [f"• <b>{escape(item.name)}</b> — глава {mention(item.owner_id)}" for item in families]
        lines.append("\nСоздать: <code>семья создать Название</code>")
        await ctx.reply("\n".join(lines) if families else "👨‍👩‍👧 Семей пока нет. Создайте первую!")
        return

    family_row = await ctx.session.get(Family, member.family_id)
    if family_row is None:
        await ctx.reply(ctx.t("family_not_found"))
        return
    members = list(
        await ctx.session.scalars(
            select(FamilyMember).where(FamilyMember.family_id == family_row.id)
        )
    )
    names = []
    for item in members:
        user = await ctx.session.get(User, item.user_id)
        names.append(f"• {mention(item.user_id, user.display_name if user else None)} — {item.role}")
    await ctx.reply(
        ctx.t(
            "family_info",
            name=escape(family_row.name),
            owner=mention(family_row.owner_id),
            count=len(members),
            description=escape(family_row.description) or "—",
            members="\n".join(names),
        )
    )


# --- Питомец --------------------------------------------------------------
@command(
    "питомец",
    aliases=("pet", "зверь"),
    module="social",
    category="social",
    description_ru="Питомец: купить, покормить, посмотреть",
    description_en="Pet: adopt, feed, info",
    usage="питомец купить кот",
    cooldown=3,
    group_only=True,
)
async def pet(ctx: CommandContext) -> None:
    sub = (ctx.arg(0) or "").lower()
    row = await ctx.session.scalar(
        select(Pet).where(Pet.chat_id == ctx.chat_id, Pet.owner_id == ctx.user_id)
    )

    if sub in {"купить", "adopt", "buy"}:
        if row is not None:
            await ctx.reply("🐾 У вас уже есть питомец.")
            return
        species_raw = (ctx.arg(1) or "кот").lower()
        emoji, species = PET_SPECIES.get(species_raw, ("🐾", species_raw))
        try:
            await ctx.economy.debit(
                ctx.chat_id, ctx.user_id, PET_PRICE, kind="pet", reason=f"Питомец: {species}"
            )
        except InsufficientFunds as exc:
            await ctx.reply(
                ctx.t("insufficient_funds", currency=ctx.t("currency"), need=exc.need, have=exc.have)
            )
            return
        except EconomyError:
            await ctx.reply(ctx.t("error"))
            return
        name = random.choice(["Барсик", "Мурка", "Рекс", "Симба", "Луна", "Пушок", "Тоша"])
        row = Pet(chat_id=ctx.chat_id, owner_id=ctx.user_id, name=name, species=species)
        ctx.session.add(row)
        await ctx.session.flush()
        await ctx.reply(f"{emoji} " + ctx.t("pet_adopted", name=name))
        return

    if row is None:
        await ctx.reply(ctx.t("pet_none"))
        return

    if sub in {"покормить", "feed"}:
        try:
            await ctx.economy.debit(
                ctx.chat_id, ctx.user_id, PET_FOOD_PRICE, kind="pet_food", reason="Корм для питомца"
            )
        except InsufficientFunds as exc:
            await ctx.reply(
                ctx.t("pet_no_money", price=PET_FOOD_PRICE, currency=ctx.t("currency"), balance=exc.have)
            )
            return
        row.hunger = min(100, row.hunger + 25)
        row.happiness = min(100, row.happiness + 10)
        row.xp += 5
        if row.xp >= row.level * 50:
            row.level += 1
        await ctx.session.flush()
        await ctx.reply(ctx.t("pet_fed", name=row.name, hunger=row.hunger))
        return

    emoji = {"кот": "🐱", "пёс": "🐶", "дракон": "🐲", "лиса": "🦊"}.get(row.species, "🐾")
    await ctx.reply(
        ctx.t(
            "pet_info",
            emoji=emoji,
            name=row.name,
            species=row.species,
            level=row.level,
            hunger=row.hunger,
            happiness=row.happiness,
        )
    )


# --- Подарки --------------------------------------------------------------
@command(
    "подарить",
    aliases=("gift", "подарок"),
    module="social",
    category="social",
    description_ru="Отправить подарок участнику (10 Ирисок)",
    description_en="Send a gift (10 coins)",
    usage="подарить @user счастья!",
    cooldown=3,
    group_only=True,
)
async def gift(ctx: CommandContext) -> None:
    target = await ctx.resolve_target()
    if target is None or not target.user_id:
        await ctx.reply(ctx.t("no_target"))
        return
    if target.user_id == ctx.user_id:
        await ctx.reply(ctx.t("mod_self"))
        return
    text = " ".join(ctx.args[1:]) if not ctx.message.reply_to_message else ctx.args_text
    if not text:
        await ctx.reply(ctx.t("not_enough_args", usage=ctx.spec.usage))
        return
    try:
        await ctx.economy.debit(
            ctx.chat_id, ctx.user_id, GIFT_PRICE, kind="gift", reason="Подарок"
        )
    except InsufficientFunds as exc:
        await ctx.reply(
            ctx.t("insufficient_funds", currency=ctx.t("currency"), need=exc.need, have=exc.have)
        )
        return
    ctx.session.add(
        Gift(
            chat_id=ctx.chat_id,
            from_user_id=ctx.user_id,
            to_user_id=target.user_id,
            text=text[:500],
        )
    )
    await ctx.session.flush()
    await ctx.reply(
        ctx.t("gift_sent", target=mention(target.user_id, target.display), text=escape(text[:500]))
    )


@command(
    "соц",
    aliases=("social", "социалка"),
    module="social",
    category="social",
    description_ru="Социальные связи: друзья, брак, семья, питомец",
    description_en="Social: friends, marriage, family, pets",
    usage="соц",
    cooldown=3,
)
async def social_panel(ctx: CommandContext) -> None:
    text = (
        "💞 <b>Социальные связи</b>\n\n"
        "🤝 <code>друг @user</code> — добавить друга\n"
        "💍 <code>брак @user</code> — предложить брак\n"
        "💞 <code>пара</code> — ваши отношения · <code>браки</code> — пары группы\n"
        "💔 <code>развод</code> — расторгнуть брак\n"
        "👨‍👩‍👧 <code>семья создать Название</code> · <code>семья вступить Название</code>\n"
        "🐾 <code>питомец купить кот</code> · <code>питомец покормить</code>\n"
        "🎁 <code>подарить @user текст</code>"
    )
    await ctx.reply(text, keyboard=menu_with_rows(ctx.locale, [[("👤 Профиль", "menu:profile")]]))


@router.callback_query(F.data == "social:panel")
async def cb_panel(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.message is None:
        await callback.answer()
        return
    async with container.db.session_scope() as session:
        settings = await container.chats.settings(session, callback.message.chat.id)
        locale = container.locale(settings)
    await edit_or_send(
        callback,
        "💞 <b>Социальные связи</b>\n\n<code>друг</code> · <code>брак</code> · <code>семья</code> · <code>питомец</code> · <code>подарить</code>",
        back_keyboard(locale),
    )
    await callback.answer()


__all__ = ["router", "friend", "marry", "divorce", "family", "pet", "gift", "social_panel", "PET_PRICE"]
