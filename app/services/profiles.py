"""Профили: карточка, описание и репутация."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.texts import escape_html
from app.core.timeutil import as_utc, format_datetime, now_utc
from app.database.models import Marriage, ReputationLog, User, UserProfile
from app.database.utils import upsert
from app.services.levels import LevelService

if TYPE_CHECKING:
    from app.container import Container

BIO_LIMIT = 300
REPUTATION_COOLDOWN = timedelta(hours=24)


class ProfileService:
    def __init__(self, session: AsyncSession, container: Container) -> None:
        self.session = session
        self.container = container

    async def get_or_create(self, user_id: int) -> UserProfile:
        profile = await self.session.get(UserProfile, user_id)
        if profile is not None:
            return profile
        await upsert(
            self.session,
            UserProfile,
            {"user_id": user_id, "reputation": 0, "total_messages": 0},
            index_elements=["user_id"],
        )
        profile = await self.session.get(UserProfile, user_id)
        if profile is None:
            profile = UserProfile(user_id=user_id)
            self.session.add(profile)
            await self.session.flush()
        return profile

    async def touch(self, user_id: int, *, messages: int = 0, commands: int = 0) -> None:
        if not messages and not commands:
            return
        profile = await self.get_or_create(user_id)
        profile.total_messages += messages
        profile.total_commands += commands
        await self.session.flush()

    async def set_bio(self, user_id: int, bio: str) -> bool:
        bio = bio.strip()
        if len(bio) > BIO_LIMIT:
            return False
        profile = await self.get_or_create(user_id)
        profile.bio = bio or None
        await self.session.flush()
        return True

    async def card(self, chat_id: int, user_id: int, locale: str = "ru") -> str:
        user = await self.session.get(User, user_id)
        profile = await self.get_or_create(user_id)
        level = await LevelService(self.session, self.container).get(chat_id, user_id)
        wallet = await self.container.economy(self.session).get_wallet(chat_id, user_id)
        name = escape_html(user.display_name if user else str(user_id))
        vip_until = as_utc(profile.vip_until)
        vip = ""
        if vip_until and vip_until > now_utc():
            vip = self.container.texts.t(
                locale, "profile_vip", date=format_datetime(vip_until, self.container.settings.timezone)
            )

        marriage = await self.session.scalar(
            select(Marriage).where(
                Marriage.chat_id == chat_id,
                Marriage.status == "active",
                or_(Marriage.user1_id == user_id, Marriage.user2_id == user_id),
            )
        )
        marriage_line = ""
        if marriage is not None:
            partner_id = (
                marriage.user2_id if marriage.user1_id == user_id else marriage.user1_id
            )
            partner = await self.session.get(User, partner_id)
            partner_name = escape_html(
                partner.display_name if partner else str(partner_id)
            )
            marriage_line = self.container.texts.t(
                locale,
                "profile_married",
                partner=f'<a href="tg://user?id={partner_id}">{partner_name}</a>',
                date=format_datetime(
                    marriage.created_at, self.container.settings.timezone
                ),
            )

        level_data = LevelService.format_level(level)
        return self.container.texts.t(
            locale,
            "profile_body",
            name=f'<a href="tg://user?id={user_id}">{name}</a>',
            user_id=user_id,
            bio=escape_html(profile.bio) if profile.bio else self.container.texts.t(locale, "profile_no_bio"),
            level=level_data["level"],
            xp=level_data["xp"],
            xp_left=level_data["xp_left"],
            messages=level_data["messages"],
            reputation=profile.reputation,
            balance=wallet.balance if wallet else 0,
            currency=self.container.texts.t(locale, "currency"),
            vip=vip,
            marriage=marriage_line,
            updated=format_datetime(profile.updated_at, self.container.settings.timezone),
        )

    async def give_reputation(
        self, chat_id: int, from_user_id: int, to_user_id: int, *, reason: str | None = None
    ) -> int | bool:
        """Возвращает новое значение репутации или False при кулдауне."""
        cooldown_key = f"rep:{chat_id}:{from_user_id}:{to_user_id}"
        if await self.container.cache.get(cooldown_key):
            return False
        last = await self.session.scalar(
            select(ReputationLog.created_at)
            .where(
                ReputationLog.chat_id == chat_id,
                ReputationLog.from_user_id == from_user_id,
                ReputationLog.to_user_id == to_user_id,
            )
            .order_by(ReputationLog.created_at.desc())
            .limit(1)
        )
        last_dt = as_utc(last)
        if last_dt and now_utc() - last_dt < REPUTATION_COOLDOWN:
            await self.container.cache.set(cooldown_key, "1", ttl=3600)
            return False

        profile = await self.get_or_create(to_user_id)
        profile.reputation += 1
        self.session.add(
            ReputationLog(
                chat_id=chat_id,
                from_user_id=from_user_id,
                to_user_id=to_user_id,
                delta=1,
                reason=reason,
            )
        )
        await self.session.flush()
        await self.container.cache.set(cooldown_key, "1", ttl=int(REPUTATION_COOLDOWN.total_seconds()))
        return profile.reputation

    async def reputation_top(self, limit: int = 10) -> list[tuple[UserProfile, User | None]]:
        rows = await self.session.execute(
            select(UserProfile, User)
            .join(User, User.id == UserProfile.user_id, isouter=True)
            .order_by(UserProfile.reputation.desc())
            .limit(limit)
        )
        return [(profile, user) for profile, user in rows.all()]

    async def bio_of(self, user_id: int) -> str | None:
        profile = await self.get_or_create(user_id)
        return profile.bio


def vip_active(vip_until: datetime | None) -> bool:
    value = as_utc(vip_until)
    return bool(value and value > now_utc())
