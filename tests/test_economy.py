"""Тесты экономики Ирисок: атомарность, идемпотентность, магазин, бонус."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.database.models import ShopItem
from app.services.economy import DuplicateOperation, EconomyError, InsufficientFunds

CHAT_ID = -100500
USER_A = 101
USER_B = 202


async def _prepare(container) -> None:
    async with container.db.session_scope() as session:
        await container.chats.ensure(session, chat_id=CHAT_ID, title="Test", chat_type="supergroup")
        await container.members(session).ensure_user(
            user_id=USER_A, username="a", first_name="A", last_name="One"
        )
        await container.members(session).ensure_user(
            user_id=USER_B, username="b", first_name="B", last_name="Two"
        )


@pytest.mark.asyncio
async def test_wallet_start_bonus(container) -> None:
    await _prepare(container)
    async with container.db.session_scope() as session:
        wallet = await container.economy(session).ensure_wallet(CHAT_ID, USER_A)
        assert wallet.balance == 100
        assert wallet.total_earned == 100


@pytest.mark.asyncio
async def test_credit_and_debit(container) -> None:
    await _prepare(container)
    async with container.db.session_scope() as session:
        economy = container.economy(session)
        await economy.credit(CHAT_ID, USER_A, 50, reason="test")
        assert await economy.balance(CHAT_ID, USER_A) == 150
        await economy.debit(CHAT_ID, USER_A, 30, reason="test")
        assert await economy.balance(CHAT_ID, USER_A) == 120


@pytest.mark.asyncio
async def test_debit_cannot_go_negative(container) -> None:
    await _prepare(container)
    async with container.db.session_scope() as session:
        economy = container.economy(session)
        with pytest.raises(InsufficientFunds):
            await economy.debit(CHAT_ID, USER_A, 500)
        assert await economy.balance(CHAT_ID, USER_A) == 100


@pytest.mark.asyncio
async def test_double_spend_sequence(container) -> None:
    """Два списания по 60 из 100: второе должно упасть, баланс не отрицательный."""
    await _prepare(container)
    async with container.db.session_scope() as session:
        economy = container.economy(session)
        await economy.debit(CHAT_ID, USER_A, 60)
        with pytest.raises(InsufficientFunds):
            await economy.debit(CHAT_ID, USER_A, 60)
        wallet = await economy.get_wallet(CHAT_ID, USER_A)
        assert wallet is not None
        assert wallet.balance == 40


@pytest.mark.asyncio
async def test_transfer(container) -> None:
    await _prepare(container)
    async with container.db.session_scope() as session:
        economy = container.economy(session)
        sender, receiver = await economy.transfer(CHAT_ID, USER_A, USER_B, 70)
        assert sender.balance == 30
        assert receiver.balance == 170
        assert sender.total_spent == 70
        assert receiver.total_earned == 170


@pytest.mark.asyncio
async def test_transfer_validation(container) -> None:
    await _prepare(container)
    async with container.db.session_scope() as session:
        economy = container.economy(session)
        with pytest.raises(EconomyError):
            await economy.transfer(CHAT_ID, USER_A, USER_A, 10)
        with pytest.raises(InsufficientFunds):
            await economy.transfer(CHAT_ID, USER_A, USER_B, 1000)


@pytest.mark.asyncio
async def test_idempotency(container) -> None:
    await _prepare(container)
    async with container.db.session_scope() as session:
        economy = container.economy(session)
        await economy.credit(CHAT_ID, USER_A, 25, idempotency_key="once")
        with pytest.raises(DuplicateOperation):
            await economy.credit(CHAT_ID, USER_A, 25, idempotency_key="once")
        assert await economy.balance(CHAT_ID, USER_A) == 125


@pytest.mark.asyncio
async def test_daily_once_per_day(container) -> None:
    await _prepare(container)
    async with container.db.session_scope() as session:
        economy = container.economy(session)
        first = await economy.daily(CHAT_ID, USER_A)
        assert first is not None
        assert first.streak == 1
        assert first.amount == container.settings.daily_bonus_base
        second = await economy.daily(CHAT_ID, USER_A)
        assert second is None
        assert await economy.balance(CHAT_ID, USER_A) == 100 + first.amount


@pytest.mark.asyncio
async def test_daily_streak(container) -> None:
    await _prepare(container)
    async with container.db.session_scope() as session:
        economy = container.economy(session)
        wallet = await economy.ensure_wallet(CHAT_ID, USER_A)
        wallet.last_daily_at = datetime.now(UTC) - timedelta(days=1)
        wallet.daily_streak = 1
        await session.flush()
        result = await economy.daily(CHAT_ID, USER_A)
        assert result is not None
        assert result.streak == 2
        assert result.amount == container.settings.daily_bonus_base + container.settings.daily_bonus_streak_step


@pytest.mark.asyncio
async def test_shop_purchase(container) -> None:
    await _prepare(container)
    async with container.db.session_scope() as session:
        item = ShopItem(
            chat_id=CHAT_ID,
            code="vip",
            title="VIP на день",
            price=50,
            kind="item",
            stock=2,
        )
        session.add(item)
        await session.flush()
        economy = container.economy(session)
        bought, wallet = await economy.buy(CHAT_ID, USER_A, "vip")
        assert bought.code == "vip"
        assert wallet.balance == 50
        inventory = await economy.inventory(CHAT_ID, USER_A)
        assert inventory and inventory[0][1] == 1
        assert bought.stock == 1


@pytest.mark.asyncio
async def test_shop_out_of_stock(container) -> None:
    await _prepare(container)
    async with container.db.session_scope() as session:
        session.add(
            ShopItem(chat_id=CHAT_ID, code="zero", title="Нет в наличии", price=10, stock=0)
        )
        await session.flush()
        with pytest.raises(EconomyError):
            await container.economy(session).buy(CHAT_ID, USER_A, "zero")


@pytest.mark.asyncio
async def test_balance_check_constraint_exists(container) -> None:
    async with container.db.session_scope() as session:
        wallet = await container.economy(session).ensure_wallet(CHAT_ID, USER_A)
        wallet.balance = -1
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()
