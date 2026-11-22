"""ИИ-помощник IrisV2 с цепочкой провайдеров и автоматическим фоллбэком.

Порядок: Groq → OpenRouter → TokenHarbor → Pollinations → Gemini.
При лимите/ошибке одного провайдера запрос уходит следующему; ключи и модели
берутся из .env. Наружу отдаётся только текст ответа, ключи не логируются.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import aiohttp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.database.models import AIHistory

if TYPE_CHECKING:
    from app.container import Container

log = get_logger(__name__)

SYSTEM_PROMPT = (
    "Ты — IrisV2, дружелюбный ассистент Telegram-сообщества. Отвечай кратко, по делу, "
    "на языке пользователя. Ты умеешь объяснять команды бота, помогать с настройками, "
    "придумывать приветствия и суммировать обсуждения. Ты НЕ выполняешь административные "
    "действия (бан, мут, удаление) и не обещаешь их — только предлагаешь команду, которую "
    "может выполнить человек с правами. Не выдумывай возможности Telegram Bot API."
)

GROQ_BASE = "https://api.groq.com/openai/v1"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
POLLINATIONS_BASE = "https://text.pollinations.ai/openai"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
MAX_TOTAL_SECONDS = 55.0


class AIUnavailable(Exception):
    pass


@dataclass(slots=True)
class AIProvider:
    name: str
    kind: str  # "openai" | "gemini"
    base_url: str
    api_key: str
    model: str
    extra_headers: dict[str, str] = field(default_factory=dict)


class AIService:
    def __init__(self, session: AsyncSession, container: Container) -> None:
        self.session = session
        self.container = container
        self.settings = container.settings

    # --- Конфигурация провайдеров ----------------------------------------
    def providers(self) -> list[AIProvider]:
        settings = self.settings
        items: list[AIProvider] = []
        seen: set[tuple[str, str, str, str]] = set()

        def add(
            name: str,
            kind: str,
            base_url: str,
            api_key: str,
            model: str,
            headers: dict[str, str] | None = None,
        ) -> None:
            if not model:
                return
            key = (name, base_url, api_key, model)
            if key in seen:
                return
            seen.add(key)
            items.append(
                AIProvider(
                    name=name,
                    kind=kind,
                    base_url=base_url.rstrip("/"),
                    api_key=api_key,
                    model=model,
                    extra_headers=headers or {},
                )
            )

        # 1. Groq: два ключа × основная/запасная модель.
        for api_key in (settings.groq_api_key, settings.groq_api_key_2):
            for model in (settings.groq_model, settings.groq_model_fallback):
                if api_key and model:
                    add("groq", "openai", GROQ_BASE, api_key, model)

        # 2. OpenRouter: два ключа, модель :free.
        for api_key in (settings.openrouter_api_key, settings.openrouter_api_key_2):
            if api_key and settings.openrouter_model:
                add(
                    "openrouter",
                    "openai",
                    OPENROUTER_BASE,
                    api_key,
                    settings.openrouter_model,
                    {"X-Title": "IrisV2", "HTTP-Referer": "https://t.me/IrisV2Bot"},
                )

        # 3. TokenHarbor — «свой» OpenAI-совместимый шлюз.
        if settings.tokenharbor_api_key and settings.tokenharbor_model:
            add(
                "tokenharbor",
                "openai",
                settings.tokenharbor_base_url,
                settings.tokenharbor_api_key,
                settings.tokenharbor_model,
            )

        # 4. Pollinations — бесплатный фоллбэк без ключа.
        add(
            "pollinations",
            "openai",
            POLLINATIONS_BASE,
            "",
            settings.pollinations_model or "openai",
            {"Referer": "https://t.me/IrisV2Bot"},
        )

        # 5. Gemini — свой формат запроса.
        for model in settings.gemini_models:
            if settings.gemini_api_key and model:
                add("gemini", "gemini", GEMINI_BASE, settings.gemini_api_key, model)

        # Совместимость со старой конфигурацией IRIS_AI_*.
        if not items and settings.ai_api_key and settings.ai_model:
            add("custom", "openai", settings.ai_base_url, settings.ai_api_key, settings.ai_model)

        return items

    @property
    def configured(self) -> bool:
        return bool(self.settings.ai_enabled and self.providers())

    # --- Публичный API ----------------------------------------------------
    async def ask(
        self,
        prompt: str,
        *,
        chat_id: int | None = None,
        user_id: int | None = None,
        system: str | None = None,
        max_tokens: int | None = None,
        remember: bool = True,
    ) -> str:
        providers = self.providers()
        if not self.settings.ai_enabled or not providers:
            raise AIUnavailable("ai not configured")

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system or SYSTEM_PROMPT}
        ]
        if chat_id is not None and remember:
            messages.extend(await self.recent_history(chat_id, user_id, limit=6))
        messages.append({"role": "user", "content": prompt})

        tokens = max_tokens or self.settings.ai_max_tokens
        timeout = min(float(self.settings.ai_timeout), 20.0)
        deadline = time.monotonic() + MAX_TOTAL_SECONDS
        errors: list[str] = []

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as client:
            for provider in providers:
                if time.monotonic() >= deadline:
                    errors.append("общий таймаут")
                    break
                started = time.monotonic()
                try:
                    if provider.kind == "gemini":
                        answer = await self._gemini(client, provider, messages, tokens)
                    else:
                        answer = await self._openai(client, provider, messages, tokens)
                    answer = (answer or "").strip()
                    if not answer:
                        raise AIUnavailable("пустой ответ")
                except Exception as exc:  # noqa: BLE001 - пробуем следующего
                    errors.append(
                        f"{provider.name}/{provider.model}: "
                        f"{type(exc).__name__}: {str(exc)[:120]}"
                    )
                    log.warning(
                        "ИИ-провайдер не ответил",
                        extra={
                            "provider": provider.name,
                            "model": provider.model,
                            "error": f"{type(exc).__name__}: {str(exc)[:160]}",
                        },
                    )
                    continue

                log.info(
                    "ИИ ответил",
                    extra={
                        "provider": provider.name,
                        "model": provider.model,
                        "latency_ms": int((time.monotonic() - started) * 1000),
                    },
                )
                if remember:
                    await self.remember(chat_id, user_id, "user", prompt)
                    await self.remember(chat_id, user_id, "assistant", answer)
                return answer

        raise AIUnavailable("; ".join(errors)[-500:] or "нет доступных провайдеров")

    # --- HTTP-провайдеры --------------------------------------------------
    async def _openai(
        self,
        client: aiohttp.ClientSession,
        provider: AIProvider,
        messages: list[dict[str, Any]],
        max_tokens: int,
    ) -> str:
        url = f"{provider.base_url}/chat/completions"
        headers = {"Content-Type": "application/json", **provider.extra_headers}
        if provider.api_key:
            headers["Authorization"] = f"Bearer {provider.api_key}"
        payload = {
            "model": provider.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }
        async with client.post(url, json=payload, headers=headers) as response:
            raw = await response.text()
            if response.status >= 400:
                raise AIUnavailable(f"HTTP {response.status}: {raw[:200]}")
            data = json.loads(raw)

        choices = data.get("choices") or []
        if not choices:
            raise AIUnavailable("нет choices в ответе")
        message = choices[0].get("message") or {}
        content = message.get("content") or message.get("reasoning_content") or ""
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        return str(content)

    async def _gemini(
        self,
        client: aiohttp.ClientSession,
        provider: AIProvider,
        messages: list[dict[str, Any]],
        max_tokens: int,
    ) -> str:
        system_parts = [m["content"] for m in messages if m.get("role") == "system"]
        contents: list[dict[str, Any]] = []
        for item in messages:
            role = item.get("role")
            if role == "system":
                continue
            gemini_role = "user" if role == "user" else "model"
            text = str(item.get("content", ""))
            if contents and contents[-1]["role"] == gemini_role:
                contents[-1]["parts"][0]["text"] += "\n" + text
            else:
                contents.append({"role": gemini_role, "parts": [{"text": text}]})
        if not contents:
            raise AIUnavailable("пустой диалог")

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.7},
        }
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n".join(system_parts)}]}

        url = f"{provider.base_url}/models/{provider.model}:generateContent"
        headers = {"Content-Type": "application/json", "x-goog-api-key": provider.api_key}
        async with client.post(url, json=payload, headers=headers) as response:
            raw = await response.text()
            if response.status >= 400:
                raise AIUnavailable(f"HTTP {response.status}: {raw[:200]}")
            data = json.loads(raw)

        candidates = data.get("candidates") or []
        if not candidates:
            reason = (data.get("promptFeedback") or {}).get("blockReason", "нет candidates")
            raise AIUnavailable(str(reason))
        parts = ((candidates[0].get("content") or {}).get("parts")) or []
        return "".join(str(part.get("text", "")) for part in parts)

    # --- История ----------------------------------------------------------
    async def remember(self, chat_id: int | None, user_id: int | None, role: str, content: str) -> None:
        self.session.add(
            AIHistory(chat_id=chat_id, user_id=user_id, role=role, content=content[:4000])
        )
        await self.session.flush()

    async def recent_history(
        self, chat_id: int, user_id: int | None, limit: int = 6
    ) -> list[dict[str, str]]:
        stmt = select(AIHistory).where(AIHistory.chat_id == chat_id)
        if user_id is not None:
            stmt = stmt.where(AIHistory.user_id == user_id)
        stmt = stmt.order_by(AIHistory.created_at.desc()).limit(limit)
        rows = list(await self.session.scalars(stmt))
        return [
            {"role": row.role if row.role in {"user", "assistant"} else "user", "content": row.content}
            for row in reversed(rows)
        ]

    async def store_chat_context(self, chat_id: int, user_id: int | None, name: str, text: str) -> None:
        self.session.add(
            AIHistory(
                chat_id=chat_id,
                user_id=user_id,
                role="user",
                kind="context",
                content=f"{name}: {text}"[:2000],
            )
        )
        await self.session.flush()

    async def summarize(self, chat_id: int, limit: int = 80) -> str:
        rows = list(
            await self.session.scalars(
                select(AIHistory)
                .where(AIHistory.chat_id == chat_id, AIHistory.kind == "context")
                .order_by(AIHistory.created_at.desc())
                .limit(limit)
            )
        )
        if len(rows) < 3:
            raise AIUnavailable("not enough context")
        transcript = "\n".join(row.content for row in reversed(rows))
        return await self.ask(
            "Сделай краткое изложение обсуждения: 3–5 пунктов, только факты из текста.\n\n"
            + transcript[:6000],
            chat_id=None,
            remember=False,
        )

    async def explain_command(self, name: str, usage: str, description: str) -> str:
        return await self.ask(
            f"Объясни простыми словами команду бота IrisV2 «{name}».\n"
            f"Описание: {description}\nИспользование: {usage}\n"
            "Дай 2 примера вызова и одну подсказку.",
            remember=False,
            max_tokens=400,
        )

    async def greeting(self, chat_title: str) -> str:
        return await self.ask(
            f"Придумай короткое тёплое приветствие нового участника для Telegram-чата «{chat_title}». "
            "Одно-два предложения, можно с эмодзи. Используй плейсхолдер {user}.",
            remember=False,
            max_tokens=150,
        )
