"""Диалект-независимые UPSERT-хелперы (PostgreSQL в бою, SQLite в тестах)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger

log = get_logger(__name__)


def _insert_for(session: AsyncSession, model: Any):
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert

        return insert(model)
    if dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert

        return insert(model)
    return None


async def upsert(
    session: AsyncSession,
    model: Any,
    values: dict[str, Any],
    *,
    index_elements: list[str],
    update_values: dict[str, Any] | None = None,
) -> bool:
    """INSERT ... ON CONFLICT DO UPDATE/NOTHING.

    Возвращает True, если применён диалектный путь. Если диалект неизвестен —
    False, и вызывающая сторона делает обычный select/insert.
    """
    statement = _insert_for(session, model)
    if statement is None:
        return False
    statement = statement.values(**values)
    if update_values:
        statement = statement.on_conflict_do_update(
            index_elements=index_elements, set_=update_values
        )
    else:
        statement = statement.on_conflict_do_nothing(index_elements=index_elements)
    await session.execute(statement)
    return True
