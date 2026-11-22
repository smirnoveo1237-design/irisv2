"""Автоматизация: событие → условие → действие."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.texts import escape_html
from app.database.models import Automation, ChatSettings
from app.services.antispam import URL_RE
from app.services.moderation import ModerationError

if TYPE_CHECKING:
    from app.container import Container

log = get_logger(__name__)


@dataclass(slots=True)
class AutomationResult:
    rule_id: int
    actions: list[str] = field(default_factory=list)


class AutomationService:
    def __init__(self, container: Container, session: AsyncSession) -> None:
        self.container = container
        self.session = session

    async def rules(self, chat_id: int, event: str = "message") -> list[Automation]:
        rows = await self.session.scalars(
            select(Automation)
            .where(
                Automation.chat_id == chat_id,
                Automation.is_active.is_(True),
                Automation.event.in_([event, "any"]),
            )
            .order_by(Automation.id)
        )
        return list(rows)

    # --- Условия ----------------------------------------------------------
    @staticmethod
    def match(rule: Automation, message: Message, *, is_new_member: bool = False) -> bool:
        conditions = rule.conditions or {}
        text = message.text or message.caption or ""
        lowered = text.casefold()

        if "contains" in conditions and str(conditions["contains"]).casefold() not in lowered:
            return False
        if "word" in conditions:
            pattern = rf"(?<!\w){re.escape(str(conditions['word']).casefold())}(?!\w)"
            if not re.search(pattern, lowered):
                return False
        if "starts_with" in conditions and not lowered.startswith(
            str(conditions["starts_with"]).casefold()
        ):
            return False
        if "regex" in conditions:
            try:
                if not re.search(str(conditions["regex"]), text, re.IGNORECASE):
                    return False
            except re.error:
                return False
        if "min_len" in conditions and len(text) < int(conditions["min_len"]):
            return False
        if conditions.get("has_link") and not URL_RE.search(text):
            return False
        if conditions.get("from_new") and not is_new_member:
            return False
        return True

    # --- Действия ---------------------------------------------------------
    async def process(
        self,
        message: Message,
        settings: ChatSettings,
        *,
        user_name: str,
        is_new_member: bool = False,
    ) -> list[AutomationResult]:
        results: list[AutomationResult] = []
        rules = await self.rules(message.chat.id)
        if not rules:
            return results

        for rule in rules:
            if not self.match(rule, message, is_new_member=is_new_member):
                continue
            executed: list[str] = []
            try:
                executed = await self._execute(rule, message, settings, user_name)
            except ModerationError as exc:
                log.warning(
                    "Автоматизация не смогла выполнить действие",
                    extra={"rule_id": rule.id, "error": str(exc)},
                )
            except Exception as exc:  # noqa: BLE001 - правило не должно ломать поток
                log.exception("Ошибка автоматизации", extra={"rule_id": rule.id, "error": str(exc)})
            if executed:
                rule.trigger_count += 1
                results.append(AutomationResult(rule_id=rule.id, actions=executed))
        await self.session.flush()
        return results

    async def _execute(
        self,
        rule: Automation,
        message: Message,
        settings: ChatSettings,
        user_name: str,
    ) -> list[str]:
        from app.services.economy import EconomyError, EconomyService
        from app.services.moderation import ModerationService

        executed: list[str] = []
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else 0
        moderation = ModerationService(self.container, self.session, settings)

        for action in rule.actions or []:
            kind = str(action.get("type", "")).lower()

            if kind in {"reply", "ответ"}:
                text = str(action.get("text", "")).format(
                    user=f'<a href="tg://user?id={user_id}">{escape_html(user_name)}</a>',
                    name=escape_html(user_name),
                    chat=escape_html(message.chat.title or ""),
                    id=user_id,
                )
                await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)
                executed.append("reply")

            elif kind in {"delete", "удалить"}:
                try:
                    await message.delete()
                    executed.append("delete")
                except Exception:  # noqa: BLE001
                    pass

            elif kind in {"mute", "мут"}:
                minutes = int(action.get("minutes", settings.mute_minutes))
                await moderation.mute(
                    chat_id,
                    user_id,
                    moderator_id=None,
                    seconds=minutes * 60,
                    reason=f"Автоматизация #{rule.id}",
                )
                executed.append("mute")

            elif kind in {"warn", "пред"}:
                await moderation.warn(
                    chat_id,
                    user_id,
                    moderator_id=None,
                    reason=f"Автоматизация #{rule.id}",
                    limit=settings.max_warnings,
                    auto_action=settings.warn_action,
                    mute_minutes=settings.mute_minutes,
                )
                executed.append("warn")

            elif kind in {"ban", "бан"}:
                await moderation.ban(
                    chat_id,
                    user_id,
                    moderator_id=None,
                    reason=f"Автоматизация #{rule.id}",
                )
                executed.append("ban")

            elif kind in {"reward", "награда"}:
                amount = int(action.get("amount", 10))
                key = f"auto:{rule.id}:{chat_id}:{user_id}"
                cooldown = await self.container.cache.get(key)
                if cooldown:
                    continue
                try:
                    await EconomyService(self.session, self.container).credit(
                        chat_id,
                        user_id,
                        amount,
                        kind="automation",
                        reason=f"Автоматизация #{rule.id}",
                        idempotency_key=f"{key}:{message.message_id}",
                    )
                    await self.container.cache.set(key, "1", ttl=60)
                    executed.append("reward")
                except EconomyError:
                    continue

            elif kind in {"notify", "уведомить"}:
                await moderation.send_log(
                    chat_id,
                    f"⚙️ Автоматизация #{rule.id}: {action.get('text', '')}".strip(),
                )
                executed.append("notify")

        return executed

    # --- Разбор DSL из команды -------------------------------------------
    @staticmethod
    def parse_rule(raw: str) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
        """«слово=привет ответ=Здравствуйте, {user}!» → conditions, actions."""
        conditions: dict[str, Any] = {}
        actions: list[dict[str, Any]] = []
        chunks = [chunk for chunk in re.split(r"\s+(?=[\wа-яА-ЯёЁ]+=)", raw.strip()) if chunk]
        parts = []
        for chunk in chunks:
            key, separator, value = chunk.partition("=")
            if separator and key and value:
                parts.append((key, value.strip()))
        if not parts:
            return None
        for key, value in parts:
            value = value.strip("\"'")
            key = key.lower()
            if key in {"слово", "word"}:
                conditions["word"] = value
            elif key in {"содержит", "contains"}:
                conditions["contains"] = value
            elif key in {"начинается", "starts"}:
                conditions["starts_with"] = value
            elif key in {"regex", "регекс"}:
                conditions["regex"] = value
            elif key in {"длина", "min_len"}:
                conditions["min_len"] = int(value)
            elif key in {"ссылка", "has_link"}:
                conditions["has_link"] = value not in {"0", "false", "нет"}
            elif key in {"новый", "from_new"}:
                conditions["from_new"] = value not in {"0", "false", "нет"}
            elif key in {"ответ", "reply"}:
                actions.append({"type": "reply", "text": value})
            elif key in {"удалить", "delete"}:
                actions.append({"type": "delete"})
            elif key in {"мут", "mute"}:
                actions.append({"type": "mute", "minutes": int(value)})
            elif key in {"пред", "warn"}:
                actions.append({"type": "warn"})
            elif key in {"бан", "ban"}:
                actions.append({"type": "ban"})
            elif key in {"награда", "reward"}:
                actions.append({"type": "reward", "amount": int(value)})
            elif key in {"уведомить", "notify"}:
                actions.append({"type": "notify", "text": value})
        if not actions:
            return None
        return conditions, actions
