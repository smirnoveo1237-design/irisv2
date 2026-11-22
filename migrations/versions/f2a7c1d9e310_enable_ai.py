"""Включение ИИ в существующих чатах

Revision ID: f2a7c1d9e310
Revises: b7f3c9a12d44
Create Date: 2026-11-22 18:10:00

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "f2a7c1d9e310"
down_revision: str | None = "b7f3c9a12d44"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ИИ-провайдеры добавлены в проект; включаем ответы в уже существующих чатах.
    op.execute("UPDATE chat_settings SET ai_enabled = true")


def downgrade() -> None:
    # Откат не выключает ИИ обратно: это изменило бы пользовательские настройки.
    pass
