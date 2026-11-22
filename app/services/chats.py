"""Группы и их настройки с коротким кэшем в процессе."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.texts import texts
from app.database.models import Chat, ChatSettings
from app.database.utils import upsert

if TYPE_CHECKING:
    from app.container import Container


class ChatService:
    SETTINGS_TTL = 30.0

    def __init__(self, container: Container) -> None:
        self.container = container
        self._cache: dict[int, tuple[float, Chat, ChatSettings]] = {}

    def invalidate(self, chat_id: int) -> None:
        self._cache.pop(chat_id, None)

    async def settings(self, session: AsyncSession, chat_id: int) -> ChatSettings | None:
        cached = self._cache.get(chat_id)
        if cached and time.monotonic() - cached[0] < self.SETTINGS_TTL:
            return cached[2]
        settings = await session.get(ChatSettings, chat_id)
        if settings is not None:
            chat = cached[1] if cached else await session.get(Chat, chat_id)
            if chat is not None:
                self._cache[chat_id] = (time.monotonic(), chat, settings)
        return settings

    async def ensure(
        self,
        session: AsyncSession,
        *,
        chat_id: int,
        title: str | None = None,
        chat_type: str = "supergroup",
        username: str | None = None,
    ) -> tuple[Chat, ChatSettings]:
        cached = self._cache.get(chat_id)
        if cached and time.monotonic() - cached[0] < self.SETTINGS_TTL:
            return cached[1], cached[2]

        defaults = self.container.settings
        chat = await session.get(Chat, chat_id)
        if chat is None:
            await upsert(
                session,
                Chat,
                {
                    "id": chat_id,
                    "title": title,
                    "type": chat_type,
                    "username": username,
                    "locale": defaults.default_locale,
                },
                index_elements=["id"],
            )
            chat = await session.get(Chat, chat_id)
        elif (title and chat.title != title) or (username and chat.username != username):
            chat.title = title or chat.title
            chat.username = username or chat.username
            chat.type = chat_type or chat.type

        settings = await session.get(ChatSettings, chat_id)
        if settings is None:
            await upsert(
                session,
                ChatSettings,
                {
                    "chat_id": chat_id,
                    "locale": (chat.locale if chat else defaults.default_locale),
                    "command_prefixes": list(defaults.command_prefixes),
                    "command_triggers": list(defaults.command_triggers),
                    "max_warnings": defaults.default_max_warnings,
                    "mute_minutes": defaults.default_mute_minutes,
                },
                index_elements=["chat_id"],
            )
            settings = await session.get(ChatSettings, chat_id)

        if chat is None or settings is None:  # pragma: no cover - защита от гонок
            raise RuntimeError(f"Не удалось создать настройки группы {chat_id}")

        if chat.title is None and title:
            chat.title = title

        self._cache[chat_id] = (time.monotonic(), chat, settings)
        return chat, settings

    async def update(self, session: AsyncSession, chat_id: int, **values: Any) -> ChatSettings:
        settings = await session.get(ChatSettings, chat_id)
        if settings is None:
            _, settings = await self.ensure(session, chat_id=chat_id)
        for key, value in values.items():
            if not hasattr(settings, key):
                raise AttributeError(f"У группы нет настройки {key}")
            setattr(settings, key, value)
        await session.flush()
        self.invalidate(chat_id)
        chat = await session.get(Chat, chat_id)
        if chat is not None:
            self._cache[chat_id] = (time.monotonic(), chat, settings)
        return settings

    async def prefixes(self, session: AsyncSession, chat_id: int) -> tuple[list[str], list[str]]:
        settings = await self.settings(session, chat_id)
        if settings is None:
            return list(self.container.settings.command_prefixes), list(
                self.container.settings.command_triggers
            )
        return list(settings.command_prefixes or []), list(settings.command_triggers or [])

    async def all_active(self, session: AsyncSession) -> list[Chat]:
        result = await session.scalars(select(Chat).where(Chat.is_active.is_(True)))
        return list(result)

    def locale(self, settings: ChatSettings | None) -> str:
        return settings.locale if settings and settings.locale else self.container.settings.default_locale

    def module_enabled(self, settings: ChatSettings | None, module: str) -> bool:
        if settings is None:
            return True
        mapping = {
            "economy": settings.economy_enabled,
            "profiles": settings.levels_enabled,
            "social": settings.social_enabled,
            "games": settings.games_enabled,
            "analytics": settings.analytics_enabled,
            "automation": settings.automation_enabled,
            "ai": settings.ai_enabled,
            "moderation": True,
            "antispam": settings.antispam_enabled,
            "settings": True,
            "shipper": True,
            "iris_who": True,
            "reports": True,
            "support": True,
            "giveaways": True,
            "menu": True,
        }
        return mapping.get(module, True)

    def localized_currency(self, locale: str) -> str:
        return texts.t(locale, "currency")
