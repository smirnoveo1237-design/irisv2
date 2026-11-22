"""Аналитика групп: суточные счётчики, топы, статистика модерации."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.texts import escape_html
from app.database.models import ChatMember, ChatStat, ModerationLog, Wallet
from app.database.utils import upsert


class AnalyticsService:
    def __init__(self, session: AsyncSession, container) -> None:
        self.session = session
        self.container = container

    async def bump(
        self,
        chat_id: int,
        *,
        messages: int = 0,
        commands: int = 0,
        joins: int = 0,
        leaves: int = 0,
        moderated: int = 0,
        day: date | None = None,
    ) -> None:
        day = day or date.today()
        # ON CONFLICT ... DO UPDATE с выражениями — один запрос на сообщение.
        applied = await upsert(
            self.session,
            ChatStat,
            {
                "chat_id": chat_id,
                "day": day,
                "messages": messages,
                "commands": commands,
                "joins": joins,
                "leaves": leaves,
                "moderated": moderated,
            },
            index_elements=["chat_id", "day"],
            update_values={
                "messages": ChatStat.messages + messages,
                "commands": ChatStat.commands + commands,
                "joins": ChatStat.joins + joins,
                "leaves": ChatStat.leaves + leaves,
                "moderated": ChatStat.moderated + moderated,
            },
        )
        if not applied:
            row = await self.session.scalar(
                select(ChatStat).where(ChatStat.chat_id == chat_id, ChatStat.day == day)
            )
            if row is None:
                self.session.add(
                    ChatStat(
                        chat_id=chat_id,
                        day=day,
                        messages=messages,
                        commands=commands,
                        joins=joins,
                        leaves=leaves,
                        moderated=moderated,
                    )
                )
            else:
                row.messages += messages
                row.commands += commands
                row.joins += joins
                row.leaves += leaves
                row.moderated += moderated

    async def messages_on(self, chat_id: int, day: date) -> int:
        return int(
            await self.session.scalar(
                select(func.coalesce(ChatStat.messages, 0)).where(
                    ChatStat.chat_id == chat_id, ChatStat.day == day
                )
            )
            or 0
        )

    async def period_sum(self, chat_id: int, field: str, days: int = 7) -> int:
        column = getattr(ChatStat, field)
        since = date.today() - timedelta(days=days - 1)
        return int(
            await self.session.scalar(
                select(func.coalesce(func.sum(column), 0)).where(
                    ChatStat.chat_id == chat_id, ChatStat.day >= since
                )
            )
            or 0
        )

    async def summary(self, chat_id: int) -> dict[str, int | str]:
        members = int(
            await self.session.scalar(
                select(func.count())
                .select_from(ChatMember)
                .where(ChatMember.chat_id == chat_id, ChatMember.is_bot.is_(False))
            )
            or 0
        )
        today = date.today()
        week = 7
        top = await self.session.scalar(
            select(ChatMember.full_name)
            .where(ChatMember.chat_id == chat_id, ChatMember.is_bot.is_(False))
            .order_by(ChatMember.message_count.desc())
            .limit(1)
        )
        economy = int(
            await self.session.scalar(
                select(func.coalesce(func.sum(Wallet.balance), 0)).where(Wallet.chat_id == chat_id)
            )
            or 0
        )
        return {
            "members": members,
            "messages_today": await self.messages_on(chat_id, today),
            "messages_week": await self.period_sum(chat_id, "messages", week),
            "joins": await self.period_sum(chat_id, "joins", week),
            "leaves": await self.period_sum(chat_id, "leaves", week),
            "moderated": await self.period_sum(chat_id, "moderated", week),
            "economy": economy,
            "top_user": escape_html(top) if top else "—",
        }

    async def top_members(self, chat_id: int, limit: int = 10) -> list[ChatMember]:
        rows = await self.session.scalars(
            select(ChatMember)
            .where(ChatMember.chat_id == chat_id, ChatMember.is_bot.is_(False))
            .order_by(ChatMember.message_count.desc())
            .limit(limit)
        )
        return list(rows)

    async def moderation_stats(self, chat_id: int, days: int = 7) -> dict[str, int]:
        since = date.today() - timedelta(days=days - 1)
        rows = await self.session.execute(
            select(ModerationLog.action, func.count())
            .where(ModerationLog.chat_id == chat_id, func.date(ModerationLog.created_at) >= since)
            .group_by(ModerationLog.action)
        )
        return {action: int(count) for action, count in rows.all()}

    async def economy_stats(self, chat_id: int, limit: int = 10) -> dict[str, int]:
        wallets = await self.session.execute(
            select(func.count(), func.coalesce(func.sum(Wallet.balance), 0)).where(
                Wallet.chat_id == chat_id
            )
        )
        count, total = wallets.one()
        earned = await self.session.scalar(
            select(func.coalesce(func.sum(Wallet.total_earned), 0)).where(Wallet.chat_id == chat_id)
        )
        return {
            "wallets": int(count or 0),
            "balance": int(total or 0),
            "earned": int(earned or 0),
        }
