"""Работа со временем и длительностями."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

_DURATION_RE = re.compile(r"^(\d+)\s*(с|s|м|m|мин|min|ч|h|час|д|d|дн|н|w|нед)?$", re.IGNORECASE)
_UNITS = {
    "с": 1, "s": 1,
    "м": 60, "m": 60, "мин": 60, "min": 60,
    "ч": 3600, "h": 3600, "час": 3600,
    "д": 86400, "d": 86400, "дн": 86400,
    "н": 604800, "w": 604800, "нед": 604800,
}
UNIT_LABELS_RU = [(604800, "нед."), (86400, "дн."), (3600, "ч"), (60, "мин"), (1, "сек")]
UNIT_LABELS_EN = [(604800, "w"), (86400, "d"), (3600, "h"), (60, "m"), (1, "s")]


def now_utc() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime | None) -> datetime | None:
    """SQLite отдаёт naive datetime — приводим к UTC, чтобы сравнения работали."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def parse_duration(text: str | None, *, default_unit: str = "м") -> int | None:
    """«10м» → 600, «2ч» → 7200, «1д» → 86400. None — если формат неверный.

    Голое число трактуется в ``default_unit`` (по умолчанию минуты).
    """
    if not text:
        return None
    raw = text.strip().lower().replace(" ", "")
    if raw in {"перм", "perm", "навсегда", "forever"}:
        return 0  # 0 = бессрочно (обрабатывается вызывающей стороной)
    match = _DURATION_RE.match(raw)
    if not match:
        return None
    amount = int(match.group(1))
    unit = (match.group(2) or default_unit).lower()
    multiplier = _UNITS.get(unit)
    if multiplier is None:
        return None
    if amount <= 0:
        return None
    return amount * multiplier


def human_duration(seconds: int, locale: str = "ru") -> str:
    if seconds <= 0:
        return "бессрочно" if locale == "ru" else "permanent"
    labels = UNIT_LABELS_EN if locale.startswith("en") else UNIT_LABELS_RU
    parts: list[str] = []
    remaining = seconds
    for unit_seconds, label in labels:
        if remaining >= unit_seconds:
            amount, remaining = divmod(remaining, unit_seconds)
            parts.append(f"{amount} {label}")
            if len(parts) == 2:
                break
    return " ".join(parts) or f"{seconds} сек"


def format_datetime(value: datetime | None, timezone: str = "Europe/Moscow") -> str:
    value = as_utc(value)
    if value is None:
        return "—"
    try:
        tz = ZoneInfo(timezone)
    except Exception:  # noqa: BLE001 - битая таймзона не должна ломать вывод
        tz = UTC
    return value.astimezone(tz).strftime("%d.%m.%Y %H:%M")


def day_start(value: datetime | None = None) -> datetime:
    current = as_utc(value) or now_utc()
    return current.replace(hour=0, minute=0, second=0, microsecond=0)


def tomorrow_midnight(value: datetime | None = None) -> datetime:
    return day_start(value) + timedelta(days=1)
