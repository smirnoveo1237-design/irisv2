"""Тесты логирования: зарезервированные ключи extra не должны ронять бота."""

from __future__ import annotations

import logging

from app.core.logging import SafeLogger, get_logger


def test_reserved_extra_keys_are_renamed(caplog) -> None:
    logger = get_logger("tests.reserved")
    with caplog.at_level(logging.INFO, logger="tests.reserved"):
        logger.info(
            "проверка",
            extra={"module": "moderation", "args": "10м", "name": "x", "message": "y"},
        )
    record = caplog.records[-1]
    assert record.ctx_module == "moderation"
    assert record.ctx_args == "10м"
    assert record.ctx_name == "x"
    assert record.ctx_message == "y"


def test_logger_class_is_safe() -> None:
    logger = get_logger("tests.reserved.class")
    assert isinstance(logger, SafeLogger)


def test_command_style_logging_does_not_raise() -> None:
    logger = get_logger("tests.commands")
    logger.info(
        "Команда",
        extra={
            "command": "бан",
            "module_name": "moderation",
            "chat_id": -1001,
            "user_id": 42,
            "cmd_args": "@user 1д",
        },
    )
