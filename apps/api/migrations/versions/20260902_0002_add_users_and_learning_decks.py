"""Add owned multilingual learning decks.

Revision ID: 20260902_0002
Revises: 20260901_0001
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260902_0002"
down_revision: str | Sequence[str] | None = "20260901_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create users and their language-aware learning decks."""

    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column("google_subject", sa.Text(), nullable=False),
        sa.Column("normalized_email", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(btrim(google_subject)) > 0",
            name="ck_users_google_subject_nonblank",
        ),
        sa.CheckConstraint(
            "char_length(btrim(normalized_email)) > 0",
            name="ck_users_normalized_email_nonblank",
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name="ck_users_timestamps_ordered",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint(
            "google_subject",
            name="uq_users_google_subject",
        ),
    )

    op.create_table(
        "learning_decks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("target_language", sa.Text(), nullable=False),
        sa.Column("explanation_language", sa.Text(), nullable=False),
        sa.Column(
            "creation_idempotency_key",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("creation_request_hash", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(btrim(title)) BETWEEN 1 AND 100",
            name="ck_learning_decks_title_length",
        ),
        sa.CheckConstraint(
            "target_language IN ('en', 'ja')",
            name="ck_learning_decks_target_language_supported",
        ),
        sa.CheckConstraint(
            "explanation_language IN ('en', 'ja', 'zh-TW')",
            name="ck_learning_decks_explanation_language_supported",
        ),
        sa.CheckConstraint(
            "(creation_idempotency_key IS NULL) = (creation_request_hash IS NULL)",
            name="ck_learning_decks_creation_replay_fields_paired",
        ),
        sa.CheckConstraint(
            "creation_request_hash IS NULL "
            "OR char_length(btrim(creation_request_hash)) > 0",
            name="ck_learning_decks_creation_request_hash_nonblank",
        ),
        sa.CheckConstraint(
            "version >= 1",
            name="ck_learning_decks_version_positive",
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name="ck_learning_decks_timestamps_ordered",
        ),
        sa.CheckConstraint(
            "archived_at IS NULL OR archived_at >= created_at",
            name="ck_learning_decks_archive_not_before_creation",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_learning_decks_owner_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_learning_decks"),
        sa.UniqueConstraint(
            "id",
            "owner_id",
            name="uq_learning_decks_id_owner_id",
        ),
    )
    op.create_index(
        "ix_learning_decks_owner_language_archive",
        "learning_decks",
        ["owner_id", "target_language", "archived_at"],
        unique=False,
    )
    op.create_index(
        "uq_learning_decks_owner_creation_idempotency_key",
        "learning_decks",
        ["owner_id", "creation_idempotency_key"],
        unique=True,
        postgresql_where=sa.text("creation_idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    """Remove learning decks before their owning users."""

    op.drop_index(
        "uq_learning_decks_owner_creation_idempotency_key",
        table_name="learning_decks",
    )
    op.drop_index(
        "ix_learning_decks_owner_language_archive",
        table_name="learning_decks",
    )
    op.drop_table("learning_decks")
    op.drop_table("users")
