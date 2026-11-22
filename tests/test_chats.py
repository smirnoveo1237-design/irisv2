"""Тесты настроек групп: значения по умолчанию, кэш, префиксы."""

from __future__ import annotations

import pytest

CHAT_ID = -101000


@pytest.mark.asyncio
async def test_defaults_created(container) -> None:
    async with container.db.session_scope() as session:
        chat, settings = await container.chats.ensure(
            session, chat_id=CHAT_ID, title="Настройки", chat_type="supergroup", username="test"
        )
        assert chat.title == "Настройки"
        assert settings.locale == "ru"
        assert settings.antiflood_enabled is True
        assert settings.antispam_enabled is True
        assert settings.captcha_enabled is False
        assert settings.command_prefixes == ["", "!", "."]
        assert "ирис" in settings.command_triggers
        assert settings.max_warnings == 3


@pytest.mark.asyncio
async def test_update_and_cache_invalidation(container) -> None:
    async with container.db.session_scope() as session:
        await container.chats.ensure(session, chat_id=CHAT_ID, title="T", chat_type="supergroup")
        cached = await container.chats.settings(session, CHAT_ID)
        assert cached is not None
        await container.chats.update(session, CHAT_ID, antilink_enabled=True, mute_minutes=15)
        fresh = await container.chats.settings(session, CHAT_ID)
        assert fresh.antilink_enabled is True
        assert fresh.mute_minutes == 15


@pytest.mark.asyncio
async def test_prefixes_per_chat(container) -> None:
    async with container.db.session_scope() as session:
        await container.chats.ensure(session, chat_id=CHAT_ID, title="T", chat_type="supergroup")
        await container.chats.update(session, CHAT_ID, command_prefixes=["", "$"])
        prefixes, triggers = await container.chats.prefixes(session, CHAT_ID)
        assert prefixes == ["", "$"]
        assert triggers


@pytest.mark.asyncio
async def test_unknown_setting_rejected(container) -> None:
    async with container.db.session_scope() as session:
        await container.chats.ensure(session, chat_id=CHAT_ID, title="T", chat_type="supergroup")
        with pytest.raises(AttributeError):
            await container.chats.update(session, CHAT_ID, not_a_setting=True)


@pytest.mark.asyncio
async def test_module_enabled_flags(container) -> None:
    async with container.db.session_scope() as session:
        _, settings = await container.chats.ensure(
            session, chat_id=CHAT_ID, title="T", chat_type="supergroup"
        )
        assert container.chats.module_enabled(settings, "games") is True
        settings.games_enabled = False
        assert container.chats.module_enabled(settings, "games") is False
