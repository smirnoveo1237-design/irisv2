"""Тесты разбора команд: все четыре формы вызова и границы."""

from __future__ import annotations

import pytest

from app.commands.parser import ParseConfig, parse_command

KNOWN = {"профиль", "баланс", "помощь", "кто", "шипперим", "меню", "бан", "ии", "операции"}
CONFIG = ParseConfig(
    prefixes=["", "!", "."],
    triggers=["ирис", "iris"],
    bot_username="IrisV2Bot",
    max_bare_length=200,
)


@pytest.mark.parametrize(
    "text",
    [
        "профиль",
        "!профиль",
        ".профиль",
        "ирис профиль",
        "Ирис Профиль",
        "/профиль",
        "/профиль@IrisV2Bot",
        "  профиль  ",
        "ирис, профиль",
        "ирис\nпрофиль",
        "ИРИС   ПРОФИЛЬ",
    ],
)
def test_same_command_all_forms(text: str) -> None:
    parsed = parse_command(text, known=KNOWN, config=CONFIG)
    assert parsed is not None
    assert parsed.name == "профиль"


def test_trigger_types() -> None:
    assert parse_command("профиль", known=KNOWN, config=CONFIG).trigger == "bare"
    assert parse_command("!профиль", known=KNOWN, config=CONFIG).trigger == "prefix"
    assert parse_command("ирис профиль", known=KNOWN, config=CONFIG).trigger == "trigger"
    assert parse_command("/профиль", known=KNOWN, config=CONFIG).trigger == "slash"


def test_arguments_preserved() -> None:
    parsed = parse_command("ирис кто самый смешной человек", known=KNOWN, config=CONFIG)
    assert parsed is not None
    assert parsed.name == "кто"
    assert parsed.args == ("самый", "смешной", "человек")
    assert parsed.raw_args == "самый смешной человек"


def test_arguments_keep_punctuation() -> None:
    parsed = parse_command("кто сегодня женится?", known=KNOWN, config=CONFIG)
    assert parsed is not None
    assert parsed.name == "кто"
    assert parsed.args_text == "сегодня женится?"


def test_word_boundary() -> None:
    assert parse_command("профилька", known=KNOWN, config=CONFIG) is None
    assert parse_command("!профилька", known=KNOWN, config=CONFIG) is None
    assert parse_command("профильчик тут", known=KNOWN, config=CONFIG) is None


def test_regular_speech_is_not_a_command() -> None:
    assert parse_command("привет как дела", known=KNOWN, config=CONFIG) is None
    assert parse_command("мне кажется это хорошая идея", known=KNOWN, config=CONFIG) is None


def test_unknown_command_rejected() -> None:
    assert parse_command("!неизвестная", known=KNOWN, config=CONFIG) is None
    assert parse_command("ирис неизвестная", known=KNOWN, config=CONFIG) is None


def test_short_command_without_prefix() -> None:
    parsed = parse_command("ии", known=KNOWN, config=CONFIG)
    assert parsed is not None
    assert parsed.name == "ии"


def test_trigger_alone_opens_menu() -> None:
    parsed = parse_command("ирис", known=KNOWN, config=CONFIG)
    assert parsed is not None
    assert parsed.name == "меню"
    assert parsed.trigger == "trigger"


def test_prefix_alone_is_not_command() -> None:
    assert parse_command("!", known=KNOWN, config=CONFIG) is None
    assert parse_command("/", known=KNOWN, config=CONFIG) is None
    assert parse_command("...", known=KNOWN, config=CONFIG) is None


def test_foreign_bot_mention_ignored() -> None:
    assert parse_command("/профиль@OtherBot", known=KNOWN, config=CONFIG) is None


def test_bare_length_limit() -> None:
    long_text = "профиль " + "а" * 300
    assert parse_command(long_text, known=KNOWN, config=CONFIG) is None
    assert parse_command("!профиль " + "а" * 300, known=KNOWN, config=CONFIG) is not None


def test_allow_bare_switch() -> None:
    assert parse_command("профиль", known=KNOWN, config=CONFIG, allow_bare=False) is None
    assert parse_command("!профиль", known=KNOWN, config=CONFIG, allow_bare=False) is not None


def test_custom_prefixes_per_chat() -> None:
    config = ParseConfig(prefixes=["", "$"], triggers=["ирис"], bot_username="IrisV2Bot")
    assert parse_command("$баланс", known=KNOWN, config=config) is not None
    assert parse_command("!баланс", known=KNOWN, config=config) is None


def test_nested_prefix_after_trigger() -> None:
    parsed = parse_command("ирис !профиль", known=KNOWN, config=CONFIG)
    assert parsed is not None
    assert parsed.name == "профиль"


def test_none_and_empty() -> None:
    assert parse_command(None, known=KNOWN, config=CONFIG) is None
    assert parse_command("", known=KNOWN, config=CONFIG) is None
    assert parse_command("   ", known=KNOWN, config=CONFIG) is None


def test_dot_number_is_not_command() -> None:
    assert parse_command("3.14", known=KNOWN, config=CONFIG) is None
