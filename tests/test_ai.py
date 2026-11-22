"""Тесты выбора ИИ-провайдеров и команды .gpt (без сетевых вызовов)."""

from __future__ import annotations

import pytest

from app.core.settings import Settings
from app.services.ai import AIService


class DummyContainer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings


def make_settings() -> Settings:
    return Settings(
        bot_token="123456:TEST",
        ai_enabled=True,
        groq_api_key="groq-1",
        groq_api_key_2="groq-2",
        groq_model="groq-main",
        groq_model_fallback="groq-fallback",
        openrouter_api_key="or-1",
        openrouter_api_key_2="or-2",
        openrouter_model="or-model",
        tokenharbor_api_key="th-key",
        tokenharbor_model="th-model",
        gemini_api_key="gemini-key",
        gemini_models=["gemini-a", "gemini-b"],
        pollinations_model="openai",
    )


def test_provider_order() -> None:
    service = AIService(None, DummyContainer(make_settings()))
    names = [provider.name for provider in service.providers()]
    assert names == [
        "groq",
        "groq",
        "groq",
        "groq",
        "openrouter",
        "openrouter",
        "tokenharbor",
        "pollinations",
        "gemini",
        "gemini",
    ]
    models = [provider.model for provider in service.providers()]
    assert models[0] == "groq-main"
    assert models[1] == "groq-fallback"
    assert "th-model" in models
    assert "gemini-a" in models


def test_configured_requires_enabled_and_provider() -> None:
    enabled = make_settings()
    assert AIService(None, DummyContainer(enabled)).configured is True

    disabled = make_settings()
    disabled.ai_enabled = False
    assert AIService(None, DummyContainer(disabled)).configured is False


@pytest.mark.asyncio
async def test_gpt_command_answers(container, monkeypatch) -> None:
    from datetime import UTC, datetime

    from aiogram import Bot
    from aiogram.types import Chat, Message, Update
    from aiogram.types import User as TgUser

    from app.services.ai import AIService
    from tests.test_dispatch import USER_ID, fresh_dispatcher

    captured: list[str] = []

    async def fake_answer(self, text, **kwargs):
        captured.append(text)
        return None

    monkeypatch.setattr(Message, "answer", fake_answer)
    container.settings.ai_enabled = True

    async def fake_ask(self, prompt, **kwargs):
        assert prompt == "как дела?"
        return "тестовый ответ"

    monkeypatch.setattr(AIService, "ask", fake_ask)
    bot = Bot(token="123456789:AAFakeTokenForTests_1234567890")
    dispatcher = fresh_dispatcher(container)
    try:
        message = Message(
            message_id=7,
            date=datetime.now(UTC),
            chat=Chat(id=-100111, type="supergroup", title="AI"),
            from_user=TgUser(id=USER_ID, is_bot=False, first_name="Иван"),
            text=".gpt как дела?",
        )
        await dispatcher.feed_update(bot, Update(update_id=7, message=message))
        assert captured
        assert "тестовый ответ" in captured[-1]
    finally:
        await bot.session.close()


@pytest.mark.asyncio
async def test_iris_question_fallback(container, monkeypatch) -> None:
    from datetime import UTC, datetime

    from aiogram import Bot
    from aiogram.types import Chat, Message, Update
    from aiogram.types import User as TgUser

    from app.services.ai import AIService
    from tests.test_dispatch import USER_ID, fresh_dispatcher

    captured: list[str] = []

    async def fake_answer(self, text, **kwargs):
        captured.append(text)
        return None

    async def fake_ask(self, prompt, **kwargs):
        return "ответ на вопрос"

    monkeypatch.setattr(Message, "answer", fake_answer)
    monkeypatch.setattr(AIService, "ask", fake_ask)
    container.settings.ai_enabled = True

    bot = Bot(token="123456789:AAFakeTokenForTests_1234567890")
    dispatcher = fresh_dispatcher(container)
    try:
        message = Message(
            message_id=8,
            date=datetime.now(UTC),
            chat=Chat(id=-100112, type="supergroup", title="AI"),
            from_user=TgUser(id=USER_ID, is_bot=False, first_name="Иван"),
            text="ирис как дела?",
        )
        await dispatcher.feed_update(bot, Update(update_id=8, message=message))
        assert captured
        assert "ответ на вопрос" in captured[-1]
    finally:
        await bot.session.close()
