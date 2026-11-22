"""Настраиваемая задержка «Шипперим»

Revision ID: b7f3c9a12d44
Revises: e832ab37281f
Create Date: 2026-11-22 17:30:00

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7f3c9a12d44"
down_revision: str | None = "e832ab37281f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chat_settings",
        sa.Column("ship_cooldown", sa.Integer(), server_default="30", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("chat_settings", "ship_cooldown")
