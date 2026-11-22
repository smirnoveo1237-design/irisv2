#!/bin/sh
# Точка входа контейнера: дождаться БД, применить миграции, запустить бота.
set -e

echo "[entrypoint] ожидание базы данных..."
python scripts/wait_for_db.py

echo "[entrypoint] применение миграций..."
alembic upgrade head

echo "[entrypoint] запуск IrisV2..."
exec python -m app.main
