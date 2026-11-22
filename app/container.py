"""Контейнер зависимостей: один объект на процесс, сервисы — на запрос."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram import Bot

from app.commands.registry import CommandRegistry, registry
from app.core.cache import Cache, MemoryCache
from app.core.db import Database
from app.core.settings import Settings
from app.core.texts import Texts, texts
from app.services.ai import AIService
from app.services.analytics import AnalyticsService
from app.services.antispam import AntispamService
from app.services.automation import AutomationService
from app.services.chats import ChatService
from app.services.economy import EconomyService
from app.services.levels import LevelService
from app.services.members import MemberService
from app.services.moderation import ModerationService
from app.services.permissions import PermissionService
from app.services.scheduler import SchedulerService
from app.services.tickets import TicketService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.database.models import ChatSettings


class Container:
    def __init__(
        self,
        settings: Settings,
        *,
        bot: Bot | None = None,
        db: Database | None = None,
        cache: Cache | None = None,
        commands: CommandRegistry | None = None,
    ) -> None:
        self.settings = settings
        self.bot = bot
        self.db = db  # type: ignore[assignment]
        self.cache: Cache = cache or MemoryCache()
        self.texts: Texts = texts
        self.commands = commands or registry
        self.chats = ChatService(self)
        self.scheduler = SchedulerService(self)

    # --- Фабрики сервисов на сессию --------------------------------------
    def economy(self, session: AsyncSession) -> EconomyService:
        return EconomyService(session, self)

    def members(self, session: AsyncSession) -> MemberService:
        return MemberService(session, self)

    def permissions(self, session: AsyncSession) -> PermissionService:
        return PermissionService(self, session)

    def levels(self, session: AsyncSession) -> LevelService:
        return LevelService(session, self)

    def moderation(
        self, session: AsyncSession, settings: ChatSettings | None = None
    ) -> ModerationService:
        return ModerationService(self, session, settings)

    def analytics(self, session: AsyncSession) -> AnalyticsService:
        return AnalyticsService(session, self)

    def automation(self, session: AsyncSession) -> AutomationService:
        return AutomationService(self, session)

    def antispam(self, session: AsyncSession) -> AntispamService:
        return AntispamService(self, session)

    def tickets(self, session: AsyncSession) -> TicketService:
        return TicketService(session, self)

    def quests(self, session: AsyncSession):
        from app.services.quests import QuestService

        return QuestService(session, self)

    def ai(self, session: AsyncSession) -> AIService:
        return AIService(session, self)

    def profiles(self, session: AsyncSession):
        from app.services.profiles import ProfileService

        return ProfileService(session, self)

    def locale(self, settings: ChatSettings | None) -> str:
        return self.chats.locale(settings)

    async def bootstrap(self) -> None:
        if self.db is None:
            return
        async with self.db.session_scope() as session:
            await self.quests(session).seed()

    async def close(self) -> None:
        await self.scheduler.stop()
        if self.db is not None:
            await self.db.dispose()
        await self.cache.close()
