#!/usr/bin/env python
"""Наполнение магазина и справочников для локальной проверки.

Запуск после миграций:
    python scripts/seed_demo.py --chat -1001234567890
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.container import Container
from app.core.cache import MemoryCache
from app.core.db import Database
from app.core.settings import get_settings
from app.database.models import Chat, ShopItem

DEFAULT_ITEMS = [
    ("vip", "⭐ VIP на день", "Звание VIP и +10% к ежедневной награде", 500, "role", 10),
    ("sticker", "🖼️ Набор стикеров", "Косметический предмет профиля", 150, "item", None),
    ("pet_food", "🍖 Корм для питомца", "Восстанавливает сытость питомца", 25, "item", None),
    ("lottery", "🎟️ Лотерейный билет", "Шанс выиграть 1000 Ирисок", 100, "item", None),
]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chat", type=int, default=None, help="ID группы для предметов")
    args = parser.parse_args()

    settings = get_settings()
    database = Database(settings.database_url)
    container = Container(settings, db=database, cache=MemoryCache())
    try:
        await database.create_all()
        async with database.session_scope() as session:
            await container.levels(session).seed_achievements()
            await container.quests(session).seed()

            chat_id = args.chat
            if chat_id is not None:
                exists = await session.get(Chat, chat_id)
                if exists is None:
                    session.add(Chat(id=chat_id, title="Demo chat", type="supergroup"))
                    await session.flush()
                await container.chats.ensure(
                    session, chat_id=chat_id, title="Demo chat", chat_type="supergroup"
                )

            for code, title, description, price, kind, stock in DEFAULT_ITEMS:
                found = await session.scalar(
                    select(ShopItem).where(ShopItem.chat_id == chat_id, ShopItem.code == code)
                )
                if found is None:
                    session.add(
                        ShopItem(
                            chat_id=chat_id,
                            code=code,
                            title=title,
                            description=description,
                            price=price,
                            kind=kind,
                            stock=stock,
                        )
                    )
            print("Демо-данные добавлены")
    finally:
        await container.close()


if __name__ == "__main__":
    asyncio.run(main())
