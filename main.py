#!/usr/bin/env python
"""Запуск IrisV2 из корня проекта.

    python main.py                # обычный запуск
    python main.py --create-db    # первый запуск: создать таблицы (dev/SQLite)

Эквивалент: python -m app.main
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Позволяет запускать файл напрямую, даже если пакет не установлен через pip.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.main import main  # noqa: E402


def run() -> None:
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nОстановлено.")
    except RuntimeError as exc:
        print(f"\n❌ {exc}", file=sys.stderr)
        print("Проверьте файл .env в папке проекта.", file=sys.stderr)
        raise SystemExit(1) from None
    except OSError as exc:
        print(f"\n❌ Не удалось подключиться к базе данных: {exc}", file=sys.stderr)
        print("PostgreSQL не запущен? Запустите без него:", file=sys.stderr)
        print("   python main.py --sqlite", file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    run()
