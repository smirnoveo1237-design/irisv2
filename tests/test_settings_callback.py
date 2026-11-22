"""Тест кнопки «Настройки» в главном меню."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from aiogram import Bot
from aiogram.types import CallbackQuery, Chat, Message, Update
from aiogram.types import User as TgUser

from tests.test_dispatch import fresh_dispatcher


@pytest.mark.asyncio
async def test_menu_settings_opens_panel(container, monkeypatch) -> None:
    container.settings.owner_ids = [1]
    edited: list[str] = []
    answered: list[bool] = []

    async def fake_edit(self, text, **kwargs):
        edited.append(text)
        return None

    async def fake_answer(self, text=None, **kwargs):
        answered.append(True)
        return None

    monkeypatch.setattr(Message, "edit_text", fake_edit)
    monkeypatch.setattr(Message, "answer", fake_edit)
    monkeypatch.setattr(CallbackQuery, "answer", fake_answer)

    bot = Bot(token="123456789:AAFakeTokenForTests_1234567890")
    dispatcher = fresh_dispatcher(container)
    try:
        message = Message(
            message_id=30,
            date=datetime.now(UTC),
            chat=Chat(id=-100321, type="supergroup", title="Settings"),
            from_user=TgUser(id=1, is_bot=False, first_name="Owner"),
            text="меню",
        )
        callback = CallbackQuery(
            id="cb-1",
            from_user=TgUser(id=1, is_bot=False, first_name="Owner"),
            chat_instance="chat-instance",
            message=message,
            data="menu:settings",
        )
        await dispatcher.feed_update(
            bot, Update(update_id=30, callback_query=callback)
        )
        assert edited
        assert "Настройки" in edited[0]
        assert "Антифлуд" in edited[0]
        assert answered
    finally:
        await bot.session.close()


@pytest.mark.asyncio
async def test_menu_settings_denied_for_member(container, monkeypatch) -> None:
    answered: list[bool] = []

    async def fake_answer(self, text=None, **kwargs):
        answered.append(True)
        return None

    monkeypatch.setattr(CallbackQuery, "answer", fake_answer)
    bot = Bot(token="123456789:AAFakeTokenForTests_1234567890")
    dispatcher = fresh_dispatcher(container)
    try:
        message = Message(
            message_id=31,
            date=datetime.now(UTC),
            chat=Chat(id=-100322, type="supergroup", title="Settings"),
            from_user=TgUser(id=555, is_bot=False, first_name="Member"),
            text="меню",
        )
        callback = CallbackQuery(
            id="cb-2",
            from_user=TgUser(id=555, is_bot=False, first_name="Member"),
            chat_instance="chat-instance",
            message=message,
            data="menu:settings",
        )
        await dispatcher.feed_update(
            bot, Update(update_id=31, callback_query=callback)
        )
        assert answered
    finally:
        await bot.session.close()
