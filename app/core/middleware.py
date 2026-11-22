"""Middleware, который прокидывает контейнер зависимостей в обработчики."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class ContainerMiddleware(BaseMiddleware):
    def __init__(self, container) -> None:
        self.container = container

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["container"] = self.container
        return await handler(event, data)
