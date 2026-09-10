"""Add persisted audit records for CSV import dry runs.

Revision ID: 20260909_0004
Revises: 20260903_0003
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260909_0004"
down_revision: str | Sequence[str] | None = "20260903_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create dry-run and row-diagnostic audit tables."""

    op.create_table(
        "import_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("deck_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_namespace", sa.Text(), nullable=False),
        sa.Column("source_snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("validator_version", sa.Text(), nullable=False),
        sa.Column("target_language", sa.Text(), nullable=False),
        sa.Column("snapshot_captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("accepted_rows", sa.Integer(), nullable=False),
        sa.Column("repaired_rows", sa.Integer(), nullable=False),
        sa.Column("rejected_rows", sa.Integer(), nullable=False),
        sa.Column("diagnostic_count", sa.Integer(), nullable=False),
        sa.Column("diagnostics", postgresql.JSONB(), nullable=False),
        sa.Column("diagnostics_truncated", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "char_length(btrim(source_namespace)) BETWEEN 1 AND 100",
            name="ck_import_runs_source_namespace_length",
        ),
        sa.CheckConstraint(
            "source_snapshot_hash ~ '^[0-9a-f]{64}$'",
            name="ck_import_runs_snapshot_hash_sha256",
        ),
        sa.CheckConstraint(
            "validator_version = 'csv-dry-run-v1'",
            name="ck_import_runs_validator_version_supported",
        ),
        sa.CheckConstraint(
            "target_language IN ('en', 'ja')",
            name="ck_import_runs_target_language_supported",
        ),
        sa.CheckConstraint(
            "status IN ('completed', 'rejected')",
            name="ck_import_runs_status_supported",
        ),
        sa.CheckConstraint(
            "total_rows >= 0 AND accepted_rows >= 0 AND repaired_rows >= 0 "
            "AND rejected_rows >= 0 AND diagnostic_count >= 0",
            name="ck_import_runs_counts_nonnegative",
        ),
        sa.CheckConstraint(
            "total_rows = accepted_rows + repaired_rows + rejected_rows",
            name="ck_import_runs_row_counts_agree",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(diagnostics) = 'array'",
            name="ck_import_runs_diagnostics_array",
        ),
        sa.CheckConstraint(
            "diagnostic_count >= jsonb_array_length(diagnostics)",
            name="ck_import_runs_diagnostic_counts_agree",
        ),
        sa.CheckConstraint(
            "completed_at >= created_at",
            name="ck_import_runs_timestamps_ordered",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_import_runs_owner_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["deck_id", "owner_id"],
            ["learning_decks.id", "learning_decks.owner_id"],
            name="fk_import_runs_deck_id_owner_id_learning_decks",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_import_runs"),
        sa.UniqueConstraint(
            "owner_id",
            "source_namespace",
            "source_snapshot_hash",
            "validator_version",
            name="uq_import_runs_owner_namespace_snapshot",
        ),
    )

    op.create_table(
        "import_items",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("source_identity_hash", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("diagnostic_count", sa.Integer(), nullable=False),
        sa.Column("diagnostics", postgresql.JSONB(), nullable=False),
        sa.Column("diagnostics_truncated", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "row_number >= 2",
            name="ck_import_items_row_number_data_row",
        ),
        sa.CheckConstraint(
            "source_identity_hash ~ '^[0-9a-f]{64}$'",
            name="ck_import_items_source_identity_hash_sha256",
        ),
        sa.CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_import_items_content_hash_sha256",
        ),
        sa.CheckConstraint(
            "outcome IN ('accepted', 'repaired', 'rejected')",
            name="ck_import_items_outcome_supported",
        ),
        sa.CheckConstraint(
            "diagnostic_count >= 0",
            name="ck_import_items_diagnostic_count_nonnegative",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(diagnostics) = 'array'",
            name="ck_import_items_diagnostics_array",
        ),
        sa.CheckConstraint(
            "diagnostic_count >= jsonb_array_length(diagnostics) "
            "AND (diagnostics_truncated OR "
            "diagnostic_count = jsonb_array_length(diagnostics))",
            name="ck_import_items_diagnostic_counts_agree",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["import_runs.id"],
            name="fk_import_items_run_id_import_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_import_items"),
        sa.UniqueConstraint(
            "run_id",
            "row_number",
            name="uq_import_items_run_id_row_number",
        ),
    )
    op.create_index(
        "ix_import_items_run_outcome_row",
        "import_items",
        ["run_id", "outcome", "row_number"],
        unique=False,
    )


def downgrade() -> None:
    """Remove dry-run and row-diagnostic audit tables."""

    op.drop_index("ix_import_items_run_outcome_row", table_name="import_items")
    op.drop_table("import_items")
    op.drop_table("import_runs")
