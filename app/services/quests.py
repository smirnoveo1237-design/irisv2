"""Квесты и недельный турнир на основе суточной активности."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Quest, QuestProgress, UserDayStat
from app.database.utils import upsert

if TYPE_CHECKING:
    from app.container import Container

DEFAULT_QUESTS = [
    {
        "code": "daily_messages_10",
        "title": "Активный участник",
        "description": "Отправьте 10 сообщений за день",
        "goal_type": "messages",
        "goal_value": 10,
        "reward_amount": 40,
        "reward_xp": 20,
        "period": "daily",
    },
    {
        "code": "daily_messages_30",
        "title": "Душа чата",
        "description": "Отправьте 30 сообщений за день",
        "goal_type": "messages",
        "goal_value": 30,
        "reward_amount": 120,
        "reward_xp": 60,
        "period": "daily",
    },
    {
        "code": "daily_command_1",
        "title": "Первый шаг",
        "description": "Выполните любую команду IrisV2",
        "goal_type": "commands",
        "goal_value": 1,
        "reward_amount": 15,
        "reward_xp": 5,
        "period": "daily",
    },
]


class QuestService:
    def __init__(self, session: AsyncSession, container: Container) -> None:
        self.session = session
        self.container = container

    async def seed(self) -> None:
        for item in DEFAULT_QUESTS:
            exists = await self.session.scalar(
                select(Quest.id).where(Quest.code == item["code"])
            )
            if exists is None:
                self.session.add(Quest(**item))
        await self.session.flush()

    async def active(self) -> list[Quest]:
        return list(
            await self.session.scalars(
                select(Quest).where(Quest.is_active.is_(True)).order_by(Quest.id)
            )
        )

    async def bump(self, chat_id: int, user_id: int, field: str, amount: int = 1) -> None:
        today = date.today()
        upsert_field = {
            "messages": {"messages": UserDayStat.messages + amount},
            "xp": {"xp": UserDayStat.xp + amount},
        }[field]
        await upsert(
            self.session,
            UserDayStat,
            {
                "chat_id": chat_id,
                "user_id": user_id,
                "day": today,
                "messages": amount if field == "messages" else 0,
                "xp": amount if field == "xp" else 0,
            },
            index_elements=["chat_id", "user_id", "day"],
            update_values=upsert_field,
        )

    async def progress_for(
        self, chat_id: int, user_id: int
    ) -> list[tuple[Quest, int, bool]]:
        today = date.today()
        row = await self.session.scalar(
            select(UserDayStat).where(
                UserDayStat.chat_id == chat_id,
                UserDayStat.user_id == user_id,
                UserDayStat.day == today,
            )
        )
        values = {
            "messages": row.messages if row else 0,
            "commands": await self._commands_today(chat_id, user_id),
        }
        result: list[tuple[Quest, int, bool]] = []
        for quest in await self.active():
            progress = min(values.get(quest.goal_type, 0), quest.goal_value)
            done = await self._is_done(chat_id, user_id, quest, today)
            result.append((quest, progress, done))
        return result

    async def _commands_today(self, chat_id: int, user_id: int) -> int:
        # Отдельного счётчика команд по участникам нет — считаем по журналу аудита.
        from app.database.models import AuditLog

        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.chat_id == chat_id,
                    AuditLog.actor_id == user_id,
                    AuditLog.action == "command",
                    func.date(AuditLog.created_at) == date.today(),
                )
            )
            or 0
        )

    async def _is_done(self, chat_id: int, user_id: int, quest: Quest, day: date) -> bool:
        exists = await self.session.scalar(
            select(QuestProgress.id).where(
                QuestProgress.quest_id == quest.id,
                QuestProgress.chat_id == chat_id,
                QuestProgress.user_id == user_id,
                QuestProgress.day == day,
            )
        )
        return exists is not None

    async def claim(self, chat_id: int, user_id: int) -> list[tuple[Quest, int]]:
        """Начисляет награды за выполненные квесты. Возвращает список наград."""
        today = date.today()
        rewards: list[tuple[Quest, int]] = []
        from app.services.economy import EconomyService
        from app.services.levels import LevelService

        economy = EconomyService(self.session, self.container)
        levels = LevelService(self.session, self.container)

        for quest, progress, done in await self.progress_for(chat_id, user_id):
            if done or progress < quest.goal_value:
                continue
            self.session.add(
                QuestProgress(
                    quest_id=quest.id,
                    chat_id=chat_id,
                    user_id=user_id,
                    day=today,
                    progress=progress,
                    completed_at=datetime.now(UTC),
                )
            )
            await self.session.flush()
            if quest.reward_amount:
                await economy.credit(
                    chat_id,
                    user_id,
                    quest.reward_amount,
                    kind="quest",
                    reason=quest.title,
                    idempotency_key=f"quest:{quest.id}:{chat_id}:{user_id}:{today}",
                )
            if quest.reward_xp:
                await levels.award(chat_id, user_id, xp=quest.reward_xp)
            rewards.append((quest, quest.reward_amount))
        return rewards

    async def week_top(self, chat_id: int, limit: int = 10) -> list[tuple[int, int, int]]:
        since = date.today() - timedelta(days=6)
        rows = await self.session.execute(
            select(
                UserDayStat.user_id,
                func.coalesce(func.sum(UserDayStat.xp), 0),
                func.coalesce(func.sum(UserDayStat.messages), 0),
            )
            .where(UserDayStat.chat_id == chat_id, UserDayStat.day >= since)
            .group_by(UserDayStat.user_id)
            .order_by(func.coalesce(func.sum(UserDayStat.xp), 0).desc())
            .limit(limit)
        )
        return [(int(user_id), int(xp), int(messages)) for user_id, xp, messages in rows.all()]
