"""Проверка догоняющей миграции SQLite для новых колонок."""

from __future__ import annotations

from sqlalchemy import text

from app.core.db import Database


async def _columns(database: Database, table: str) -> set[str]:
    async with database.engine.connect() as conn:
        result = await conn.execute(text(f"PRAGMA table_info({table})"))
        return {row[1] for row in result.fetchall()}


async def test_sqlite_adds_missing_ship_cooldown(tmp_path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'legacy.db'}"
    database = Database(url)
    await database.create_all()
    assert "ship_cooldown" in await _columns(database, "chat_settings")

    # Имитируем старую базу, созданную до появления настройки.
    async with database.engine.begin() as conn:
        await conn.execute(text("ALTER TABLE chat_settings DROP COLUMN ship_cooldown"))
    await database.dispose()

    reopened = Database(url)
    await reopened.create_all()
    assert "ship_cooldown" in await _columns(reopened, "chat_settings")
    await reopened.dispose()
