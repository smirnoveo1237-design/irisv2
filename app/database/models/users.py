"""Пользователи, группы, участники и настройки групп."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, BigIntPK, TimestampMixin, utcnow


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))
    language_code: Mapped[str | None] = mapped_column(String(8))
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    @property
    def display_name(self) -> str:
        name = " ".join(part for part in (self.first_name, self.last_name) if part)
        return name or (f"@{self.username}" if self.username else str(self.id))


class Chat(Base, TimestampMixin):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    title: Mapped[str | None] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(32), default="supergroup", nullable=False)
    username: Mapped[str | None] = mapped_column(String(64))
    locale: Mapped[str] = mapped_column(String(8), default="ru", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    member_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class ChatSettings(Base):
    __tablename__ = "chat_settings"

    chat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chats.id", ondelete="CASCADE"), primary_key=True
    )
    locale: Mapped[str] = mapped_column(String(8), default="ru", nullable=False)

    # --- Команды ---
    command_prefixes: Mapped[list] = mapped_column(JSON, default=lambda: ["", "!", "."], nullable=False)
    command_triggers: Mapped[list] = mapped_column(
        JSON, default=lambda: ["ирис", "iris"], nullable=False
    )
    bare_commands: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # --- Модерация ---
    welcome_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    welcome_text: Mapped[str | None] = mapped_column(Text)
    goodbye_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    goodbye_text: Mapped[str | None] = mapped_column(Text)
    captcha_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    captcha_timeout: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    max_warnings: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    warn_action: Mapped[str] = mapped_column(String(16), default="mute", nullable=False)
    mute_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    ship_cooldown: Mapped[int] = mapped_column(
        Integer, default=30, server_default="30", nullable=False
    )
    log_channel_id: Mapped[int | None] = mapped_column(BigInteger)

    # --- Антиспам ---
    antiflood_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    flood_limit: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    flood_window: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    antiflood_action: Mapped[str] = mapped_column(String(16), default="mute", nullable=False)
    antispam_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    antilink_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    anticaps_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    antiphishing_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    stop_words: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # --- Модули ---
    levels_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    economy_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    social_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    games_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    analytics_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    automation_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ai_history_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class ChatMember(Base):
    __tablename__ = "chat_members"
    __table_args__ = (
        UniqueConstraint("chat_id", "user_id", name="uq_chat_members_chat_user"),
        Index("ix_chat_members_chat_last_seen", "chat_id", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    username: Mapped[str | None] = mapped_column(String(64))
    full_name: Mapped[str | None] = mapped_column(String(255))
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="member", nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChatStat(Base):
    """Суточная агрегация активности — дешёвая основа для аналитики."""

    __tablename__ = "chat_stats"
    __table_args__ = (UniqueConstraint("chat_id", "day", name="uq_chat_stats_chat_day"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)
    messages: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    commands: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    joins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    leaves: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    moderated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active_users: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class UserDayStat(Base):
    """Активность участника по дням: турниры, квесты, «топ недели». """

    __tablename__ = "user_day_stats"
    __table_args__ = (
        UniqueConstraint("chat_id", "user_id", "day", name="uq_user_day_stats"),
        Index("ix_user_day_stats_chat_day", "chat_id", "day"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    messages: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
