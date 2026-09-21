"""Add versioned derived card embeddings without calling a provider.

Revision ID: 20260920_0006
Revises: 20260910_0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260920_0006"
down_revision: str | Sequence[str] | None = "20260910_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("learning_cards", sa.Column("semantic_content_hash", sa.String(64)))
    op.create_check_constraint(
        "ck_learning_cards_semantic_content_hash",
        "learning_cards",
        "semantic_content_hash IS NULL OR semantic_content_hash ~ '^[0-9a-f]{64}$'",
    )
    op.create_table(
        "card_embeddings",
        sa.Column("card_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("model_version", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=True),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("embedded_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.Text()),
        sa.Column("claim_token", postgresql.UUID(as_uuid=True)),
        sa.CheckConstraint(
            "state IN ('pending', 'ready', 'retryable', 'exhausted')",
            name="ck_card_embeddings_state",
        ),
        sa.CheckConstraint(
            "attempt_count BETWEEN 0 AND 3", name="ck_card_embeddings_attempt_count"
        ),
        sa.CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'", name="ck_card_embeddings_content_hash"
        ),
        sa.CheckConstraint(
            "char_length(btrim(model_version)) BETWEEN 1 AND 120",
            name="ck_card_embeddings_model_version",
        ),
        sa.CheckConstraint(
            "(embedding IS NOT NULL) = (state = 'ready')",
            name="ck_card_embeddings_vector_state",
        ),
        sa.ForeignKeyConstraint(
            ["card_id", "owner_id"],
            ["learning_cards.id", "learning_cards.owner_id"],
            name="fk_card_embeddings_owned_card",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "card_id", "owner_id", "model_version", name="pk_card_embeddings"
        ),
    )
    op.execute(
        "ALTER TABLE card_embeddings ALTER COLUMN embedding TYPE vector(512) USING embedding::vector(512)"
    )
    op.create_index(
        "ix_card_embeddings_owner_state_retry",
        "card_embeddings",
        ["owner_id", "model_version", "state", "next_retry_at"],
    )


def downgrade() -> None:
    op.drop_table("card_embeddings")
    op.drop_constraint(
        "ck_learning_cards_semantic_content_hash", "learning_cards", type_="check"
    )
    op.drop_column("learning_cards", "semantic_content_hash")
    # The extension can be shared by other database objects; retain it.
