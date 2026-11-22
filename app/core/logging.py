"""Структурированное логирование (JSON или читаемый текст)."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

_RESERVED = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename", "module",
    "exc_info", "exc_text", "stack_info", "lineno", "funcName", "created", "msecs",
    "relativeCreated", "thread", "threadName", "processName", "process", "taskName",
}

# Поля, которые нельзя передавать в extra: logging выбросит KeyError.
_EXTRA_RESERVED = _RESERVED | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = f"{self.formatTime(record, '%Y-%m-%d %H:%M:%S')} | {record.levelname:<8} | {record.name:<28} | "
        message = record.getMessage()
        extra = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED and not key.startswith("_")
        }
        if extra:
            message = f"{message} | " + " ".join(f"{k}={v}" for k, v in extra.items())
        if record.exc_info:
            message = f"{message}\n{self.formatException(record.exc_info)}"
        return base + message


class SafeLogger(logging.Logger):
    """Логгер, который не падает на зарезервированных ключах extra.

    ``logging`` бросает KeyError, если в ``extra`` передать ``module``, ``args``,
    ``name`` и подобные поля LogRecord. Такая ошибка возникала прямо в цикле
    обработки команд и ломала любую команду. Здесь такие ключи переименовываются
    в ``ctx_*``, а лог остаётся информативным.
    """

    def makeRecord(
        self,
        name: str,
        level: int,
        fn: str,
        lno: int,
        msg: object,
        args: tuple,
        exc_info,
        func: str | None = None,
        extra: dict | None = None,
        sinfo: str | None = None,
    ) -> logging.LogRecord:
        if extra:
            extra = {
                (f"ctx_{key}" if key in _EXTRA_RESERVED else key): value
                for key, value in extra.items()
            }
        return super().makeRecord(name, level, fn, lno, msg, args, exc_info, func, extra, sinfo)


logging.setLoggerClass(SafeLogger)


def setup_logging(level: str = "INFO", json_logs: bool = False) -> None:
    """Настраивает корневой логгер один раз, не дублируя обработчики."""
    logging.setLoggerClass(SafeLogger)
    root = logging.getLogger()
    root.setLevel(level.upper())

    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter() if json_logs else TextFormatter())
    root.addHandler(handler)

    for noisy in ("aiogram.event", "sqlalchemy.engine.Engine", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not isinstance(logger, SafeLogger):
        # Логгер мог быть создан до setLoggerClass (например, при импорте модуля).
        logger.__class__ = SafeLogger
    return logger
