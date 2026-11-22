#!/usr/bin/env python
"""Ожидание готовности PostgreSQL (используется в docker/entrypoint.sh)."""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.settings import get_settings

ATTEMPTS = 40
DELAY = 1.5


async def wait() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        for attempt in range(1, ATTEMPTS + 1):
            try:
                async with engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))
                print(f"[wait_for_db] база готова (попытка {attempt})")
                return
            except Exception as exc:  # noqa: BLE001 - ждём именно сетевую готовность
                print(f"[wait_for_db] попытка {attempt}/{ATTEMPTS}: {exc.__class__.__name__}")
                await asyncio.sleep(DELAY)
        raise SystemExit("[wait_for_db] база недоступна")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(wait())
    except KeyboardInterrupt:
        sys.exit(1)
