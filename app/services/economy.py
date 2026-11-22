"""Экономика Ирисок: атомарные операции, идемпотентность, магазин."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.timeutil import as_utc, now_utc
from app.database.models import Inventory, ShopItem, Transaction, Wallet
from app.database.utils import upsert

if TYPE_CHECKING:
    from app.container import Container

log = get_logger(__name__)

START_BONUS = 100
MAX_TRANSFER = 10_000_000


class EconomyError(Exception):
    """Базовая ошибка экономики — текст показывается пользователю."""


class InsufficientFunds(EconomyError):
    def __init__(self, need: int, have: int) -> None:
        super().__init__(f"need {need}, have {have}")
        self.need = need
        self.have = have


class DuplicateOperation(EconomyError):
    """Операция с таким idempotency_key уже выполнена."""


@dataclass(slots=True)
class DailyResult:
    amount: int
    streak: int
    balance: int


class EconomyService:
    def __init__(self, session: AsyncSession, container: Container) -> None:
        self.session = session
        self.container = container
        self.settings = container.settings

    # --- Кошельки ---------------------------------------------------------
    async def get_wallet(self, chat_id: int, user_id: int) -> Wallet | None:
        return await self.session.scalar(
            select(Wallet).where(Wallet.chat_id == chat_id, Wallet.user_id == user_id)
        )

    async def ensure_wallet(self, chat_id: int, user_id: int) -> Wallet:
        wallet = await self.get_wallet(chat_id, user_id)
        if wallet is not None:
            return wallet
        await upsert(
            self.session,
            Wallet,
            {
                "chat_id": chat_id,
                "user_id": user_id,
                "balance": START_BONUS,
                "total_earned": START_BONUS,
            },
            index_elements=["chat_id", "user_id"],
        )
        wallet = await self.get_wallet(chat_id, user_id)
        if wallet is None:
            wallet = Wallet(
                chat_id=chat_id,
                user_id=user_id,
                balance=START_BONUS,
                total_earned=START_BONUS,
            )
            self.session.add(wallet)
            await self.session.flush()
        else:
            # Бонус начисляем только реально новому кошельку.
            await self.session.refresh(wallet)
        return wallet

    async def balance(self, chat_id: int, user_id: int) -> int:
        wallet = await self.get_wallet(chat_id, user_id)
        return wallet.balance if wallet else 0

    async def _lock_wallets(self, chat_id: int, user_ids: list[int]) -> dict[int, Wallet]:
        """Блокирует кошельки в детерминированном порядке (против дедлоков)."""
        wallets = {}
        for user_id in sorted(set(user_ids)):
            await self.ensure_wallet(chat_id, user_id)
        stmt = (
            select(Wallet)
            .where(Wallet.chat_id == chat_id, Wallet.user_id.in_(sorted(set(user_ids))))
            .order_by(Wallet.user_id)
            .with_for_update()
        )
        for wallet in await self.session.scalars(stmt):
            wallets[wallet.user_id] = wallet
        return wallets

    async def _check_idempotency(self, key: str | None) -> None:
        if not key:
            return
        exists = await self.session.scalar(
            select(Transaction.id).where(Transaction.idempotency_key == key)
        )
        if exists is not None:
            raise DuplicateOperation(key)

    async def _write_transaction(
        self,
        *,
        chat_id: int,
        user_id: int | None,
        counterparty_id: int | None,
        amount: int,
        kind: str,
        reason: str | None,
        balance_after: int | None,
        key: str | None,
    ) -> Transaction:
        tx = Transaction(
            chat_id=chat_id,
            user_id=user_id,
            counterparty_id=counterparty_id,
            amount=amount,
            kind=kind,
            reason=reason,
            balance_after=balance_after,
            idempotency_key=key,
        )
        self.session.add(tx)
        try:
            await self.session.flush()
        except IntegrityError as exc:  # гонка по ключу идемпотентности
            await self.session.rollback()
            raise DuplicateOperation(key or "") from exc
        return tx

    # --- Начисления и списания -------------------------------------------
    async def credit(
        self,
        chat_id: int,
        user_id: int,
        amount: int,
        *,
        kind: str = "credit",
        reason: str | None = None,
        idempotency_key: str | None = None,
    ) -> Wallet:
        if amount <= 0:
            raise EconomyError("amount must be positive")
        await self._check_idempotency(idempotency_key)
        wallet = await self.ensure_wallet(chat_id, user_id)
        wallet.balance += amount
        wallet.total_earned += amount
        await self.session.flush()
        await self._write_transaction(
            chat_id=chat_id,
            user_id=user_id,
            counterparty_id=None,
            amount=amount,
            kind=kind,
            reason=reason,
            balance_after=wallet.balance,
            key=idempotency_key,
        )
        return wallet

    async def debit(
        self,
        chat_id: int,
        user_id: int,
        amount: int,
        *,
        kind: str = "debit",
        reason: str | None = None,
        idempotency_key: str | None = None,
    ) -> Wallet:
        if amount <= 0:
            raise EconomyError("amount must be positive")
        await self._check_idempotency(idempotency_key)
        wallets = await self._lock_wallets(chat_id, [user_id])
        wallet = wallets[user_id]
        if wallet.balance < amount:
            raise InsufficientFunds(need=amount, have=wallet.balance)
        wallet.balance -= amount
        wallet.total_spent += amount
        await self.session.flush()
        await self._write_transaction(
            chat_id=chat_id,
            user_id=user_id,
            counterparty_id=None,
            amount=-amount,
            kind=kind,
            reason=reason,
            balance_after=wallet.balance,
            key=idempotency_key,
        )
        return wallet

    async def transfer(
        self,
        chat_id: int,
        from_user_id: int,
        to_user_id: int,
        amount: int,
        *,
        kind: str = "transfer",
        reason: str | None = None,
        idempotency_key: str | None = None,
    ) -> tuple[Wallet, Wallet]:
        if amount <= 0:
            raise EconomyError("amount must be positive")
        if amount > MAX_TRANSFER:
            raise EconomyError("amount too large")
        if from_user_id == to_user_id:
            raise EconomyError("self transfer")
        await self._check_idempotency(idempotency_key)

        wallets = await self._lock_wallets(chat_id, [from_user_id, to_user_id])
        sender, receiver = wallets[from_user_id], wallets[to_user_id]
        if sender.balance < amount:
            raise InsufficientFunds(need=amount, have=sender.balance)

        sender.balance -= amount
        sender.total_spent += amount
        receiver.balance += amount
        receiver.total_earned += amount
        await self.session.flush()

        await self._write_transaction(
            chat_id=chat_id,
            user_id=from_user_id,
            counterparty_id=to_user_id,
            amount=-amount,
            kind=kind,
            reason=reason,
            balance_after=sender.balance,
            key=idempotency_key,
        )
        return sender, receiver

    # --- Ежедневная награда ----------------------------------------------
    async def daily(self, chat_id: int, user_id: int) -> DailyResult | None:
        """Возвращает результат или None, если награда уже получена сегодня."""
        today: date = now_utc().date()
        key = f"daily:{chat_id}:{user_id}:{today.isoformat()}"
        wallet = await self.ensure_wallet(chat_id, user_id)
        last = as_utc(wallet.last_daily_at)

        if last is not None and last.date() == today:
            return None

        if last is not None and last.date() == today - timedelta(days=1):
            wallet.daily_streak += 1
        else:
            wallet.daily_streak = 1

        amount = self.settings.daily_bonus_base + self.settings.daily_bonus_streak_step * (
            wallet.daily_streak - 1
        )
        amount = min(amount, self.settings.daily_bonus_base * 3)

        wallet.balance += amount
        wallet.total_earned += amount
        wallet.last_daily_at = now_utc()
        await self.session.flush()
        try:
            await self._write_transaction(
                chat_id=chat_id,
                user_id=user_id,
                counterparty_id=None,
                amount=amount,
                kind="daily",
                reason="Ежедневная награда",
                balance_after=wallet.balance,
                key=key,
            )
        except DuplicateOperation:
            await self.session.rollback()
            return None
        return DailyResult(amount=amount, streak=wallet.daily_streak, balance=wallet.balance)

    # --- Магазин ----------------------------------------------------------
    async def shop_items(self, chat_id: int) -> list[ShopItem]:
        rows = await self.session.scalars(
            select(ShopItem)
            .where(
                ShopItem.is_active.is_(True),
                or_(ShopItem.chat_id == chat_id, ShopItem.chat_id.is_(None)),
            )
            .order_by(ShopItem.price)
        )
        return list(rows)

    async def find_item(self, chat_id: int, code_or_id: str) -> ShopItem | None:
        stmt = select(ShopItem).where(
            or_(ShopItem.chat_id == chat_id, ShopItem.chat_id.is_(None)),
            ShopItem.is_active.is_(True),
        )
        if code_or_id.isdigit():
            stmt = stmt.where(ShopItem.id == int(code_or_id))
        else:
            stmt = stmt.where(ShopItem.code == code_or_id.casefold())
        return await self.session.scalar(stmt)

    async def buy(
        self, chat_id: int, user_id: int, code_or_id: str, *, idempotency_key: str | None = None
    ) -> tuple[ShopItem, Wallet]:
        item = await self.find_item(chat_id, code_or_id)
        if item is None:
            raise EconomyError("item not found")
        if item.stock is not None and item.stock <= 0:
            raise EconomyError("out of stock")

        wallet = await self.ensure_wallet(chat_id, user_id)
        if wallet.balance < item.price:
            raise InsufficientFunds(need=item.price, have=wallet.balance)

        key = idempotency_key or f"shop:{chat_id}:{user_id}:{item.id}:{now_utc().timestamp()}"
        await self.debit(
            chat_id,
            user_id,
            item.price,
            kind="shop",
            reason=f"Покупка: {item.title}",
            idempotency_key=key,
        )

        if item.stock is not None:
            item.stock -= 1

        inventory = await self.session.scalar(
            select(Inventory).where(
                Inventory.chat_id == chat_id,
                Inventory.user_id == user_id,
                Inventory.item_id == item.id,
            )
        )
        if inventory is None:
            self.session.add(
                Inventory(chat_id=chat_id, user_id=user_id, item_id=item.id, quantity=1)
            )
        else:
            inventory.quantity += 1
        await self.session.flush()

        # Предметы вида vip продлевают статус VIP в профиле.
        if item.kind == "vip" or item.code == "vip":
            from datetime import timedelta

            from app.services.profiles import ProfileService

            profile = await ProfileService(self.session, self.container).get_or_create(user_id)
            base = as_utc(profile.vip_until) or now_utc()
            profile.vip_until = max(base, now_utc()) + timedelta(days=1)
            await self.session.flush()

        return item, wallet

    async def inventory(self, chat_id: int, user_id: int) -> list[tuple[ShopItem, int]]:
        rows = await self.session.execute(
            select(ShopItem, Inventory.quantity)
            .join(Inventory, Inventory.item_id == ShopItem.id)
            .where(
                Inventory.chat_id == chat_id,
                Inventory.user_id == user_id,
                Inventory.quantity > 0,
            )
            .order_by(ShopItem.price.desc())
        )
        return [(item, quantity) for item, quantity in rows.all()]

    async def take_from_inventory(self, chat_id: int, user_id: int, code: str) -> ShopItem | None:
        item = await self.find_item(chat_id, code)
        if item is None:
            return None
        inventory = await self.session.scalar(
            select(Inventory).where(
                Inventory.chat_id == chat_id,
                Inventory.user_id == user_id,
                Inventory.item_id == item.id,
                Inventory.quantity > 0,
            )
        )
        if inventory is None:
            return None
        inventory.quantity -= 1
        await self.session.flush()
        return item

    # --- История и рейтинги ---------------------------------------------
    async def history(self, chat_id: int, user_id: int, limit: int = 10) -> list[Transaction]:
        rows = await self.session.scalars(
            select(Transaction)
            .where(
                Transaction.chat_id == chat_id,
                or_(Transaction.user_id == user_id, Transaction.counterparty_id == user_id),
            )
            .order_by(Transaction.created_at.desc())
            .limit(limit)
        )
        return list(rows)

    async def top_balances(self, chat_id: int, limit: int = 10) -> list[Wallet]:
        rows = await self.session.scalars(
            select(Wallet)
            .where(Wallet.chat_id == chat_id)
            .order_by(Wallet.balance.desc())
            .limit(limit)
        )
        return list(rows)

    async def circulation(self, chat_id: int) -> int:
        from sqlalchemy import func

        return int(
            await self.session.scalar(
                select(func.coalesce(func.sum(Wallet.balance), 0)).where(Wallet.chat_id == chat_id)
            )
            or 0
        )
