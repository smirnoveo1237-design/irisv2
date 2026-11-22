"""Экономика Ирисок: баланс, переводы, бонус, магазин, инвентарь."""

from __future__ import annotations

import re
from datetime import timedelta

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.commands.context import CommandContext
from app.commands.registry import command
from app.container import Container
from app.core.timeutil import now_utc
from app.modules.common import escape, mention
from app.services.economy import DuplicateOperation, EconomyError, InsufficientFunds
from app.ui.keyboards import back_keyboard, main_menu, menu_with_rows
from app.ui.render import edit_or_send

router = Router(name="iris.economy")

AMOUNT_RE = re.compile(r"^(\d+(?:[.,]\d+)?)\s*(кк|kk|к|k|м|m)?$", re.IGNORECASE)


def parse_amount(raw: str | None) -> int | None:
    if not raw:
        return None
    match = AMOUNT_RE.match(raw.strip())
    if not match:
        return None
    value = float(match.group(1).replace(",", "."))
    suffix = (match.group(2) or "").lower()
    if suffix in {"к", "k"}:
        value *= 1_000
    elif suffix in {"кк", "kk", "м", "m"}:
        value *= 1_000_000
    amount = int(round(value))
    return amount if amount > 0 else None


def hours_to_midnight() -> int:
    now = now_utc()
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((tomorrow - now).total_seconds() // 3600))


@command(
    "баланс",
    aliases=("balance", "кошелёк", "кошелек"),
    module="economy",
    category="economy",
    description_ru="Показать баланс Ирисок",
    description_en="Show your Iris coin balance",
    usage="баланс",
    cooldown=2,
)
async def balance(ctx: CommandContext) -> None:
    wallet = await ctx.economy.ensure_wallet(ctx.chat_id, ctx.user_id)
    await ctx.reply(
        ctx.t(
            "balance",
            name=escape(ctx.message.from_user.full_name if ctx.message.from_user else ""),
            balance=wallet.balance,
            currency=ctx.t("currency"),
            earned=wallet.total_earned,
            spent=wallet.total_spent,
        ),
        keyboard=menu_with_rows(
            ctx.locale,
            [[("🎁 Бонус", "eco:daily"), ("🛍️ Магазин", "eco:shop")]],
        ),
    )


@command(
    "перевод",
    aliases=("дать", "transfer", "перевести"),
    module="economy",
    category="economy",
    description_ru="Перевести Ириски участнику",
    description_en="Send Iris coins to a member",
    usage="перевод @user 100",
    cooldown=2,
)
async def transfer(ctx: CommandContext) -> None:
    target = await ctx.resolve_target()
    if target is None or not target.user_id:
        await ctx.reply(ctx.t("no_target"))
        return
    if target.user_id == ctx.user_id:
        await ctx.reply(ctx.t("transfer_self"))
        return
    raw_amount = ctx.args[0] if ctx.message.reply_to_message else ctx.arg(1)
    amount = parse_amount(raw_amount)
    if amount is None:
        await ctx.reply(ctx.t("transfer_bad_amount", usage=ctx.spec.usage))
        return
    try:
        sender, _ = await ctx.economy.transfer(
            ctx.chat_id,
            ctx.user_id,
            target.user_id,
            amount,
            reason="Перевод участнику",
            idempotency_key=f"tr:{ctx.chat_id}:{ctx.user_id}:{target.user_id}:{ctx.message.message_id}",
        )
    except InsufficientFunds as exc:
        await ctx.reply(
            ctx.t("insufficient_funds", currency=ctx.t("currency"), need=exc.need, have=exc.have)
        )
        return
    except DuplicateOperation:
        await ctx.reply(ctx.t("done"))
        return
    except EconomyError:
        await ctx.reply(ctx.t("error"))
        return

    await ctx.reply(
        ctx.t(
            "transfer_ok",
            amount=amount,
            currency=ctx.t("currency"),
            target=mention(target.user_id, target.display),
            balance=sender.balance,
        )
    )
    try:
        await ctx.bot.send_message(
            target.user_id,
            ctx.t(
                "transfer_received",
                sender=mention(ctx.user_id),
                amount=amount,
                currency=ctx.t("currency"),
            ),
        )
    except Exception:  # noqa: BLE001 - у получателя может быть закрыт ЛС
        pass


@command(
    "бонус",
    aliases=("daily", "дейли", "ежедневно"),
    module="economy",
    category="economy",
    description_ru="Ежедневная награда Ирисками",
    description_en="Claim your daily Iris coins",
    usage="бонус",
    cooldown=2,
)
async def daily(ctx: CommandContext) -> None:
    result = await ctx.economy.daily(ctx.chat_id, ctx.user_id)
    if result is None:
        await ctx.reply(ctx.t("daily_already", hours=hours_to_midnight()))
        return
    await ctx.reply(
        ctx.t(
            "daily_ok",
            amount=result.amount,
            currency=ctx.t("currency"),
            streak=result.streak,
            balance=result.balance,
        )
    )


@command(
    "магазин",
    aliases=("shop", "лавка"),
    module="economy",
    category="economy",
    description_ru="Магазин предметов за Ириски",
    description_en="Iris coin shop",
    usage="магазин",
    cooldown=2,
)
async def shop(ctx: CommandContext) -> None:
    items = await ctx.economy.shop_items(ctx.chat_id)
    if not items:
        await ctx.reply(ctx.t("shop_empty"))
        return
    lines = [ctx.t("shop_title", currency=ctx.t("currency")), ""]
    for item in items:
        stock = f" · осталось {item.stock}" if item.stock is not None else ""
        lines.append(
            f"<b>{item.title}</b> — <code>{item.code}</code> · {item.price} {ctx.t('currency')}{stock}\n"
            f"   <i>{item.description or ''}</i>"
        )
    lines.append("\n🛒 Купить: <code>купить код</code>")
    await ctx.reply("\n".join(lines))


@command(
    "купить",
    aliases=("buy",),
    module="economy",
    category="economy",
    description_ru="Купить предмет из магазина",
    description_en="Buy a shop item",
    usage="купить vip",
    cooldown=2,
)
async def buy(ctx: CommandContext) -> None:
    code = ctx.arg(0)
    if not code:
        await ctx.reply(ctx.t("not_enough_args", usage=ctx.spec.usage))
        return
    try:
        item, wallet = await ctx.economy.buy(
            ctx.chat_id,
            ctx.user_id,
            code,
            idempotency_key=f"buy:{ctx.chat_id}:{ctx.user_id}:{ctx.message.message_id}",
        )
    except InsufficientFunds as exc:
        await ctx.reply(
            ctx.t("insufficient_funds", currency=ctx.t("currency"), need=exc.need, have=exc.have)
        )
        return
    except EconomyError as exc:
        if str(exc) == "item not found":
            await ctx.reply(ctx.t("shop_no_item"))
        elif str(exc) == "out of stock":
            await ctx.reply(ctx.t("shop_no_stock"))
        else:
            await ctx.reply(ctx.t("error"))
        return
    await ctx.reply(
        ctx.t(
            "shop_bought",
            title=item.title,
            price=item.price,
            currency=ctx.t("currency"),
            balance=wallet.balance,
        )
    )


@command(
    "инвентарь",
    aliases=("inventory", "рюкзак"),
    module="economy",
    category="economy",
    description_ru="Ваши предметы",
    description_en="Your items",
    usage="инвентарь",
    cooldown=2,
)
async def inventory(ctx: CommandContext) -> None:
    items = await ctx.economy.inventory(ctx.chat_id, ctx.user_id)
    if not items:
        await ctx.reply(ctx.t("inventory_empty"))
        return
    lines = [ctx.t("inventory_title"), ""]
    for item, quantity in items:
        lines.append(f"• <b>{item.title}</b> × {quantity} (<code>{item.code}</code>)")
    await ctx.reply("\n".join(lines))


@command(
    "операции",
    aliases=("transactions", "транзакции"),
    module="economy",
    category="economy",
    description_ru="Последние операции с Ирисками",
    description_en="Recent coin transactions",
    usage="операции",
    cooldown=2,
)
async def history(ctx: CommandContext) -> None:
    items = await ctx.economy.history(ctx.chat_id, ctx.user_id, limit=10)
    if not items:
        await ctx.reply(ctx.t("history_empty"))
        return
    lines = [ctx.t("history_title"), ""]
    for item in items:
        sign = "+" if item.amount > 0 else ""
        lines.append(
            f"• {item.created_at:%d.%m %H:%M} — <b>{sign}{item.amount}</b> {ctx.t('currency')} "
            f"· {item.kind} {('· ' + item.reason) if item.reason else ''}"
        )
    await ctx.reply("\n".join(lines))


@command(
    "топбаланс",
    aliases=("богачи", "topbalance"),
    module="economy",
    category="economy",
    description_ru="Самые богатые участники группы",
    description_en="Richest members",
    usage="топбаланс",
    cooldown=5,
)
async def top_balance(ctx: CommandContext) -> None:
    rows = await ctx.economy.top_balances(ctx.chat_id, 10)
    if not rows:
        await ctx.reply(ctx.t("leaderboard_empty"))
        return
    lines = [ctx.t("top_balance"), ""]
    for index, wallet in enumerate(rows, start=1):
        member = await ctx.members.get(ctx.chat_id, wallet.user_id)
        name = member.full_name if member else str(wallet.user_id)
        lines.append(f"{index}. {mention(wallet.user_id, name)} — <b>{wallet.balance}</b> {ctx.t('currency')}")
    await ctx.reply("\n".join(lines))


# --- Callback-кнопки ------------------------------------------------------
@router.callback_query(F.data == "eco:daily")
async def cb_daily(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    async with container.db.session_scope() as session:
        result = await container.economy(session).daily(
            callback.message.chat.id, callback.from_user.id
        )
    if result is None:
        await callback.answer(f"⏳ Награда уже получена. Следующая через {hours_to_midnight()} ч.", show_alert=True)
    else:
        await callback.answer(f"🎁 +{result.amount} Ирисок! Баланс: {result.balance}", show_alert=True)


@router.callback_query(F.data == "eco:shop")
async def cb_shop(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.message is None:
        await callback.answer()
        return
    chat_id = callback.message.chat.id
    async with container.db.session_scope() as session:
        settings = await container.chats.settings(session, chat_id)
        locale = container.locale(settings)
        items = await container.economy(session).shop_items(chat_id)
        currency = container.texts.t(locale, "currency")
        if not items:
            text = container.texts.t(locale, "shop_empty")
        else:
            lines = [container.texts.t(locale, "shop_title", currency=currency), ""]
            for item in items:
                lines.append(f"<b>{item.title}</b> — <code>{item.code}</code> · {item.price}")
            text = "\n".join(lines) + "\n\n🛒 <code>купить код</code>"
    await edit_or_send(callback, text, back_keyboard(locale))
    await callback.answer()


@router.callback_query(F.data == "eco:inventory")
async def cb_inventory(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    chat_id = callback.message.chat.id
    async with container.db.session_scope() as session:
        settings = await container.chats.settings(session, chat_id)
        locale = container.locale(settings)
        items = await container.economy(session).inventory(chat_id, callback.from_user.id)
        if not items:
            text = container.texts.t(locale, "inventory_empty")
        else:
            lines = [container.texts.t(locale, "inventory_title"), ""]
            for item, quantity in items:
                lines.append(f"• <b>{item.title}</b> × {quantity}")
            text = "\n".join(lines)
    await edit_or_send(callback, text, back_keyboard(locale))
    await callback.answer()


@router.callback_query(F.data == "eco:history")
async def cb_history(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    chat_id = callback.message.chat.id
    async with container.db.session_scope() as session:
        settings = await container.chats.settings(session, chat_id)
        locale = container.locale(settings)
        items = await container.economy(session).history(chat_id, callback.from_user.id, 10)
        if not items:
            text = container.texts.t(locale, "history_empty")
        else:
            lines = [container.texts.t(locale, "history_title"), ""]
            for item in items:
                sign = "+" if item.amount > 0 else ""
                lines.append(f"• {item.created_at:%d.%m %H:%M} — <b>{sign}{item.amount}</b> · {item.kind}")
            text = "\n".join(lines)
    await edit_or_send(callback, text, back_keyboard(locale))
    await callback.answer()


@router.callback_query(F.data == "eco:top")
async def cb_top(callback: CallbackQuery, container: Container | None = None) -> None:
    if container is None or callback.message is None:
        await callback.answer()
        return
    chat_id = callback.message.chat.id
    async with container.db.session_scope() as session:
        settings = await container.chats.settings(session, chat_id)
        locale = container.locale(settings)
        wallets = await container.economy(session).top_balances(chat_id, 10)
        lines = [container.texts.t(locale, "top_balance"), ""]
        for index, wallet in enumerate(wallets, start=1):
            member = await container.members(session).get(chat_id, wallet.user_id)
            name = member.full_name if member else str(wallet.user_id)
            lines.append(f"{index}. {mention(wallet.user_id, name)} — <b>{wallet.balance}</b>")
        text = "\n".join(lines) if wallets else container.texts.t(locale, "leaderboard_empty")
    await edit_or_send(callback, text, back_keyboard(locale))
    await callback.answer()


__all__ = ["router", "balance", "transfer", "daily", "shop", "buy", "inventory", "history", "top_balance", "parse_amount", "main_menu"]
