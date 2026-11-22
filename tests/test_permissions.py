"""Тесты прав: владелец, пользовательские роли, обычный участник."""

from __future__ import annotations

import pytest

CHAT_ID = -100800
ADMIN = 601
MEMBER = 602
MODERATOR = 603


@pytest.mark.asyncio
async def test_owner_has_all_permissions(container) -> None:
    async with container.db.session_scope() as session:
        await container.chats.ensure(session, chat_id=CHAT_ID, title="Perm", chat_type="supergroup")
        permissions = container.permissions(session)
        assert permissions.is_owner(1) is True
        assert await permissions.has_permission(CHAT_ID, 1, "ban") is True


@pytest.mark.asyncio
async def test_regular_member_has_no_permissions(container) -> None:
    async with container.db.session_scope() as session:
        await container.chats.ensure(session, chat_id=CHAT_ID, title="Perm", chat_type="supergroup")
        permissions = container.permissions(session)
        assert await permissions.has_permission(CHAT_ID, MEMBER, "ban") is False
        assert await permissions.has_permission(CHAT_ID, MEMBER, "settings") is False


@pytest.mark.asyncio
async def test_custom_role_grants_permission(container) -> None:
    async with container.db.session_scope() as session:
        await container.chats.ensure(session, chat_id=CHAT_ID, title="Perm", chat_type="supergroup")
        permissions = container.permissions(session)
        role = await permissions.create_role(CHAT_ID, "Модератор", ["ban", "mute", "moderation"])
        await permissions.grant_role(CHAT_ID, MODERATOR, role)
        assert await permissions.has_permission(CHAT_ID, MODERATOR, "ban") is True
        assert await permissions.has_permission(CHAT_ID, MODERATOR, "settings") is False
        await permissions.revoke_role(CHAT_ID, MODERATOR, role)
        assert await permissions.has_permission(CHAT_ID, MODERATOR, "ban") is False


@pytest.mark.asyncio
async def test_wildcard_role(container) -> None:
    async with container.db.session_scope() as session:
        await container.chats.ensure(session, chat_id=CHAT_ID, title="Perm", chat_type="supergroup")
        permissions = container.permissions(session)
        role = await permissions.create_role(CHAT_ID, "Всё", ["*"])
        await permissions.grant_role(CHAT_ID, MODERATOR, role)
        for permission in ("ban", "settings", "economy_admin"):
            assert await permissions.has_permission(CHAT_ID, MODERATOR, permission) is True


@pytest.mark.asyncio
async def test_module_flags(container) -> None:
    async with container.db.session_scope() as session:
        _, settings = await container.chats.ensure(
            session, chat_id=CHAT_ID, title="Perm", chat_type="supergroup"
        )
        assert container.chats.module_enabled(settings, "economy") is True
        settings.economy_enabled = False
        assert container.chats.module_enabled(settings, "economy") is False
        assert container.chats.module_enabled(None, "economy") is True
