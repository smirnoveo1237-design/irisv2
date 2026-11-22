#!/usr/bin/env python
"""Ожидание готовности PostgreSQL (используется в docker/entrypoint.sh)."""

from __future__ import annotations

import asyncio
import sys
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.settings import get_settings

ATTEMPTS = 15
DELAY = 1.0


def _host_and_password(url: str) -> tuple[str, str]:
    parsed = urlparse(url.replace("postgresql+asyncpg", "postgresql"))
    return parsed.hostname or "", parsed.password or ""


def _safe_error(exc: Exception, password: str) -> str:
    message = f"{type(exc).__name__}: {str(exc)}"
    if password:
        message = message.replace(password, "***")
    return message[:240]


async def wait() -> None:
    settings = get_settings()
    host, password = _host_and_password(settings.database_url)

    if settings.is_production and host in {"localhost", "127.0.0.1", "::1"}:
        print(
            "[wait_for_db] IRIS_DATABASE_URL не задан или указывает на localhost. "
            "Добавьте строку Neon/PostgreSQL в Render Dashboard → Environment.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    print(f"[wait_for_db] подключаюсь к host={host or '?'} (попыток: {ATTEMPTS})", flush=True)
    try:
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    except Exception as exc:  # noqa: BLE001 - некорректный URL
        print(f"[wait_for_db] ошибка URL: {_safe_error(exc, password)}", file=sys.stderr)
        raise SystemExit(2) from exc

    try:
        for attempt in range(1, ATTEMPTS + 1):
            try:
                async with engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))
                print(f"[wait_for_db] база готова (попытка {attempt})", flush=True)
                return
            except Exception as exc:  # noqa: BLE001 - ждём именно сетевую готовность
                print(
                    f"[wait_for_db] попытка {attempt}/{ATTEMPTS}: {_safe_error(exc, password)}",
                    flush=True,
                )
                await asyncio.sleep(DELAY)
        print(
            "[wait_for_db] база недоступна. Проверьте IRIS_DATABASE_URL, SSL и доступ из интернета.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(wait())
    except KeyboardInterrupt:
        sys.exit(1)
