"""Add confirmed CSV import audit and source mappings.

Revision ID: 20260910_0005
Revises: 20260909_0004
Create Date: 2026-09-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260910_0005"
down_revision: str | Sequence[str] | None = "20260909_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create confirmed-import run and source-to-card mapping tables."""

    op.create_unique_constraint(
        "uq_import_runs_id_owner_deck_namespace",
        "import_runs",
        ["id", "owner_id", "deck_id", "source_namespace"],
    )
    op.create_unique_constraint(
        "uq_import_items_id_run_row_hashes",
        "import_items",
        [
            "id",
            "run_id",
            "row_number",
            "source_identity_hash",
            "content_hash",
        ],
    )

    op.create_table(
        "confirmed_import_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("approved_dry_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("deck_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_namespace", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("eligible_row_count", sa.Integer(), nullable=False),
        sa.Column("imported_card_count", sa.Integer(), nullable=False),
        sa.Column("source_mapping_count", sa.Integer(), nullable=False),
        sa.Column("tag_count", sa.Integer(), nullable=False),
        sa.Column("card_tag_association_count", sa.Integer(), nullable=False),
        sa.Column("review_state_count", sa.Integer(), nullable=False),
        sa.Column("archived_card_count", sa.Integer(), nullable=False),
        sa.Column("reconciliation_status", sa.Text(), nullable=False),
        sa.Column("reconciliation_result", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "char_length(btrim(source_namespace)) BETWEEN 1 AND 100",
            name="ck_confirmed_import_runs_namespace_length",
        ),
        sa.CheckConstraint(
            "status = 'completed'",
            name="ck_confirmed_import_runs_status_completed",
        ),
        sa.CheckConstraint(
            "eligible_row_count >= 0 "
            "AND imported_card_count >= 0 "
            "AND source_mapping_count >= 0 "
            "AND tag_count >= 0 "
            "AND card_tag_association_count >= 0 "
            "AND review_state_count >= 0 "
            "AND archived_card_count >= 0",
            name="ck_confirmed_import_runs_counts_nonnegative",
        ),
        sa.CheckConstraint(
            "eligible_row_count = imported_card_count "
            "AND eligible_row_count = source_mapping_count "
            "AND eligible_row_count = review_state_count",
            name="ck_confirmed_import_runs_primary_counts_agree",
        ),
        sa.CheckConstraint(
            "archived_card_count <= eligible_row_count",
            name="ck_confirmed_import_runs_archived_count_bounded",
        ),
        sa.CheckConstraint(
            "reconciliation_status IN ('pending', 'passed', 'failed')",
            name="ck_confirmed_import_runs_reconciliation_status",
        ),
        sa.CheckConstraint(
            "(reconciliation_status = 'pending' "
            "AND reconciliation_result IS NULL AND reconciled_at IS NULL) "
            "OR (reconciliation_status IN ('passed', 'failed') "
            "AND reconciliation_result IS NOT NULL AND reconciled_at IS NOT NULL)",
            name="ck_confirmed_import_runs_reconciliation_fields",
        ),
        sa.CheckConstraint(
            "reconciliation_result IS NULL "
            "OR jsonb_typeof(reconciliation_result) = 'object'",
            name="ck_confirmed_import_runs_reconciliation_object",
        ),
        sa.CheckConstraint(
            "completed_at >= created_at",
            name="ck_confirmed_import_runs_timestamps_ordered",
        ),
        sa.CheckConstraint(
            "reconciled_at IS NULL OR reconciled_at >= completed_at",
            name="ck_confirmed_import_runs_reconciled_after_complete",
        ),
        sa.ForeignKeyConstraint(
            ["approved_dry_run_id", "owner_id", "deck_id", "source_namespace"],
            [
                "import_runs.id",
                "import_runs.owner_id",
                "import_runs.deck_id",
                "import_runs.source_namespace",
            ],
            name="fk_confirmed_import_runs_approved_dry_run",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_confirmed_import_runs"),
        sa.UniqueConstraint(
            "approved_dry_run_id",
            name="uq_confirmed_import_runs_approved_dry_run",
        ),
        sa.UniqueConstraint(
            "owner_id",
            "source_namespace",
            name="uq_confirmed_import_runs_owner_namespace",
        ),
        sa.UniqueConstraint(
            "id",
            "approved_dry_run_id",
            "owner_id",
            "source_namespace",
            name="uq_confirmed_import_runs_mapping_scope",
        ),
    )

    op.create_table(
        "confirmed_import_mappings",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column(
            "confirmed_import_run_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("approved_dry_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approved_import_item_id", sa.BigInteger(), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("source_namespace", sa.Text(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("source_identity_hash", sa.String(length=64), nullable=False),
        sa.Column("canonical_content_hash", sa.String(length=64), nullable=False),
        sa.Column("learning_card_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(btrim(source_namespace)) BETWEEN 1 AND 100",
            name="ck_confirmed_import_mappings_namespace_length",
        ),
        sa.CheckConstraint(
            "row_number >= 2",
            name="ck_confirmed_import_mappings_row_number",
        ),
        sa.CheckConstraint(
            "source_identity_hash ~ '^[0-9a-f]{64}$'",
            name="ck_confirmed_import_mappings_identity_hash",
        ),
        sa.CheckConstraint(
            "canonical_content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_confirmed_import_mappings_content_hash",
        ),
        sa.CheckConstraint(
            "outcome = 'created'",
            name="ck_confirmed_import_mappings_outcome_created",
        ),
        sa.ForeignKeyConstraint(
            [
                "confirmed_import_run_id",
                "approved_dry_run_id",
                "owner_id",
                "source_namespace",
            ],
            [
                "confirmed_import_runs.id",
                "confirmed_import_runs.approved_dry_run_id",
                "confirmed_import_runs.owner_id",
                "confirmed_import_runs.source_namespace",
            ],
            name="fk_confirmed_import_mappings_apply_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "approved_import_item_id",
                "approved_dry_run_id",
                "row_number",
                "source_identity_hash",
                "canonical_content_hash",
            ],
            [
                "import_items.id",
                "import_items.run_id",
                "import_items.row_number",
                "import_items.source_identity_hash",
                "import_items.content_hash",
            ],
            name="fk_confirmed_import_mappings_approved_item",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["learning_card_id", "owner_id"],
            ["learning_cards.id", "learning_cards.owner_id"],
            name="fk_confirmed_import_mappings_owned_card",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_confirmed_import_mappings"),
        sa.UniqueConstraint(
            "owner_id",
            "source_namespace",
            "source_identity_hash",
            name="uq_confirmed_import_mappings_source_identity",
        ),
        sa.UniqueConstraint(
            "learning_card_id",
            name="uq_confirmed_import_mappings_learning_card",
        ),
        sa.UniqueConstraint(
            "confirmed_import_run_id",
            "row_number",
            name="uq_confirmed_import_mappings_run_row",
        ),
    )


def downgrade() -> None:
    """Remove confirmed-import mappings and run audit records."""

    op.drop_table("confirmed_import_mappings")
    op.drop_table("confirmed_import_runs")
    op.drop_constraint(
        "uq_import_items_id_run_row_hashes",
        "import_items",
        type_="unique",
    )
    op.drop_constraint(
        "uq_import_runs_id_owner_deck_namespace",
        "import_runs",
        type_="unique",
    )
