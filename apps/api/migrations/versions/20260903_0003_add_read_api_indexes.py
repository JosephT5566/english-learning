"""Add deterministic management-list indexes.

Revision ID: 20260903_0003
Revises: 20260902_0002
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260903_0003"
down_revision: str | Sequence[str] | None = "20260902_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add owner-scoped indexes matching the public management order."""

    op.create_index(
        "ix_learning_decks_owner_updated_id",
        "learning_decks",
        ["owner_id", sa.text("updated_at DESC"), sa.text("id DESC")],
        unique=False,
    )
    op.create_index(
        "ix_learning_cards_owner_updated_id",
        "learning_cards",
        ["owner_id", sa.text("updated_at DESC"), sa.text("id DESC")],
        unique=False,
    )


def downgrade() -> None:
    """Remove management-list indexes without changing domain data."""

    op.drop_index("ix_learning_cards_owner_updated_id", table_name="learning_cards")
    op.drop_index("ix_learning_decks_owner_updated_id", table_name="learning_decks")
