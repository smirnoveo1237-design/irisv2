#!/usr/bin/env python
"""Резервная копия PostgreSQL через pg_dump.

Запуск:
    python scripts/backup.py            # копия в ./backups
    python scripts/backup.py --keep 14  # хранить 14 последних копий

Требует установленный pg_dump (в образе postgres он есть).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from app.core.settings import get_settings


def pg_connection(url: str) -> dict[str, str]:
    parsed = urlparse(url.replace("postgresql+asyncpg", "postgresql"))
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": parsed.username or "postgres",
        "password": parsed.password or "",
        "dbname": (parsed.path or "/postgres").lstrip("/"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Резервная копия IrisV2")
    parser.add_argument("--keep", type=int, default=7, help="сколько последних копий хранить")
    args = parser.parse_args()

    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        source = Path(settings.database_url.split("///")[-1])
        if not source.exists():
            print(f"Файл БД не найден: {source}", file=sys.stderr)
            return 1
        target = Path(settings.backup_dir) / f"iris_{datetime.now():%Y%m%d_%H%M%S}.sqlite"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        print(f"Резервная копия SQLite: {target}")
        return 0

    connection = pg_connection(settings.database_url)
    if shutil.which("pg_dump") is None:
        print("pg_dump не найден в PATH. Установите postgresql-client.", file=sys.stderr)
        return 2
    settings.backup_path.mkdir(parents=True, exist_ok=True)
    target = settings.backup_path / f"iris_{datetime.now():%Y%m%d_%H%M%S}.dump"

    env = os.environ.copy()
    env["PGPASSWORD"] = connection["password"]
    command = [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        "-h", connection["host"],
        "-p", connection["port"],
        "-U", connection["user"],
        "-f", str(target),
        connection["dbname"],
    ]
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"pg_dump ошибка: {result.stderr.strip()}", file=sys.stderr)
        return result.returncode

    copies = sorted(settings.backup_path.glob("iris_*.dump"), reverse=True)
    for old in copies[args.keep :]:
        old.unlink(missing_ok=True)
    print(f"Резервная копия создана: {target} ({target.stat().st_size} байт)")
    print(f"Восстановление: pg_restore --clean --if-exists -d <db> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
