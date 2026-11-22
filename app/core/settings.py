"""Конфигурация IrisV2 (Pydantic Settings)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)
from pydantic_settings.sources import DotEnvSettingsSource, EnvSettingsSource


def _split_list(value: Any) -> Any:
    """Разбирает список из строки: «a, b, c» или JSON-массива ["a", "b"]."""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return parsed
        return [item.strip() for item in stripped.split(",") if item.strip()]
    return value


class _RawValuesMixin:
    """Не декодирует значения как JSON.

    pydantic-settings по умолчанию требует JSON для list-полей, из-за чего
    привычная запись `IRIS_COMMAND_PREFIXES=!,.,$` падает с SettingsError.
    Здесь значения отдаются строками, а списки разбирают валидаторы выше.
    """

    def prepare_field_value(
        self, field_name: str, field: Any, value: Any, value_is_complex: bool
    ) -> Any:
        return value


class RawEnvSource(_RawValuesMixin, EnvSettingsSource):
    pass


class RawDotEnvSource(_RawValuesMixin, DotEnvSettingsSource):
    pass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="IRIS_",
        extra="ignore",
    )

    bot_token: str = ""
    bot_username: str = "IrisV2Bot"
    owner_ids: list[int] = Field(default_factory=list)
    support_chat_id: int | None = None

    database_url: str = "postgresql+asyncpg://iris:iris@localhost:5432/iris"
    redis_url: str = ""

    env: str = "dev"
    log_level: str = "INFO"
    log_json: bool = False
    default_locale: str = "ru"
    timezone: str = "Europe/Moscow"

    # --- Webhook / Render -------------------------------------------------
    webhook_enabled: bool = False
    webhook_url: str = ""
    webhook_secret: str = ""
    webhook_path: str = "/telegram/webhook"
    drop_pending_updates: bool = False
    port: int = Field(8080, validation_alias=AliasChoices("PORT", "IRIS_PORT"))
    scheduler_tick: int = 20
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_recycle: int = 300

    command_prefixes: list[str] = Field(default_factory=lambda: ["", "!", "."])
    command_triggers: list[str] = Field(default_factory=lambda: ["ирис", "iris"])
    max_bare_length: int = 200

    ai_enabled: bool = False
    ai_base_url: str = "https://api.openai.com/v1"
    ai_api_key: str = ""
    ai_model: str = "gpt-4o-mini"
    ai_max_tokens: int = 600
    ai_timeout: float = 30.0

    # --- Мультипровайдерный ИИ (порядок в AIService) ---------------------
    groq_api_key: str = Field(
        "", validation_alias=AliasChoices("GROQ_API_KEY", "IRIS_GROQ_API_KEY")
    )
    groq_api_key_2: str = Field(
        "", validation_alias=AliasChoices("GROQ_API_KEY_2", "IRIS_GROQ_API_KEY_2")
    )
    groq_model: str = Field(
        "openai/gpt-oss-120b",
        validation_alias=AliasChoices("GROQ_MODEL", "IRIS_GROQ_MODEL"),
    )
    groq_model_fallback: str = Field(
        "", validation_alias=AliasChoices("GROQ_MODEL_FALLBACK", "IRIS_GROQ_MODEL_FALLBACK")
    )
    openrouter_api_key: str = Field(
        "", validation_alias=AliasChoices("OPENROUTER_API_KEY", "IRIS_OPENROUTER_API_KEY")
    )
    openrouter_api_key_2: str = Field(
        "",
        validation_alias=AliasChoices("OPENROUTER_API_KEY_2", "IRIS_OPENROUTER_API_KEY_2"),
    )
    openrouter_model: str = Field(
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        validation_alias=AliasChoices("OPENROUTER_MODEL", "IRIS_OPENROUTER_MODEL"),
    )
    tokenharbor_api_key: str = Field(
        "", validation_alias=AliasChoices("TOKENHARBOR_API_KEY", "IRIS_TOKENHARBOR_API_KEY")
    )
    tokenharbor_base_url: str = Field(
        "https://tokenharbor.ai/v1",
        validation_alias=AliasChoices("TOKENHARBOR_BASE_URL", "IRIS_TOKENHARBOR_BASE_URL"),
    )
    tokenharbor_model: str = Field(
        "", validation_alias=AliasChoices("TOKENHARBOR_MODEL", "IRIS_TOKENHARBOR_MODEL")
    )
    gemini_api_key: str = Field(
        "", validation_alias=AliasChoices("GEMINI_API_KEY", "IRIS_GEMINI_API_KEY")
    )
    gemini_models: list[str] = Field(
        default_factory=lambda: [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
        ],
        validation_alias=AliasChoices("GEMINI_MODELS", "IRIS_GEMINI_MODELS"),
    )
    pollinations_model: str = Field(
        "openai", validation_alias=AliasChoices("POLLINATIONS_MODEL", "IRIS_POLLINATIONS_MODEL")
    )

    backup_dir: str = "./backups"

    # Значения по умолчанию для новых групп
    default_mute_minutes: int = 60
    default_max_warnings: int = 3
    daily_bonus_base: int = 50
    daily_bonus_streak_step: int = 10

    @field_validator("support_chat_id", mode="before")
    @classmethod
    def _empty_optional_int(cls, value: Any) -> Any:
        if value == "" or value is None:
            return None
        return value

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        value = value.strip()
        if value.startswith("postgres://"):
            value = "postgresql+asyncpg://" + value[len("postgres://") :]
        elif value.startswith("postgresql://"):
            value = "postgresql+asyncpg://" + value[len("postgresql://") :]
        # Neon/Supabase отдают sslmode=require, asyncpg понимает ssl=require.
        if value.startswith("postgresql+asyncpg://") and "sslmode=" in value:
            value = value.replace("sslmode=", "ssl=")
        return value

    @field_validator("command_prefixes", "command_triggers", "gemini_models", mode="before")
    @classmethod
    def _validate_lists(cls, value: Any) -> Any:
        return _split_list(value)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Подменяет источники на версии без JSON-декодирования списков."""
        prefix = cls.model_config.get("env_prefix")
        return (
            init_settings,
            RawEnvSource(settings_cls, env_prefix=prefix),
            RawDotEnvSource(
                settings_cls,
                env_file=cls.model_config.get("env_file"),
                env_file_encoding=cls.model_config.get("env_file_encoding"),
                env_prefix=prefix,
            ),
            file_secret_settings,
        )

    @field_validator("owner_ids", mode="before")
    @classmethod
    def _validate_owner_ids(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [int(item) for item in _split_list(value)]
        return value

    @field_validator("command_triggers", "command_prefixes")
    @classmethod
    def _normalize(cls, value: list[str]) -> list[str]:
        return [item.lower() for item in value]

    @property
    def is_production(self) -> bool:
        return self.env.lower() in {"prod", "production"}

    @property
    def backup_path(self) -> Path:
        return Path(self.backup_dir)

    @property
    def access_token(self) -> str:
        if not self.bot_token:
            raise RuntimeError(
                "IRIS_BOT_TOKEN не задан. Скопируйте .env.example в .env и укажите токен бота."
            )
        return self.bot_token


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
