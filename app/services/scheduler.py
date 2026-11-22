"""Планировщик: отложенные задачи, розыгрыши, CAPTCHA-таймауты, истечение наказаний."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING

from aiogram.exceptions import TelegramAPIError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.timeutil import as_utc, now_utc
from app.database.models import Giveaway, GiveawayMember, ScheduledTask

if TYPE_CHECKING:
    from app.container import Container

log = get_logger(__name__)


class SchedulerService:
    def __init__(self, container: Container) -> None:
        self.container = container
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._running = True
            self._task = asyncio.create_task(self._loop(), name="iris-scheduler")
            log.info("Планировщик запущен")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while self._running:
            try:
                await self.tick()
            except Exception as exc:  # noqa: BLE001 - планировщик не должен падать
                log.exception("Ошибка планировщика", extra={"error": str(exc)})
            await asyncio.sleep(max(5, self.container.settings.scheduler_tick))

    async def tick(self) -> None:
        async with self.container.db.session_scope() as session:
            await self._run_tasks(session)
            await self._finish_giveaways(session)

    async def _run_tasks(self, session: AsyncSession) -> None:
        due = list(
            await session.scalars(
                select(ScheduledTask)
                .where(
                    ScheduledTask.is_active.is_(True),
                    ScheduledTask.run_at <= now_utc(),
                )
                .order_by(ScheduledTask.run_at)
                .limit(50)
            )
        )
        for task in due:
            try:
                await self._execute(session, task)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "Отложенная задача не выполнена",
                    extra={"task_id": task.id, "kind": task.kind, "error": str(exc)},
                )
            task.last_run_at = now_utc()
            if task.repeat_every:
                task.run_at = now_utc() + timedelta(seconds=task.repeat_every)
            else:
                task.is_active = False
        await session.commit()

    async def _execute(self, session: AsyncSession, task: ScheduledTask) -> None:
        payload = task.payload or {}
        bot = self.container.bot
        if bot is None:
            return

        if task.kind == "captcha_kick":
            chat_id = int(payload["chat_id"])
            user_id = int(payload["user_id"])
            settings = await self.container.chats.settings(session, chat_id)
            if settings and settings.captcha_enabled:
                member = await self.container.members(session).get(chat_id, user_id)
                if member and not member.is_verified:
                    try:
                        await bot.ban_chat_member(chat_id, user_id)
                        await bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
                        await bot.send_message(
                            chat_id,
                            f"⌛ {member.full_name or user_id} не прошёл проверку CAPTCHA и был исключён.",
                        )
                    except TelegramAPIError:
                        pass

        elif task.kind == "unmute":
            try:
                await self.container.moderation(session, None).unmute(
                    int(payload["chat_id"]), int(payload["user_id"]), moderator_id=None, reason="Истёк мут"
                )
            except Exception:  # noqa: BLE001
                pass

        elif task.kind == "unban":
            try:
                await self.container.moderation(session, None).unban(
                    int(payload["chat_id"]), int(payload["user_id"]), moderator_id=None, reason="Истёк бан"
                )
            except Exception:  # noqa: BLE001
                pass

        elif task.kind == "reminder":
            try:
                await bot.send_message(int(payload["chat_id"]), str(payload.get("text", "⏰ Напоминание")))
            except TelegramAPIError:
                pass

    async def _finish_giveaways(self, session: AsyncSession) -> None:
        due = list(
            await session.scalars(
                select(Giveaway).where(
                    Giveaway.status == "active", Giveaway.ends_at <= now_utc()
                )
            )
        )
        if not due:
            return
        import random

        for giveaway in due:
            members = list(
                await session.scalars(
                    select(GiveawayMember.user_id).where(
                        GiveawayMember.giveaway_id == giveaway.id
                    )
                )
            )
            giveaway.status = "finished"
            if not members:
                message = "🎁 Розыгрыш завершён, но участников не было."
            else:
                winners = random.sample(members, min(giveaway.winner_count, len(members)))
                mentions = ", ".join(f'<a href="tg://user?id={uid}">участник</a>' for uid in winners)
                message = f"🎉 Розыгрыш «{giveaway.prize}» завершён! Победители: {mentions}"
            if self.container.bot is not None:
                try:
                    await self.container.bot.send_message(giveaway.chat_id, message)
                except TelegramAPIError:
                    log.warning("Не удалось объявить победителей", extra={"giveaway_id": giveaway.id})
        await session.commit()

    async def schedule(
        self,
        session: AsyncSession,
        *,
        chat_id: int | None,
        kind: str,
        run_at,
        payload: dict | None = None,
        repeat_every: int | None = None,
    ) -> None:
        session.add(
            ScheduledTask(
                chat_id=chat_id,
                kind=kind,
                run_at=run_at,
                payload=payload or {},
                repeat_every=repeat_every,
            )
        )
        await session.flush()

    async def expire_old_bans(self, session: AsyncSession) -> int:
        """Возвращает баны, срок которых истёк, — вызывается по расписанию."""
        from datetime import timedelta

        from sqlalchemy import update

        from app.database.models import Ban

        result = await session.execute(
            update(Ban)
            .where(
                Ban.is_active.is_(True),
                Ban.until.is_not(None),
                Ban.until < now_utc() - timedelta(seconds=1),
            )
            .values(is_active=False)
        )
        return int(result.rowcount or 0)


def safe_seconds(value) -> int:
    value = as_utc(value)
    if value is None:
        return 0
    return max(0, int((value - now_utc()).total_seconds()))
