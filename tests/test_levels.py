"""Тесты уровней, опыта и достижений."""

from __future__ import annotations

import pytest

from app.services.levels import level_for_xp, xp_for_level, xp_to_next

CHAT_ID = -100700


def test_level_table() -> None:
    assert xp_for_level(1) == 0
    assert xp_for_level(2) == 50
    assert xp_for_level(3) == 150
    assert xp_for_level(4) == 300


def test_level_from_xp() -> None:
    assert level_for_xp(0) == 1
    assert level_for_xp(49) == 1
    assert level_for_xp(50) == 2
    assert level_for_xp(149) == 2
    assert level_for_xp(150) == 3
    assert level_for_xp(10_000) > 10


def test_xp_to_next() -> None:
    assert xp_to_next(0) == 50
    assert xp_to_next(50) == 100
    assert xp_to_next(150) == 150


@pytest.mark.asyncio
async def test_award_and_level_up(container) -> None:
    async with container.db.session_scope() as session:
        await container.chats.ensure(session, chat_id=CHAT_ID, title="Lvl", chat_type="supergroup")
        levels = container.levels(session)
        first = await levels.award(CHAT_ID, 501, xp=30)
        assert first.level == 1 and first.xp == 30 and not first.leveled_up
        second = await levels.award(CHAT_ID, 501, xp=30)
        assert second.level == 2 and second.leveled_up
        row = await levels.get(CHAT_ID, 501)
        assert row is not None and row.messages == 2
