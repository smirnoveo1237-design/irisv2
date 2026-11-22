#!/usr/bin/env python
"""Создание схемы БД без Alembic (только для локальной разработки).

В production используйте `alembic upgrade head`.
"""

from __future__ import annotations

import asyncio

from app.core.db import Database
from app.core.settings import get_settings
from app.database import models  # noqa: F401
from app.database.base import Base


async def main() -> None:
    settings = get_settings()
    database = Database(settings.database_url)
    try:
        await database.create_all()
        async with database.engine.connect() as connection:
            from sqlalchemy import text

            if database.dialect == "sqlite":
                result = await connection.execute(
                    text(
                        "SELECT count(*) FROM sqlite_master "
                        "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                    )
                )
            else:
                result = await connection.execute(
                    text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
                )
            print(f"Таблиц в базе: {result.scalar()}")
        print(f"Моделей в метаданных: {len(Base.metadata.tables)}")
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
