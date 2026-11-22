"""Логика команды «Ирис кто»."""

from __future__ import annotations

import random
from dataclasses import dataclass

from app.core.texts import escape_html

PHRASES_RU = (
    "Я думаю, что {user} — {text}",
    "Шар говорит, что {user} — {text}",
    "Мне кажется, что {user} — {text}",
    "Моя интуиция подсказывает, что {user} — {text}",
    "Вселенная выбрала {user}",
    "Ставлю на {user}: {text}",
    "Без сомнений, {user} — {text}",
)

PHRASES_EN = (
    "I think that {user} is {text}",
    "The ball says that {user} is {text}",
    "It seems to me that {user} is {text}",
    "My intuition tells me that {user} is {text}",
    "The universe has chosen {user}",
    "My bet is on {user}: {text}",
)

DEFAULT_TEXT_RU = "загадочная личность"
DEFAULT_TEXT_EN = "a mysterious person"


@dataclass(frozen=True, slots=True)
class Candidate:
    user_id: int
    name: str
    is_bot: bool = False


def pick_person(
    candidates: list[Candidate],
    *,
    exclude_ids: set[int] | None = None,
    rng: random.Random | None = None,
) -> Candidate | None:
    """Случайный реальный участник: боты и сам IrisV2 исключены."""
    rng = rng or random.Random()
    exclude_ids = exclude_ids or set()
    pool = [
        candidate
        for candidate in candidates
        if not candidate.is_bot and candidate.user_id not in exclude_ids
    ]
    return rng.choice(pool) if pool else None


def build_answer(
    person: Candidate,
    text: str | None,
    *,
    locale: str = "ru",
    rng: random.Random | None = None,
) -> str:
    rng = rng or random.Random()
    template = rng.choice(PHRASES_EN if locale.startswith("en") else PHRASES_RU)
    subject = text.strip() if text and text.strip() else (
        DEFAULT_TEXT_EN if locale.startswith("en") else DEFAULT_TEXT_RU
    )
    link = f'<a href="tg://user?id={person.user_id}">{escape_html(person.name)}</a>'
    if "{text}" not in template:
        return template.format(user=link)
    return template.format(user=link, text=subject)
