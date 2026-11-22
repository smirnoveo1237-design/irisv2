"""Тесты отношений: брак в профиле и выборка пар."""

from __future__ import annotations

import pytest

from app.database.models import Marriage
from app.modules.social.handlers import _marriage_of
from app.services.profiles import ProfileService

CHAT_ID = -100666
USER_A = 71
USER_B = 72


async def prepare(container) -> None:
    async with container.db.session_scope() as session:
        await container.chats.ensure(session, chat_id=CHAT_ID, title="Love", chat_type="supergroup")
        await container.members(session).ensure_user(
            user_id=USER_A, username="a", first_name="Аня", last_name=None
        )
        await container.members(session).ensure_user(
            user_id=USER_B, username="b", first_name="Борис", last_name=None
        )


@pytest.mark.asyncio
async def test_profile_shows_partner(container) -> None:
    await prepare(container)
    async with container.db.session_scope() as session:
        session.add(Marriage(chat_id=CHAT_ID, user1_id=USER_A, user2_id=USER_B, status="active"))
        await session.flush()
        card = await ProfileService(session, container).card(CHAT_ID, USER_A, "ru")
        assert "Борис" in card
        assert "В браке" in card


@pytest.mark.asyncio
async def test_marriage_lookup(container) -> None:
    await prepare(container)
    async with container.db.session_scope() as session:
        row = await _marriage_of(session, CHAT_ID, USER_A)
        assert row is None
        session.add(Marriage(chat_id=CHAT_ID, user1_id=USER_A, user2_id=USER_B, status="active"))
        await session.flush()
        row = await _marriage_of(session, CHAT_ID, USER_B)
        assert row is not None
        assert row.user1_id == USER_A
