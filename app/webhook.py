"""Webhook-режим для Render и других хостингов с публичным HTTPS.

Long polling на бесплатном Render невозможен: сервис должен принимать входящие
HTTP-запросы, иначе он засыпает. Здесь Telegram присылает updates на /telegram/webhook,
а /health используется health-check'ом Render.
"""

from __future__ import annotations

import asyncio
import os
import re
import secrets
import signal
from typing import TYPE_CHECKING

from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from app.core.logging import get_logger

if TYPE_CHECKING:
    from aiogram import Bot, Dispatcher

    from app.container import Container
    from app.core.settings import Settings

log = get_logger(__name__)

HEALTH_PATH = "/health"


def public_base_url(settings: Settings) -> str:
    """IRIS_WEBHOOK_URL или автоматический URL Render."""
    return (settings.webhook_url or os.environ.get("RENDER_EXTERNAL_URL", "")).rstrip("/")


def create_webhook_app(
    container: Container,
    dispatcher: Dispatcher,
    bot: Bot,
    settings: Settings,
) -> tuple[web.Application, str]:
    base_url = public_base_url(settings)
    if not base_url:
        raise RuntimeError(
            "Webhook включён, но нет публичного URL: задайте IRIS_WEBHOOK_URL "
            "или разверните сервис на Render (RENDER_EXTERNAL_URL)."
        )

    path = settings.webhook_path if settings.webhook_path.startswith("/") else f"/{settings.webhook_path}"
    webhook_url = f"{base_url}{path}"
    secret = settings.webhook_secret or secrets.token_urlsafe(32)
    # Telegram разрешает только A-Z a-z 0-9 _ -; Render generateValue может дать иные символы.
    secret = re.sub(r"[^A-Za-z0-9_-]", "", secret)[:256]
    if not secret:
        secret = secrets.token_urlsafe(32)
    if not settings.webhook_secret:
        log.warning(
            "IRIS_WEBHOOK_SECRET не задан — сгенерирован временный секрет. "
            "На Render задайте его через generateValue."
        )

    app = web.Application()

    async def health(_: web.Request) -> web.Response:
        # Не трогаем БД: health-check должен отвечать даже при холодном старте.
        return web.Response(text="ok")

    app.router.add_get(HEALTH_PATH, health)
    app.router.add_get("/", health)

    handler = SimpleRequestHandler(
        dispatcher=dispatcher,
        bot=bot,
        secret_token=secret,
        handle_in_background=True,
    )
    handler.register(app, path=path)
    setup_application(app, dispatcher, bot=bot)

    async def on_startup(_: web.Application) -> None:
        await container.bootstrap()
        await bot.set_webhook(
            url=webhook_url,
            secret_token=secret,
            allowed_updates=dispatcher.resolve_used_update_types(),
            drop_pending_updates=settings.drop_pending_updates,
        )
        container.scheduler.start()
        log.info("Webhook установлен", extra={"url": webhook_url, "path": path})

    async def on_shutdown(_: web.Application) -> None:
        log.info("Остановка webhook-сервера")
        await container.scheduler.stop()
        await container.close()
        try:
            await bot.session.close()
        except Exception:  # noqa: BLE001 - сессия могла быть уже закрыта
            pass

    # setup_application уже добавил dispatcher.emit_startup/shutdown;
    # наши колбэки идут после них.
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    return app, webhook_url


async def run_webhook(
    container: Container,
    dispatcher: Dispatcher,
    bot: Bot,
    settings: Settings,
) -> None:
    app, webhook_url = create_webhook_app(container, dispatcher, bot, settings)

    runner = web.AppRunner(app, shutdown_timeout=30)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=settings.port)
    await site.start()
    log.info(
        "HTTP-сервер запущен",
        extra={"port": settings.port, "webhook": webhook_url},
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, RuntimeError):
            signal.signal(sig, lambda *_: stop_event.set())

    try:
        await stop_event.wait()
    finally:
        log.info("Остановка IrisV2 (webhook)")
        await runner.cleanup()
