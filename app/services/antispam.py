"""Антиспам, антифлуд, антикапс, антиссылки и защита от фишинга."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.database.models import ChatMember, ChatSettings, Filter

if TYPE_CHECKING:
    from app.container import Container

log = get_logger(__name__)

URL_RE = re.compile(r"(https?://|www\.|t\.me/|telegram\.me/)[^\s]+", re.IGNORECASE)
MENTION_RE = re.compile(r"@[A-Za-z0-9_]{4,}")
SUSPICIOUS_TLDS = (".top", ".xyz", ".click", ".buzz", ".loan", ".work", ".shop", ".icu", ".cyou")
PHISHING_WORDS = (
    "seed-фраз", "seed phrase", "приватный ключ", "private key", "код из смс",
    "никому не сообщайте код", "airdrop", "free crypto", "бесплатные ириски",
    "ставки на спорт", "казино", "1xbet", "выигрыш guaranteed",
)


@dataclass(slots=True)
class SpamVerdict:
    reason: str
    action: str = "delete"
    mute_minutes: int = 0
    details: str = ""


def text_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


def caps_ratio(text: str) -> float:
    letters = [char for char in text if char.isalpha()]
    if len(letters) < 8:
        return 0.0
    upper = sum(1 for char in letters if char.isupper())
    return upper / len(letters)


def looks_like_phishing(text: str) -> bool:
    lowered = text.casefold()
    if any(word in lowered for word in PHISHING_WORDS):
        return True
    for url in URL_RE.findall(text):
        host = url.casefold()
        if any(tld in host for tld in SUSPICIOUS_TLDS) and any(
            keyword in lowered for keyword in ("telegram", "tg", "wallet", "кошел", "крипт", "bonus", "бонус")
        ):
            return True
    return False


class AntispamService:
    def __init__(self, container: Container, session: AsyncSession) -> None:
        self.container = container
        self.session = session
        self.cache = container.cache

    async def check(
        self,
        message: Message,
        settings: ChatSettings,
        *,
        is_admin: bool = False,
        is_new_member: bool = False,
        is_command: bool = False,
    ) -> SpamVerdict | None:
        if message.from_user is None or message.from_user.is_bot:
            return None
        if is_admin:
            return None

        text = message.text or message.caption or ""
        chat_id = message.chat.id
        user_id = message.from_user.id

        if settings.antiflood_enabled and text:
            key = f"flood:{chat_id}:{user_id}"
            count = await self.cache.incr(key, ttl=max(3, settings.flood_window))
            if count > max(2, settings.flood_limit):
                await self.cache.delete(key)
                return SpamVerdict(
                    reason="flood",
                    action=settings.antiflood_action or "mute",
                    mute_minutes=max(1, settings.mute_minutes),
                    details=f"{count} сообщений за {settings.flood_window} с",
                )

        if not text:
            return None

        if is_command:
            # Команды проверяем только на флуд: аргументы команды могут содержать
            # ссылки/слова, которые не должны приводить к наказанию.
            return None

        if settings.antispam_enabled:
            dup_key = f"dup:{chat_id}:{user_id}:{text_hash(text)}"
            repeats = await self.cache.incr(dup_key, ttl=600)
            if repeats >= 2:
                await self.cache.delete(dup_key)
                return SpamVerdict(reason="duplicate", action="delete")

            mention_count = len(MENTION_RE.findall(text)) + len(
                [entity for entity in (message.entities or []) if entity.type == "text_mention"]
            )
            if mention_count >= 6:
                return SpamVerdict(reason="mentions", action="delete")

            if settings.anticaps_enabled and caps_ratio(text) > 0.7:
                return SpamVerdict(reason="caps", action="delete")

            if settings.antiphishing_enabled and looks_like_phishing(text):
                return SpamVerdict(
                    reason="phishing",
                    action="mute",
                    mute_minutes=max(60, settings.mute_minutes),
                )

            if settings.antilink_enabled and URL_RE.search(text):
                return SpamVerdict(reason="link", action="delete")

            if is_new_member and URL_RE.search(text):
                return SpamVerdict(
                    reason="newbie_link",
                    action="mute",
                    mute_minutes=max(10, settings.mute_minutes),
                )

            lowered = text.casefold()
            stop_words = [word.casefold() for word in (settings.stop_words or []) if word]
            if any(word in lowered for word in stop_words):
                return SpamVerdict(reason="stop_word", action="delete")

            verdict = await self._check_filters(chat_id, text)
            if verdict is not None:
                return verdict

        return None

    async def _check_filters(self, chat_id: int, text: str) -> SpamVerdict | None:
        filters = list(
            await self.session.scalars(
                select(Filter).where(Filter.chat_id == chat_id, Filter.is_active.is_(True))
            )
        )
        lowered = text.casefold()
        for item in filters:
            matched = False
            if item.kind == "word":
                matched = item.pattern.casefold() in lowered
            elif item.kind == "regex":
                try:
                    matched = re.search(item.pattern, text, re.IGNORECASE) is not None
                except re.error:
                    matched = False
            if matched:
                item.hits += 1
                await self.session.flush()
                return SpamVerdict(
                    reason=f"filter:{item.pattern}",
                    action=item.action or "delete",
                    mute_minutes=item.mute_minutes,
                )
        return None

    async def is_new_member(self, chat_id: int, user_id: int, hours: int = 24) -> bool:
        member = await self.session.scalar(
            select(ChatMember).where(
                ChatMember.chat_id == chat_id, ChatMember.user_id == user_id
            )
        )
        if member is None:
            return True
        from app.core.timeutil import as_utc, now_utc

        first_seen = as_utc(member.first_seen_at)
        if first_seen is None:
            return True
        return (now_utc() - first_seen).total_seconds() < hours * 3600
