"""Restricted-role helpers for testing PostgreSQL policies independently of the app."""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import Connection, Engine, text

RLS_TABLES = (
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


def grant_restricted_role(engine: Engine) -> None:
    """Create the cluster role safely and grant access in this disposable database."""

    with engine.begin() as connection:
        connection.exec_driver_sql("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_rls_test') THEN
                    CREATE ROLE app_rls_test NOLOGIN NOSUPERUSER NOBYPASSRLS
                        NOCREATEDB NOCREATEROLE;
                END IF;
            EXCEPTION WHEN duplicate_object OR unique_violation THEN
                NULL;
            END $$
        """)
        connection.exec_driver_sql("GRANT USAGE ON SCHEMA public TO app_rls_test")
        connection.exec_driver_sql(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
            "TO app_rls_test"
        )
        connection.exec_driver_sql(
            "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_rls_test"
        )


def set_restricted_context(
    connection: Connection,
    *,
    owner_id: int | str | None = None,
    public_deck_id: UUID | None = None,
) -> None:
    """Switch role and optionally set identities for the current transaction only."""

    connection.exec_driver_sql("SET LOCAL ROLE app_rls_test")
    if owner_id is not None:
        connection.execute(
            text("SELECT set_config('app.user_id', :value, true)"),
            {"value": str(owner_id)},
        )
    if public_deck_id is not None:
        connection.execute(
            text("SELECT set_config('app.public_deck_id', :value, true)"),
            {"value": str(public_deck_id)},
        )


@contextmanager
def restricted_connection(
    engine: Engine,
    owner_id: int | str | None = None,
    public_deck_id: UUID | None = None,
) -> Iterator[Connection]:
    """Yield one restricted transaction after grant_restricted_role has run."""

    with engine.begin() as connection:
        set_restricted_context(
            connection, owner_id=owner_id, public_deck_id=public_deck_id
        )
        yield connection
