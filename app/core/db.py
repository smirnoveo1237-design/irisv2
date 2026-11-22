"""Асинхронное подключение к базе данных."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.logging import get_logger

log = get_logger(__name__)


class Database:
    """Владелец engine и фабрики сессий.

    Один экземпляр создаётся при старте приложения (и в тестах — на временной БД),
    поэтому сервисы не зависят от глобального состояния.
    """

    def __init__(
        self,
        url: str,
        *,
        echo: bool = False,
        pool_size: int = 10,
        max_overflow: int = 20,
        pool_recycle: int = 300,
        static_pool: bool = False,
    ) -> None:
        self.url = url
        kwargs: dict = {
            "echo": echo,
            "future": True,
            "pool_pre_ping": True,
            "pool_recycle": pool_recycle,
        }
        if url.startswith("sqlite"):
            if static_pool or ":memory:" in url:
                from sqlalchemy.pool import StaticPool

                kwargs["poolclass"] = StaticPool
                kwargs["connect_args"] = {"check_same_thread": False}
        else:
            kwargs.update(pool_size=pool_size, max_overflow=max_overflow)
        self.engine: AsyncEngine = create_async_engine(url, **kwargs)
        self.session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self.engine, expire_on_commit=False, autoflush=False
        )

    def session(self) -> AsyncSession:
        return self.session_factory()

    @asynccontextmanager
    async def session_scope(self) -> AsyncIterator[AsyncSession]:
        session = self.session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def create_all(self) -> None:
        from app.database import models  # noqa: F401  (регистрация метаданных)
        from app.database.base import Base

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        if self.dialect == "sqlite":
            await self._ensure_sqlite_columns()
        log.info("Схема БД создана (create_all)")

    async def _ensure_sqlite_columns(self) -> None:
        """Догоняющая миграция локальной SQLite: create_all не добавляет колонки."""
        from sqlalchemy import text

        additions = {
            "chat_settings": {
                "ship_cooldown": "INTEGER NOT NULL DEFAULT 30",
            },
        }
        async with self.engine.begin() as conn:
            for table, columns in additions.items():
                result = await conn.execute(text(f"PRAGMA table_info({table})"))
                existing = {row[1] for row in result.fetchall()}
                for column, ddl in columns.items():
                    if column not in existing:
                        await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
                        log.info(
                            "SQLite: добавлена колонка",
                            extra={"table": table, "column": column},
                        )
            # Одноразовое включение ИИ для чатов, созданных до появления провайдеров.
            version = await conn.scalar(text("PRAGMA user_version"))
            if int(version or 0) < 1:
                await conn.execute(text("UPDATE chat_settings SET ai_enabled = 1"))
                await conn.execute(text("PRAGMA user_version = 1"))

    async def drop_all(self) -> None:
        from app.database import models  # noqa: F401
        from app.database.base import Base

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    async def dispose(self) -> None:
        await self.engine.dispose()

    @property
    def dialect(self) -> str:
        return self.engine.dialect.name
