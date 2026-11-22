"""Права: владелец бота, администратор Telegram и пользовательские роли."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.database.models import Role, UserRole

if TYPE_CHECKING:
    from app.container import Container

log = get_logger(__name__)

# Права IrisV2, которые можно выдать ролью.
PERMISSIONS: dict[str, tuple[str, str]] = {
    "moderation": ("Базовая модерация (предупреждения, удаление)", "Basic moderation"),
    "ban": ("Бан и разбан", "Ban / unban"),
    "mute": ("Мут и размут", "Mute / unmute"),
    "kick": ("Исключение из группы", "Kick"),
    "delete": ("Удаление сообщений", "Delete messages"),
    "settings": ("Изменение настроек группы", "Chat settings"),
    "roles": ("Управление ролями", "Roles"),
    "filters": ("Фильтры слов и ссылок", "Word/link filters"),
    "economy_admin": ("Выдача и списание Ирисок", "Economy admin"),
    "giveaway": ("Розыгрыши и голосования", "Giveaways and polls"),
    "pin": ("Закрепление сообщений", "Pin messages"),
    "ai": ("Настройка ИИ", "AI settings"),
}

# Какое право Telegram нужно для действия.
TELEGRAM_RIGHTS = {
    "ban": "can_restrict_members",
    "mute": "can_restrict_members",
    "kick": "can_restrict_members",
    "delete": "can_delete_messages",
    "pin": "can_pin_messages",
}


class PermissionService:
    def __init__(self, container: Container, session: AsyncSession) -> None:
        self.container = container
        self.session = session

    # --- Владелец ---------------------------------------------------------
    def is_owner(self, user_id: int) -> bool:
        return user_id in self.container.settings.owner_ids

    # --- Telegram ---------------------------------------------------------
    async def chat_status(self, chat_id: int, user_id: int) -> str:
        cache = self.container.cache
        key = f"member_status:{chat_id}:{user_id}"
        cached = await cache.get(key)
        if cached:
            return cached

        bot = self.container.bot
        if bot is None:
            return "unknown"
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            status = member.status
            if status == "creator":
                result = "creator"
            elif status == "administrator":
                rights = {
                    right: bool(getattr(member, right, False))
                    for right in set(TELEGRAM_RIGHTS.values())
                }
                result = "admin:" + json.dumps(rights)
            elif status in {"left", "kicked"}:
                result = status
            else:
                result = "member"
        except Exception as exc:  # noqa: BLE001 - бот может не быть в чате
            log.debug("get_chat_member failed", extra={"chat_id": chat_id, "error": str(exc)})
            result = "unknown"
        await cache.set(key, result, ttl=60)
        return result

    async def is_chat_admin(self, chat_id: int, user_id: int) -> bool:
        if self.is_owner(user_id):
            return True
        status = await self.chat_status(chat_id, user_id)
        return status == "creator" or status.startswith("admin:")

    async def bot_can(self, chat_id: int, right: str = "can_restrict_members") -> bool:
        bot = self.container.bot
        if bot is None:
            return False
        if not bot.id:
            return False
        cache = self.container.cache
        key = f"bot_rights:{chat_id}"
        cached = await cache.get(key)
        if cached:
            rights = json.loads(cached)
            return bool(rights.get(right))
        try:
            me = await bot.get_chat_member(chat_id, bot.id)
            rights = {
                "can_restrict_members": bool(getattr(me, "can_restrict_members", False)),
                "can_delete_messages": bool(getattr(me, "can_delete_messages", False)),
                "can_pin_messages": bool(getattr(me, "can_pin_messages", False)),
                "can_invite_users": bool(getattr(me, "can_invite_users", False)),
                "is_admin": me.status in {"administrator", "creator"},
            }
        except Exception:  # noqa: BLE001
            return False
        await cache.set(key, json.dumps(rights), ttl=120)
        return bool(rights.get(right))

    # --- Составные проверки ----------------------------------------------
    async def has_permission(self, chat_id: int, user_id: int, permission: str) -> bool:
        if self.is_owner(user_id):
            return True

        role_permissions = await self.role_permissions(chat_id, user_id)
        if "*" in role_permissions or permission in role_permissions:
            return True

        status = await self.chat_status(chat_id, user_id)
        if status == "creator":
            return True
        if status.startswith("admin:"):
            required = TELEGRAM_RIGHTS.get(permission)
            if required is None:
                return True  # администратор группы может пользоваться остальным
            rights = json.loads(status.split(":", 1)[1])
            return bool(rights.get(required))
        return False

    async def role_permissions(self, chat_id: int, user_id: int) -> set[str]:
        rows = await self.session.execute(
            select(Role.permissions)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.chat_id == chat_id, UserRole.user_id == user_id)
        )
        result: set[str] = set()
        for (permissions,) in rows.all():
            result.update(permissions or [])
        return result

    # --- Пользовательские роли -------------------------------------------
    async def list_roles(self, chat_id: int) -> list[Role]:
        return list(
            await self.session.scalars(select(Role).where(Role.chat_id == chat_id).order_by(Role.id))
        )

    async def get_role(self, chat_id: int, name: str) -> Role | None:
        return await self.session.scalar(
            select(Role).where(Role.chat_id == chat_id, Role.name == name)
        )

    async def create_role(self, chat_id: int, name: str, permissions: list[str]) -> Role:
        role = Role(chat_id=chat_id, name=name, permissions=permissions)
        self.session.add(role)
        await self.session.flush()
        return role

    async def grant_role(self, chat_id: int, user_id: int, role: Role) -> None:
        exists = await self.session.scalar(
            select(UserRole.id).where(
                UserRole.chat_id == chat_id,
                UserRole.user_id == user_id,
                UserRole.role_id == role.id,
            )
        )
        if exists is None:
            self.session.add(UserRole(chat_id=chat_id, user_id=user_id, role_id=role.id))
            await self.session.flush()
        await self.container.cache.delete(f"role_perms:{chat_id}:{user_id}")

    async def revoke_role(self, chat_id: int, user_id: int, role: Role) -> bool:
        result = await self.session.execute(
            delete(UserRole).where(
                UserRole.chat_id == chat_id,
                UserRole.user_id == user_id,
                UserRole.role_id == role.id,
            )
        )
        await self.container.cache.delete(f"role_perms:{chat_id}:{user_id}")
        return bool(result.rowcount)
