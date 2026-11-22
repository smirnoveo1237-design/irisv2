"""Разбор команд IrisV2.

Поддерживаются четыре формы вызова одной и той же команды::

    профиль
    !профиль
    .профиль
    ирис профиль
    /профиль            (стандартный способ Telegram, если он включён)
    /профиль@IrisV2Bot  (в группах, где несколько ботов)

Разбор намеренно не использует регулярные выражения на весь текст: сначала
снимается префикс/триггер, затем берётся ровно одно слово команды. Благодаря
этому «профилька» не считается командой «профиль».
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from app.core.logging import get_logger

log = get_logger(__name__)

CommandTrigger = Literal["bare", "prefix", "trigger", "slash"]

# Имя команды: буква (любой алфавит), далее буквы/цифры/_/-
_COMMAND_RE = re.compile(r"^[^\W\d_][\w\-]*$", re.UNICODE)
_SEPARATORS = " \t\n\r,.:;!—–-"
_TRAILING = ",.!?;:…»"


@dataclass(frozen=True, slots=True)
class ParsedCommand:
    name: str
    args: tuple[str, ...]
    raw_args: str
    trigger: CommandTrigger
    prefix: str
    raw: str

    @property
    def args_text(self) -> str:
        return self.raw_args


@dataclass(frozen=True)
class ParseConfig:
    prefixes: Sequence[str] = ("", "!", ".")
    triggers: Sequence[str] = ("ирис", "iris")
    bot_username: str = ""
    max_bare_length: int = 200
    default_command: str | None = "меню"


def normalize_text(text: str) -> str:
    """NFKC + единые пробелы: «ирис   профиль» и «ирис профиль» — одно и то же."""
    text = unicodedata.normalize("NFKC", text).replace("\u00a0", " ").replace("\u200b", "")
    return re.sub(r"[ \t]+", " ", text).strip()


def _clean_token(token: str) -> str:
    return token.rstrip(_TRAILING)


def _match_trigger(text: str, triggers: Sequence[str]) -> tuple[str, str] | None:
    """Возвращает (триггер, остаток), если сообщение начинается со слова-триггера."""
    lowered = text.casefold()
    for trigger in sorted(triggers, key=len, reverse=True):
        if not trigger:
            continue
        if lowered == trigger:
            return text[: len(trigger)], ""
        if lowered.startswith(trigger):
            boundary = text[len(trigger)]
            if boundary in " \t\n,.:;!—–-":
                rest = text[len(trigger) :]
                return text[: len(trigger)], rest.lstrip(_SEPARATORS)
    return None


def _match_prefix(text: str, prefixes: Sequence[str]) -> tuple[str, str] | None:
    for prefix in sorted((p for p in prefixes if p), key=len, reverse=True):
        if text.startswith(prefix):
            return prefix, text[len(prefix) :].lstrip()
    return None


def parse_command(
    text: str | None,
    *,
    known: Iterable[str] | None = None,
    config: ParseConfig | None = None,
    allow_bare: bool = True,
) -> ParsedCommand | None:
    """Разбирает сообщение в команду или возвращает None.

    ``known`` — имена и алиасы зарегистрированных команд. Если он передан,
    сообщение, первое слово которого не является командой, командой не считается.
    """
    config = config or ParseConfig()
    if not text:
        return None

    raw = text
    text = normalize_text(text)
    if not text or len(text) > 4096:
        return None

    trigger: CommandTrigger
    used_prefix = ""
    body: str

    if text.startswith("/"):
        trigger = "slash"
        used_prefix = "/"
        body = text[1:].lstrip()
    elif (prefix_match := _match_prefix(text, config.prefixes)) is not None:
        trigger = "prefix"
        used_prefix, body = prefix_match
    elif (trigger_match := _match_trigger(text, config.triggers)) is not None:
        trigger = "trigger"
        used_prefix, body = trigger_match
    else:
        trigger = "bare"
        body = text

    if not body:
        if trigger in {"slash", "prefix"}:
            return None
        if trigger == "trigger" and config.default_command:
            return ParsedCommand(
                name=config.default_command,
                args=(),
                raw_args="",
                trigger=trigger,
                prefix=used_prefix,
                raw=raw,
            )
        return None

    # После триггера может стоять ещё один префикс: «ирис !профиль»
    if trigger == "trigger":
        nested = _match_prefix(body, config.prefixes)
        if nested is not None and nested[1]:
            used_prefix, body = nested[0], nested[1]

    head, _, tail = body.partition(" ")
    head = head.split("\n", 1)[0]
    tail = tail.strip()

    if trigger == "slash" and "@" in head:
        head, _, mention = head.partition("@")
        expected = config.bot_username.lstrip("@").casefold()
        if expected and mention.casefold() != expected:
            # Команда адресована другому боту в этой же группе.
            return None

    name = _clean_token(head).casefold()
    if not name or not _COMMAND_RE.match(name):
        return None

    is_bare = trigger == "bare"

    if is_bare:
        if not allow_bare:
            return None
        if len(text) > config.max_bare_length:
            return None

    if known is not None and name not in known:
        return None

    args = tuple(part for part in re.split(r"\s+", tail) if part) if tail else ()
    return ParsedCommand(
        name=name,
        args=args,
        raw_args=tail,
        trigger=trigger,
        prefix=used_prefix,
        raw=raw,
    )


def strip_command(text: str, parsed: ParsedCommand) -> str:
    """Возвращает текст сообщения без команды (для сценариев «кто ...»)."""
    return parsed.raw_args.strip()
