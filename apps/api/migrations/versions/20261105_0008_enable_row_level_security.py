"""Enable transaction-scoped owner isolation and public deck reads.

Revision ID: 20261105_0008
Revises: 20261105_0007
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261105_0008"
down_revision: str | Sequence[str] | None = "20261105_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OWNER_TABLES = (
    "learning_decks",
    "learning_cards",
    "tags",
    "learning_card_tags",
    "review_batches",
    "review_states",
    "review_events",
    "import_runs",
    "confirmed_import_runs",
    "confirmed_import_mappings",
    "card_embeddings",
)
PUBLIC_DECK_COLUMNS = {"learning_decks": "id", "learning_cards": "deck_id"}
OWNER_PREDICATE = "owner_id = NULLIF(current_setting('app.user_id', true), '')::bigint"


def upgrade() -> None:
    """Fail closed for runtime roles while preserving the table owner's bypass."""

    for table in OWNER_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_owner_isolation ON {table} FOR ALL "
            f"USING ({OWNER_PREDICATE}) WITH CHECK ({OWNER_PREDICATE})"
        )
    for table, column in PUBLIC_DECK_COLUMNS.items():
        op.execute(
            f"CREATE POLICY {table}_public_deck_read ON {table} FOR SELECT "
            f"USING ({column} = "
            "NULLIF(current_setting('app.public_deck_id', true), '')::uuid)"
        )


def downgrade() -> None:
    """Remove every policy before restoring unrestricted pre-migration tables."""

    for table in reversed(PUBLIC_DECK_COLUMNS):
        op.execute(f"DROP POLICY {table}_public_deck_read ON {table}")
    for table in reversed(OWNER_TABLES):
        op.execute(f"DROP POLICY {table}_owner_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
