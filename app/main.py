"""Точка входа IrisV2."""

from __future__ import annotations

import asyncio
import signal
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from app.commands.middleware import IrisMiddleware
from app.container import Container
from app.core.cache import build_cache
from app.core.db import Database
from app.core.logging import get_logger, setup_logging
from app.core.middleware import ContainerMiddleware
from app.core.settings import Settings, get_settings
from app.modules.loader import include_modules

log = get_logger(__name__)

SQLITE_URL = "sqlite+aiosqlite:///./iris.db"


def apply_cli_overrides(settings: Settings, argv: list[str] | None = None) -> bool:
    """Применяет флаги запуска. Возвращает True, если включён режим SQLite.

    --sqlite — быстрый локальный запуск без PostgreSQL и Redis: база в ./iris.db,
    кэш в памяти. Таблицы создаются автоматически.
    """
    arguments = list(argv if argv is not None else sys.argv)
    if "--sqlite" in arguments:
        settings.database_url = SQLITE_URL
        settings.redis_url = ""
        return True
    return False


def build_dispatcher(container: Container) -> Dispatcher:
    dispatcher = Dispatcher(storage=MemoryStorage())
    for observer in (
        dispatcher.message,
        dispatcher.callback_query,
        dispatcher.chat_member,
        dispatcher.my_chat_member,
    ):
        observer.middleware(ContainerMiddleware(container))
    dispatcher.message.middleware(IrisMiddleware(container))
    include_modules(dispatcher)

    @dispatcher.errors()
    async def on_error(event: ErrorEvent) -> bool:
        log.exception(
            "Необработанная ошибка апдейта",
            extra={"update": type(event.update).__name__, "error": str(event.exception)},
        )
        return True

    return dispatcher


async def main() -> None:
    settings = get_settings()
    sqlite_mode = apply_cli_overrides(settings)
    setup_logging(settings.log_level, settings.log_json)
    # Проверяем токен до подключения к БД и сети — ошибка конфига видна сразу.
    token = settings.access_token
    log.info("Запуск IrisV2", extra={"env": settings.env, "bot": settings.bot_username})
    if sqlite_mode:
        log.warning("Режим SQLite: локальная база ./iris.db, кэш в памяти (не для production)")

    db = Database(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle,
    )
    if sqlite_mode or settings.database_url.startswith("sqlite") or "--create-db" in sys.argv:
        await db.create_all()

    cache = await build_cache(settings.redis_url)
    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    container = Container(settings, bot=bot, db=db, cache=cache)
    dispatcher = build_dispatcher(container)

    if settings.webhook_enabled:
        from app.webhook import run_webhook

        await run_webhook(container, dispatcher, bot, settings)
        return

    await container.bootstrap()
    container.scheduler.start()

    stop_event = asyncio.Event()

    def _signal(*_args) -> None:
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_running_loop().add_signal_handler(sig, _signal)
        except NotImplementedError:  # Windows
            signal.signal(sig, lambda *_: stop_event.set())

    polling = asyncio.create_task(
        dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types()),
        name="iris-polling",
    )
    stop_task = asyncio.create_task(stop_event.wait(), name="iris-stop")
    done, pending = await asyncio.wait({polling, stop_task}, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    for task in done:
        if task.cancelled() or task.exception() is None:
            continue
        log.error("Polling завершился с ошибкой", extra={"error": str(task.exception())})

    log.info("Остановка IrisV2")
    await dispatcher.stop_polling()
    await container.close()
    await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
    except RuntimeError as exc:
        # Понятное сообщение вместо трассировки: чаще всего забыт .env или токен.
        log.error(str(exc))
        sys.exit(1)
    except Exception:
        log.exception("Фатальная ошибка запуска")
        raise
