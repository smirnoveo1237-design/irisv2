"""Тесты webhook-режима и health-check для Render."""

from __future__ import annotations

import pytest
from aiogram import Bot

from app.core.settings import Settings
from app.webhook import create_webhook_app
from tests.test_dispatch import fresh_dispatcher


def webhook_settings(url: str = "https://irisv2.onrender.com") -> Settings:
    return Settings(
        bot_token="123456:TEST",
        webhook_enabled=True,
        webhook_url=url,
        webhook_secret="test-secret",
        webhook_path="/telegram/webhook",
    )


@pytest.mark.asyncio
async def test_webhook_routes(container) -> None:
    settings = webhook_settings()
    bot = Bot(token="123456789:AAFakeTokenForTests_1234567890")
    dispatcher = fresh_dispatcher(container)
    try:
        app, url = create_webhook_app(container, dispatcher, bot, settings)
        assert url == "https://irisv2.onrender.com/telegram/webhook"
        paths = {resource.get_info().get("path") for resource in app.router.resources()}
        assert "/health" in paths
        assert "/telegram/webhook" in paths
    finally:
        await bot.session.close()


@pytest.mark.asyncio
async def test_webhook_requires_public_url(container, monkeypatch) -> None:
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    settings = webhook_settings(url="")
    bot = Bot(token="123456789:AAFakeTokenForTests_1234567890")
    dispatcher = fresh_dispatcher(container)
    try:
        with pytest.raises(RuntimeError):
            create_webhook_app(container, dispatcher, bot, settings)
    finally:
        await bot.session.close()


def test_render_external_url_fallback(monkeypatch) -> None:
    from app.webhook import public_base_url

    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://iris.onrender.com/")
    assert public_base_url(webhook_settings(url="")) == "https://iris.onrender.com"


def test_neon_url_is_normalized() -> None:
    settings = Settings(
        bot_token="123456:TEST",
        database_url="postgresql://user:pass@db.neon.tech/iris?sslmode=require",
    )
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert "ssl=require" in settings.database_url


def test_empty_support_chat_is_allowed() -> None:
    settings = Settings(bot_token="123456:TEST", support_chat_id="")
    assert settings.support_chat_id is None


@pytest.mark.asyncio
async def test_health_endpoint(container, monkeypatch) -> None:
    from aiohttp.test_utils import TestClient, TestServer

    settings = webhook_settings()
    bot = Bot(token="123456789:AAFakeTokenForTests_1234567890")

    async def fake_set_webhook(self, *args, **kwargs):
        return True

    monkeypatch.setattr(Bot, "set_webhook", fake_set_webhook)
    dispatcher = fresh_dispatcher(container)
    app, _ = create_webhook_app(container, dispatcher, bot, settings)
    client = TestClient(TestServer(app))
    try:
        await client.start_server()
        response = await client.get("/health")
        assert response.status == 200
        assert await response.text() == "ok"
    finally:
        await client.close()
        await bot.session.close()
