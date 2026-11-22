"""Реестр участников группы.

Telegram Bot API не отдаёт полный список участников, поэтому IrisV2 ведёт
собственный реестр: он наполняется любыми доступными событиями (сообщения,
вход/выход, изменения статуса) и постепенно «догоняет» старые группы.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.database.models import ChatMember, User
from app.database.utils import upsert

if TYPE_CHECKING:
    from app.container import Container

log = get_logger(__name__)


class MemberService:
    def __init__(self, session: AsyncSession, container: Container) -> None:
        self.session = session
        self.container = container

    async def touch(
        self,
        *,
        chat_id: int,
        user_id: int,
        username: str | None = None,
        full_name: str | None = None,
        is_bot: bool = False,
        status: str = "member",
        message_increment: bool = False,
        verified: bool = True,
    ) -> None:
        now = datetime.now(UTC)
        values = {
            "chat_id": chat_id,
            "user_id": user_id,
            "username": username,
            "full_name": full_name,
            "is_bot": is_bot,
            "status": status,
            "last_seen_at": now,
            "is_verified": verified,
        }
        update_values: dict[str, Any] = {
            "username": username,
            "full_name": full_name,
            "status": status,
            "last_seen_at": now,
        }
        if message_increment:
            update_values["message_count"] = ChatMember.message_count + 1

        applied = await upsert(
            self.session,
            ChatMember,
            {**values, "message_count": 1 if message_increment else 0},
            index_elements=["chat_id", "user_id"],
            update_values=update_values,
        )
        if not applied:  # неизвестный диалект — ручной путь
            member = await self.get(chat_id, user_id)
            if member is None:
                self.session.add(ChatMember(**values, message_count=1 if message_increment else 0))
            else:
                member.username = username
                member.full_name = full_name
                member.status = status
                member.last_seen_at = now
                if message_increment:
                    member.message_count += 1

    async def get(self, chat_id: int, user_id: int) -> ChatMember | None:
        return await self.session.scalar(
            select(ChatMember).where(
                ChatMember.chat_id == chat_id, ChatMember.user_id == user_id
            )
        )

    async def mark_left(self, chat_id: int, user_id: int, *, kicked: bool = False) -> None:
        await self.session.execute(
            update(ChatMember)
            .where(ChatMember.chat_id == chat_id, ChatMember.user_id == user_id)
            .values(status="kicked" if kicked else "left", left_at=datetime.now(UTC))
        )

    async def mark_verified(self, chat_id: int, user_id: int) -> None:
        await self.session.execute(
            update(ChatMember)
            .where(ChatMember.chat_id == chat_id, ChatMember.user_id == user_id)
            .values(is_verified=True)
        )

    async def find_in_chat(self, chat_id: int, raw: str) -> ChatMember | None:
        raw = raw.strip()
        if raw.startswith("@"):
            return await self.session.scalar(
                select(ChatMember).where(
                    ChatMember.chat_id == chat_id,
                    func.lower(ChatMember.username) == raw[1:].lower(),
                )
            )
        if raw.lstrip("-").isdigit():
            return await self.get(chat_id, int(raw))
        return None

    async def random_candidates(
        self,
        chat_id: int,
        *,
        exclude: set[int] | None = None,
        limit: int = 60,
    ) -> list[ChatMember]:
        """Случайная выборка реальных участников, известных боту."""
        exclude = exclude or set()
        stmt = (
            select(ChatMember)
            .where(
                ChatMember.chat_id == chat_id,
                ChatMember.is_bot.is_(False),
                ChatMember.status.in_(["member", "administrator", "creator"]),
            )
            .order_by(func.random())
            .limit(limit + len(exclude))
        )
        rows = list(await self.session.scalars(stmt))
        return [row for row in rows if row.user_id not in exclude][:limit]

    async def count(self, chat_id: int) -> int:
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(ChatMember)
                .where(ChatMember.chat_id == chat_id, ChatMember.is_bot.is_(False))
            )
            or 0
        )

    async def sync_admins(self, bot: Any, chat_id: int) -> int:
        """Подтягивает администраторов чата в реестр. Возвращает число новых."""
        if bot is None:
            return 0
        try:
            admins = await bot.get_chat_administrators(chat_id)
        except Exception as exc:  # noqa: BLE001 - нет прав/сети — не критично
            log.warning(
                "Не удалось получить администраторов",
                extra={"chat_id": chat_id, "error": str(exc)},
            )
            return 0

        added = 0
        for admin in admins:
            user = admin.user
            if user.is_bot:
                continue
            existing = await self.get(chat_id, user.id)
            await self.ensure_user(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                language_code=user.language_code,
                is_bot=False,
            )
            await self.touch(
                chat_id=chat_id,
                user_id=user.id,
                username=user.username,
                full_name=user.full_name,
                status="creator" if admin.status == "creator" else "administrator",
                verified=True,
            )
            if existing is None:
                added += 1
        await self.session.flush()
        return added

    async def stats(self, chat_id: int) -> dict[str, int]:
        rows = await self.session.execute(
            select(ChatMember.status, ChatMember.is_bot, ChatMember.is_verified, func.count())
            .where(ChatMember.chat_id == chat_id)
            .group_by(ChatMember.status, ChatMember.is_bot, ChatMember.is_verified)
        )
        result = {"total": 0, "active": 0, "admins": 0, "verified": 0, "bots": 0}
        for status, is_bot, is_verified, count in rows.all():
            count = int(count)
            if is_bot:
                result["bots"] += count
                continue
            result["total"] += count
            if status in {"member", "administrator", "creator"}:
                result["active"] += count
            if status in {"administrator", "creator"}:
                result["admins"] += count
            if is_verified:
                result["verified"] += count
        return result

    async def top_by_messages(self, chat_id: int, limit: int = 10) -> list[ChatMember]:
        rows = await self.session.scalars(
            select(ChatMember)
            .where(ChatMember.chat_id == chat_id, ChatMember.is_bot.is_(False))
            .order_by(ChatMember.message_count.desc())
            .limit(limit)
        )
        return list(rows)

    async def ensure_user(
        self,
        *,
        user_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
        language_code: str | None = None,
        is_bot: bool = False,
    ) -> User:
        now = datetime.now(UTC)
        await upsert(
            self.session,
            User,
            {
                "id": user_id,
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "language_code": language_code,
                "is_bot": is_bot,
                "last_seen_at": now,
            },
            index_elements=["id"],
            update_values={
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "language_code": language_code,
                "last_seen_at": now,
            },
        )
        user = await self.session.get(User, user_id)
        if user is None:  # неизвестный диалект
            user = User(
                id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                language_code=language_code,
                is_bot=is_bot,
            )
            self.session.add(user)
            await self.session.flush()
        return user

    def display(self, member: ChatMember | User | None) -> str:
        if member is None:
            return "—"
        name = getattr(member, "full_name", None)
        if name:
            return name
        return " ".join(
            part for part in (getattr(member, "first_name", None), getattr(member, "last_name", None)) if part
        ) or "—"

    @staticmethod
    def pick(candidates: list[ChatMember]) -> ChatMember | None:
        return random.choice(candidates) if candidates else None
