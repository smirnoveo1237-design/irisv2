"""Интеграционные тесты: полный путь апдейта Telegram → middleware → команда."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from aiogram import Bot
from aiogram.types import Chat, Message, Update
from aiogram.types import User as TgUser
from sqlalchemy import func, select

from app.database.models import AuditLog, ChatMember
from app.main import build_dispatcher
from app.modules.loader import load_routers

CHAT_ID = -100111
USER_ID = 900


def fresh_dispatcher(container):
    """Новый Dispatcher для теста: глобальные роутеры уже привязаны к предыдущему."""
    for router in load_routers():
        router._parent_router = None
    return build_dispatcher(container)


@pytest.fixture
def captured(monkeypatch) -> list[str]:
    messages: list[str] = []

    async def fake_answer(self, text, **kwargs):
        messages.append(text)
        return None

    monkeypatch.setattr(Message, "answer", fake_answer)
    return messages


async def _feed(dispatcher, bot: Bot, text: str, *, chat_type: str = "supergroup", user_id: int = USER_ID):
    message = Message(
        message_id=42,
        date=datetime.now(UTC),
        chat=Chat(id=CHAT_ID, type=chat_type, title="Тестовая группа"),
        from_user=TgUser(id=user_id, is_bot=False, first_name="Иван", last_name="Тестов"),
        text=text,
    )
    await dispatcher.feed_update(bot, Update(update_id=1, message=message))


@pytest.mark.asyncio
async def test_profile_command_end_to_end(container, captured) -> None:
    bot = Bot(token="123456789:AAFakeTokenForTests_1234567890")
    dispatcher = fresh_dispatcher(container)
    try:
        await _feed(dispatcher, bot, "профиль")
        assert captured, "команда должна ответить"
        assert "Тестов" in captured[0] or "Иван" in captured[0]
        async with container.db.session_scope() as session:
            member = await session.scalar(
                select(ChatMember).where(
                    ChatMember.chat_id == CHAT_ID, ChatMember.user_id == USER_ID
                )
            )
            assert member is not None and member.message_count >= 1
            audits = await session.scalar(
                select(func.count()).select_from(AuditLog).where(AuditLog.action == "command")
            )
            assert audits == 1
    finally:
        await bot.session.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["профиль", "!профиль", ".профиль", "ирис профиль", "/профиль"])
async def test_all_command_forms(container, captured, text: str) -> None:
    bot = Bot(token="123456789:AAFakeTokenForTests_1234567890")
    dispatcher = fresh_dispatcher(container)
    try:
        await _feed(dispatcher, bot, text)
        assert captured, f"форма {text!r} должна распознаваться"
        assert "Профиль" in captured[0] or "Профиль" in captured[0] or "Уровень" in captured[0]
    finally:
        await bot.session.close()


@pytest.mark.asyncio
async def test_plain_message_ignored(container, captured) -> None:
    bot = Bot(token="123456789:AAFakeTokenForTests_1234567890")
    dispatcher = fresh_dispatcher(container)
    try:
        await _feed(dispatcher, bot, "привет, как у вас дела?")
        # Обычное сообщение не должно вызывать командных ответов.
        assert all("Профиль" not in text and "Уровень" not in text for text in captured)
    finally:
        await bot.session.close()


@pytest.mark.asyncio
async def test_shipper_includes_iris(container, captured) -> None:
    bot = Bot(token="123456789:AAFakeTokenForTests_1234567890")
    dispatcher = fresh_dispatcher(container)
    try:
        await _feed(dispatcher, bot, "шипперим")
        assert captured
        text = captured[0]
        assert "IrisV2" in text
        assert "+" in text
        assert "%" not in text
    finally:
        await bot.session.close()


@pytest.mark.asyncio
async def test_who_answers_with_member(container, captured) -> None:
    bot = Bot(token="123456789:AAFakeTokenForTests_1234567890")
    dispatcher = fresh_dispatcher(container)
    try:
        await _feed(dispatcher, bot, "кто самый умный")
        assert captured
        assert "Иван" in captured[-1] or "кто" in captured[-1].lower()
    finally:
        await bot.session.close()


@pytest.mark.asyncio
async def test_shipper_with_members(container, captured) -> None:
    async with container.db.session_scope() as session:
        await container.chats.ensure(
            session, chat_id=CHAT_ID, title="Тестовая группа", chat_type="supergroup"
        )
        for index, name in enumerate(("Анна", "Борис", "Вера"), start=1):
            user_id = 800 + index
            await container.members(session).ensure_user(
                user_id=user_id, username=f"u{index}", first_name=name, last_name=None
            )
            await container.members(session).touch(
                chat_id=CHAT_ID, user_id=user_id, full_name=name, verified=True
            )

    bot = Bot(token="123456789:AAFakeTokenForTests_1234567890")
    dispatcher = fresh_dispatcher(container)
    try:
        await _feed(dispatcher, bot, "шипперим")
        assert captured
        text = captured[-1]
        assert "%" not in text
        assert "+" in text
        assert sum(1 for name in ("Анна", "Борис", "Вера", "Иван", "IrisV2") if name in text) == 2
    finally:
        await bot.session.close()


@pytest.mark.asyncio
async def test_admin_command_denied_for_member(container, captured) -> None:
    bot = Bot(token="123456789:AAFakeTokenForTests_1234567890")
    dispatcher = fresh_dispatcher(container)
    try:
        await _feed(dispatcher, bot, "бан @someone")
        assert captured
        assert "прав" in captured[0].lower()
    finally:
        await bot.session.close()


@pytest.mark.asyncio
async def test_daily_bonus_twice(container, captured) -> None:
    bot = Bot(token="123456789:AAFakeTokenForTests_1234567890")
    dispatcher = fresh_dispatcher(container)
    try:
        await _feed(dispatcher, bot, "бонус")
        await container.cache.delete(f"cmd_cd:{CHAT_ID}:{USER_ID}:бонус")
        await _feed(dispatcher, bot, "бонус")
        assert len(captured) >= 2
        assert "+50" in captured[0]
        assert "уже" in captured[-1].lower()
    finally:
        await bot.session.close()


@pytest.mark.asyncio
async def test_bare_commands_can_be_disabled(container, captured) -> None:
    bot = Bot(token="123456789:AAFakeTokenForTests_1234567890")
    dispatcher = fresh_dispatcher(container)
    try:
        await _feed(dispatcher, bot, "!профиль")
        assert captured
        async with container.db.session_scope() as session:
            await container.chats.update(session, CHAT_ID, bare_commands=False)
        captured.clear()
        await _feed(dispatcher, bot, "профиль")
        assert all("Профиль" not in text and "Уровень" not in text for text in captured)
        await container.cache.delete(f"cmd_cd:{CHAT_ID}:{USER_ID}:профиль")
        await _feed(dispatcher, bot, "ирис профиль")
        assert any("Уровень" in text or "Профиль" in text for text in captured)
    finally:
        await bot.session.close()
