"""Уровни и опыт."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import now_utc
from app.database.models import UserLevel
from app.database.utils import upsert

XP_PER_MESSAGE = 5


def xp_for_level(level: int) -> int:
    """Суммарный XP, необходимый для достижения уровня."""
    return 25 * level * (level - 1)


def level_for_xp(xp: int) -> int:
    level = 1
    while xp_for_level(level + 1) <= xp and level < 500:
        level += 1
    return level


def xp_to_next(xp: int) -> int:
    level = level_for_xp(xp)
    return max(0, xp_for_level(level + 1) - xp)


@dataclass(slots=True)
class LevelResult:
    level: int
    xp: int
    leveled_up: bool


class LevelService:
    def __init__(self, session: AsyncSession, container) -> None:
        self.session = session
        self.container = container

    async def get(self, chat_id: int, user_id: int) -> UserLevel | None:
        return await self.session.scalar(
            select(UserLevel).where(UserLevel.chat_id == chat_id, UserLevel.user_id == user_id)
        )

    async def ensure(self, chat_id: int, user_id: int) -> UserLevel:
        await upsert(
            self.session,
            UserLevel,
            {"chat_id": chat_id, "user_id": user_id, "level": 1, "xp": 0, "messages": 0},
            index_elements=["chat_id", "user_id"],
            update_values={"updated_at": now_utc()},
        )
        row = await self.get(chat_id, user_id)
        if row is None:  # неизвестный диалект
            row = UserLevel(chat_id=chat_id, user_id=user_id)
            self.session.add(row)
            await self.session.flush()
        return row

    async def award(self, chat_id: int, user_id: int, xp: int = XP_PER_MESSAGE) -> LevelResult:
        row = await self.ensure(chat_id, user_id)
        row.xp += xp
        row.messages += 1
        new_level = level_for_xp(row.xp)
        leveled = new_level > row.level
        if leveled:
            row.level = new_level
        await self.session.flush()
        return LevelResult(level=row.level, xp=row.xp, leveled_up=leveled)

    async def top(self, chat_id: int, limit: int = 10) -> list[UserLevel]:
        rows = await self.session.scalars(
            select(UserLevel)
            .where(UserLevel.chat_id == chat_id)
            .order_by(UserLevel.xp.desc())
            .limit(limit)
        )
        return list(rows)

    # --- Прогресс ---------------------------------------------------------
    def progress(self, row: UserLevel) -> tuple[int, int]:
        current = row.xp - xp_for_level(row.level)
        needed = xp_for_level(row.level + 1) - xp_for_level(row.level)
        return max(0, current), max(1, needed)

    @staticmethod
    def format_level(row: UserLevel | None) -> dict[str, int]:
        if row is None:
            return {"level": 1, "xp": 0, "messages": 0, "xp_left": xp_for_level(2)}
        return {
            "level": row.level,
            "xp": row.xp,
            "messages": row.messages,
            "xp_left": xp_to_next(row.xp),
        }


def today_key() -> datetime:
    return now_utc().replace(hour=0, minute=0, second=0, microsecond=0)


__all__ = [
    "LevelResult",
    "LevelService",
    "XP_PER_MESSAGE",
    "level_for_xp",
    "xp_for_level",
    "xp_to_next",
]
