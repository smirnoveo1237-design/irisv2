"""Общие помощники для модулей."""

from __future__ import annotations

import random
from collections.abc import Iterable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.texts import escape_html
from app.database.models import ChatMember, User


def escape(text: str | None) -> str:
    return escape_html(text)


def mention(user_id: int, name: str | None = None) -> str:
    label = escape(name) if name else str(user_id)
    return f'<a href="tg://user?id={user_id}">{label}</a>'


def user_mention(user: User | ChatMember | None, fallback_id: int = 0) -> str:
    if user is None:
        return mention(fallback_id)
    user_id = getattr(user, "id", None) or getattr(user, "user_id", fallback_id)
    name = getattr(user, "full_name", None)
    if not name:
        name = " ".join(
            part
            for part in (getattr(user, "first_name", None), getattr(user, "last_name", None))
            if part
        )
    return mention(user_id, name or None)


def progress_bar(percent: int, length: int = 10, filled: str = "█", empty: str = "░") -> str:
    percent = max(0, min(100, percent))
    filled_count = round(percent / 100 * length)
    return filled * filled_count + empty * (length - filled_count)


def score_phrase(score: int) -> str:
    if score >= 90:
        return "Это судьба! 💞"
    if score >= 75:
        return "Отличная пара, им стоит познакомиться поближе."
    if score >= 55:
        return "Есть chemistry — попробуйте сходить на кофе."
    if score >= 35:
        return "Сложится, если поработать над общением."
    if score >= 15:
        return "Скорее друзья, чем пара."
    return "Вселенная против, но попробовать можно."


def inline(rows: Iterable[Iterable[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=data) for label, data in row]
            for row in rows
        ]
    )


def pick_weighted(options: list[tuple[str, float]]) -> str:
    total = sum(weight for _, weight in options)
    point = random.uniform(0, total)
    current = 0.0
    for value, weight in options:
        current += weight
        if point <= current:
            return value
    return options[-1][0]


def chunks(items: list, size: int) -> list[list]:
    return [items[index : index + size] for index in range(0, len(items), size)]
