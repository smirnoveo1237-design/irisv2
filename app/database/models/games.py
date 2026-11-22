"""Игровые сущности: квесты, прогресс, активные игры."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, BigIntPK, utcnow


class Quest(Base):
    __tablename__ = "quests"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    goal_type: Mapped[str] = mapped_column(String(32), default="messages", nullable=False)
    goal_value: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    reward_amount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reward_xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    period: Mapped[str] = mapped_column(String(16), default="daily", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class QuestProgress(Base):
    __tablename__ = "quest_progress"
    __table_args__ = (UniqueConstraint("quest_id", "chat_id", "user_id", "day", name="uq_quest_progress"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    quest_id: Mapped[int] = mapped_column(
        ForeignKey("quests.id", ondelete="CASCADE"), nullable=False
    )
    chat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Game(Base):
    __tablename__ = "games"
    __table_args__ = ()

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    host_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    opponent_id: Mapped[int | None] = mapped_column(BigInteger)
    stake: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    state: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    winner_id: Mapped[int | None] = mapped_column(BigInteger)
    message_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
