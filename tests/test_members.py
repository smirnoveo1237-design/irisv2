"""Тесты реестра участников: статистика и синхронизация администраторов."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

CHAT_ID = -100555


def admin(user_id: int, name: str, username: str | None = None, status: str = "administrator"):
    user = SimpleNamespace(
        id=user_id,
        is_bot=False,
        username=username,
        first_name=name,
        last_name=None,
        language_code="ru",
        full_name=name,
    )
    return SimpleNamespace(user=user, status=status)


class FakeBot:
    def __init__(self, admins) -> None:
        self.admins = admins
        self.calls = 0

    async def get_chat_administrators(self, chat_id: int):
        self.calls += 1
        return self.admins


@pytest.mark.asyncio
async def test_sync_admins_adds_users_and_members(container) -> None:
    async with container.db.session_scope() as session:
        await container.chats.ensure(session, chat_id=CHAT_ID, title="Reg", chat_type="supergroup")
        bot = FakeBot([admin(11, "Админ", "admin"), admin(12, "Владелец", "owner", "creator")])
        added = await container.members(session).sync_admins(bot, CHAT_ID)
        assert added == 2
        stats = await container.members(session).stats(CHAT_ID)
        assert stats["total"] == 2
        assert stats["admins"] == 2
        assert stats["verified"] == 2


@pytest.mark.asyncio
async def test_sync_admins_is_idempotent(container) -> None:
    async with container.db.session_scope() as session:
        await container.chats.ensure(session, chat_id=CHAT_ID, title="Reg", chat_type="supergroup")
        bot = FakeBot([admin(11, "Админ", "admin")])
        assert await container.members(session).sync_admins(bot, CHAT_ID) == 1
        assert await container.members(session).sync_admins(bot, CHAT_ID) == 0
        assert (await container.members(session).stats(CHAT_ID))["total"] == 1


@pytest.mark.asyncio
async def test_stats_ignores_bots(container) -> None:
    async with container.db.session_scope() as session:
        await container.chats.ensure(session, chat_id=CHAT_ID, title="Reg", chat_type="supergroup")
        await container.members(session).touch(
            chat_id=CHAT_ID, user_id=21, full_name="Человек", status="member"
        )
        await container.members(session).touch(
            chat_id=CHAT_ID, user_id=22, full_name="Бот", is_bot=True
        )
        stats = await container.members(session).stats(CHAT_ID)
        assert stats["total"] == 1
        assert stats["bots"] == 1


@pytest.mark.asyncio
async def test_sync_tolerates_missing_rights(container) -> None:
    class FailingBot:
        async def get_chat_administrators(self, chat_id: int):
            raise RuntimeError("not enough rights")

    async with container.db.session_scope() as session:
        await container.chats.ensure(session, chat_id=CHAT_ID, title="Reg", chat_type="supergroup")
        assert await container.members(session).sync_admins(FailingBot(), CHAT_ID) == 0
