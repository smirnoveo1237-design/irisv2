"""Загрузка модулей: импорт обработчиков и подключение роутеров."""

from __future__ import annotations

import importlib
import pkgutil

from aiogram import Dispatcher, Router

import app.modules as modules_package
from app.core.logging import get_logger

log = get_logger(__name__)

# Порядок важен: команды и FSM-ввод раньше «ловящих» текстовых обработчиков.
MODULE_ORDER = [
    "menu",
    "members",
    "settings",
    "moderation",
    "antispam",
    "economy",
    "profiles",
    "social",
    "ai",
    "games",
    "analytics",
    "automation",
    "support",
    "shipper",
    "iris_who",
    "reports",
    "giveaways",
]


def discover_modules() -> list[str]:
    found = [info.name for info in pkgutil.iter_modules(modules_package.__path__) if info.ispkg]
    ordered = [name for name in MODULE_ORDER if name in found]
    ordered += sorted(name for name in found if name not in MODULE_ORDER)
    return ordered


def load_routers() -> list[Router]:
    routers: list[Router] = []
    for name in discover_modules():
        try:
            module = importlib.import_module(f"app.modules.{name}.handlers")
        except ModuleNotFoundError as exc:
            log.error("Модуль без обработчиков", extra={"module_name": name, "error": str(exc)})
            continue
        router = getattr(module, "router", None)
        if isinstance(router, Router):
            routers.append(router)
            log.debug("Роутер подключён", extra={"module_name": name})
        else:
            log.warning("В модуле нет router", extra={"module_name": name})
    return routers


def include_modules(dispatcher: Dispatcher) -> None:
    for router in load_routers():
        dispatcher.include_router(router)
