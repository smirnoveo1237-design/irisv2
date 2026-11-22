"""Общие фикстуры тестов IrisV2."""

from __future__ import annotations

import pytest
import pytest_asyncio

from app.container import Container
from app.core.db import Database
from app.core.settings import Settings


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings(
        bot_token="123456:TEST",
        bot_username="IrisV2Bot",
        owner_ids=[1],
        database_url="sqlite+aiosqlite:///:memory:",
        redis_url="",
        command_prefixes=["", "!", "."],
        command_triggers=["ирис", "iris"],
    )


@pytest_asyncio.fixture
async def db() -> Database:
    database = Database("sqlite+aiosqlite:///:memory:", static_pool=True)
    await database.create_all()
    try:
        yield database
    finally:
        await database.dispose()


@pytest_asyncio.fixture
async def container(settings: Settings, db: Database) -> Container:
    instance = Container(settings, bot=None, db=db)
    await instance.bootstrap()
    try:
        yield instance
    finally:
        await instance.close()


@pytest_asyncio.fixture
async def session(db: Database):
    async with db.session_scope() as session:
        yield session
