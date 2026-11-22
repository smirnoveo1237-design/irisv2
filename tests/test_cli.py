"""Тесты флагов запуска."""

from __future__ import annotations

from app.core.settings import Settings
from app.main import SQLITE_URL, apply_cli_overrides


def make_settings() -> Settings:
    return Settings(
        bot_token="123456:TEST",
        database_url="postgresql+asyncpg://iris:iris@localhost:5432/iris",
        redis_url="redis://localhost:6379/0",
    )


def test_sqlite_flag_overrides_database_and_cache() -> None:
    settings = make_settings()
    enabled = apply_cli_overrides(settings, ["main.py", "--sqlite"])
    assert enabled is True
    assert settings.database_url == SQLITE_URL
    assert settings.redis_url == ""


def test_no_flag_keeps_configuration() -> None:
    settings = make_settings()
    enabled = apply_cli_overrides(settings, ["main.py"])
    assert enabled is False
    assert settings.database_url.startswith("postgresql")
    assert settings.redis_url.startswith("redis://")
