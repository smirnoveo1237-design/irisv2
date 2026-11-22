"""Логика команды «Шипперим»: случайная пара и текст без процентов.

Функции вынесены из обработчика, чтобы их можно было проверить юнит-тестами
без Telegram и базы данных.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from app.core.texts import escape_html

TITLES = (
    "💞 РАНДОМ ШИППЕРИМ:",
    "💘 РАНДОМ ШИППЕРИМ:",
    "💞 ШИППЕРИМ ДНЯ:",
    "🌸 РАНДОМНАЯ ПАРА:",
    "💕 СЛУЧАЙНАЯ ПАРА:",
)

ENDINGS = (
    "Любите друг друга и берегите. Мур.",
    "Совет да любовь. Мур.",
    "Берегите друг друга. Мяу.",
    "Не ссорьтесь, вам ещё вместе жить. Мур.",
    "Вселенная одобряет. Мур-мур.",
    "Пусть всё сложится. Мур.",
)


@dataclass(frozen=True, slots=True)
class Candidate:
    user_id: int
    name: str
    username: str | None = None
    is_bot: bool = False
    is_self: bool = False

    @property
    def link(self) -> str:
        if self.username:
            return f"https://t.me/{self.username.lstrip('@')}"
        return f"tg://user?id={self.user_id}"

    def html(self) -> str:
        return f'<a href="{self.link}">{escape_html(self.name)}</a>'


def choose_pair(
    candidates: list[Candidate],
    *,
    initiator_id: int | None = None,
    recent_pairs: set[frozenset[int]] | None = None,
    rng: random.Random | None = None,
    attempts: int = 12,
) -> tuple[Candidate, Candidate, bool] | None:
    """Выбирает двух разных участников.

    Боты исключаются, но сам IrisV2 (``is_self``) — полноценный участник шутки.
    Инициатор исключается, если после этого остаётся минимум два кандидата.
    """
    rng = rng or random.Random()
    recent_pairs = recent_pairs or set()

    pool = [candidate for candidate in candidates if candidate.is_self or not candidate.is_bot]
    if len(pool) < 2:
        return None

    without_initiator = [item for item in pool if item.user_id != initiator_id]
    if len(without_initiator) >= 2:
        pool = without_initiator

    fallback: tuple[Candidate, Candidate] | None = None
    for _ in range(max(1, attempts)):
        first, second = rng.sample(pool, 2)
        fallback = fallback or (first, second)
        if frozenset((first.user_id, second.user_id)) not in recent_pairs:
            return first, second, False
    first, second = fallback  # все варианты недавно показывали — новый круг
    return first, second, True


def build_ship_message(
    first: Candidate, second: Candidate, rng: random.Random | None = None
) -> str:
    rng = rng or random.Random()
    title = rng.choice(TITLES)
    ending = rng.choice(ENDINGS)
    return f"{title} {first.html()} + {second.html()}. {ending}"
