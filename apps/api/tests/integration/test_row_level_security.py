"""Exercise owner isolation using a role that cannot bypass PostgreSQL RLS."""

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import Connection, Engine, MetaData, Table, text
from sqlalchemy.exc import DBAPIError

from tests.integration.rls import (
    RLS_TABLES,
    grant_restricted_role,
    restricted_connection,
    set_restricted_context,
)
from tests.integration.test_confirmed_import_schema import (
    SOURCE_NAMESPACE,
    _approved_item,
    _insert_confirmed_run,
    _persist_dry_run,
)
from tests.integration.test_learning_cards import insert_deck, insert_user

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1",
        reason="set RUN_POSTGRES_INTEGRATION_TESTS=1 to run PostgreSQL integration tests",
    ),
]


def seed_owner(engine: Engine) -> int:
    """Seed all eleven tables as the owner, respecting composite foreign keys."""

    owner = insert_user(engine)
    deck = insert_deck(engine, owner_id=owner)
    dry_run = _persist_dry_run(
        engine,
        owner_id=owner,
        deck_id=deck,
        snapshot_captured_at=datetime(2026, 11, 5, tzinfo=UTC),
    )
    with engine.begin() as connection:
        params = {"owner": owner, "deck": deck, "key": uuid4()}
        card = connection.execute(
            text("""
                INSERT INTO learning_cards (owner_id, deck_id, term, meaning)
                VALUES (:owner, :deck, 'RLS test', 'synthetic meaning') RETURNING id
            """),
            params,
        ).scalar_one()
        params["card"] = card
        tag = connection.execute(
            text("""
                INSERT INTO tags (owner_id, display_name, normalized_name)
                VALUES (:owner, 'RLS', 'rls') RETURNING id
            """),
            params,
        ).scalar_one()
        params["tag"] = tag
        connection.execute(
            text("""
                INSERT INTO learning_card_tags (owner_id, card_id, tag_id)
                VALUES (:owner, :card, :tag)
            """),
            params,
        )
        batch = connection.execute(
            text("""
                INSERT INTO review_batches (owner_id, idempotency_key, request_hash,
                    reviewed_at, algorithm_version, item_count)
                VALUES (:owner, :key, 'rls-test', CURRENT_TIMESTAMP, 'srs-v1', 1)
                RETURNING id
            """),
            params,
        ).scalar_one()
        params["batch"] = batch
        connection.execute(
            text("""
                INSERT INTO review_states (owner_id, card_id, review_stage,
                    ease_factor, interval_days, next_review_at, version)
                VALUES (:owner, :card, 1, 2.5, 0, CURRENT_TIMESTAMP, 1)
            """),
            params,
        )
        connection.execute(
            text("""
                INSERT INTO review_events (owner_id, batch_id, card_id, decision,
                    quality, previous_review_stage, resulting_review_stage,
                    previous_ease_factor, resulting_ease_factor,
                    previous_interval_days, resulting_interval_days,
                    resulting_last_reviewed_at, previous_next_review_at,
                    resulting_next_review_at, previous_version, resulting_version,
                    algorithm_version, reviewed_at)
                VALUES (:owner, :batch, :card, 'yes', 5, 1, 2, 2.5, 2.5, 0, 1,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                    1, 2, 'srs-v1', CURRENT_TIMESTAMP)
            """),
            params,
        )
        connection.execute(
            text("""
                INSERT INTO card_embeddings
                    (owner_id, card_id, model_version, content_hash, state)
                VALUES (:owner, :card, 'rls-test', repeat('a', 64), 'pending')
            """),
            params,
        )
        confirmed = _insert_confirmed_run(
            connection, dry_run_id=dry_run, owner_id=owner, deck_id=deck
        )
        item = _approved_item(connection, dry_run)
        connection.execute(
            text("""
                INSERT INTO confirmed_import_mappings (
                    confirmed_import_run_id, approved_dry_run_id,
                    approved_import_item_id, owner_id, source_namespace,
                    row_number, source_identity_hash, canonical_content_hash,
                    learning_card_id, outcome)
                VALUES (:confirmed, :dry_run, :item, :owner, :namespace,
                    :row, :identity, :hash, :card, 'created')
            """),
            {
                "confirmed": confirmed,
                "dry_run": dry_run,
                "item": item.id,
                "owner": owner,
                "namespace": SOURCE_NAMESPACE,
                "row": item.row_number,
                "identity": item.source_identity_hash,
                "hash": item.content_hash,
                "card": card,
            },
        )
    return owner


@pytest.fixture
def rls_data(migrated_database_engine: Engine):
    engine = migrated_database_engine
    owners = (seed_owner(engine), seed_owner(engine))
    grant_restricted_role(engine)
    # Repeat setup to prove the cluster-wide role is reusable across databases/tests.
    grant_restricted_role(engine)
    metadata = MetaData()
    tables = {name: Table(name, metadata, autoload_with=engine) for name in RLS_TABLES}
    with engine.connect() as connection:
        rows = {
            name: {
                owner: dict(
                    connection.execute(table.select().where(table.c.owner_id == owner))
                    .mappings()
                    .one()
                )
                for owner in owners
            }
            for name, table in tables.items()
        }
        role = connection.execute(
            text("""
                SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole, rolcanlogin
                FROM pg_roles WHERE rolname = 'app_rls_test'
            """)
        ).one()
        assert tuple(role) == (False, False, False, False, False)
    return engine, owners, tables, rows


def assert_insert_denied(connection: Connection, table: Table, row: dict) -> None:
    # RLS must reject the candidate, rather than a uniqueness/FK/NOT NULL constraint.
    values = {key: value for key, value in row.items() if table.c[key].identity is None}
    with pytest.raises(DBAPIError) as caught, connection.begin_nested():
        connection.execute(table.insert().values(**values))
    assert caught.value.orig.sqlstate == "42501"
    assert "row-level security policy" in str(caught.value.orig)


@pytest.mark.parametrize("name", RLS_TABLES)
def test_owner_isolation_for_every_table(rls_data, name: str) -> None:
    engine, (owner_a, owner_b), tables, rows = rls_data
    table = tables[name]
    with restricted_connection(engine, owner_a) as connection:
        assert [dict(row) for row in connection.execute(table.select()).mappings()] == [
            rows[name][owner_a]
        ]
        assert (
            connection.execute(
                table.update()
                .where(table.c.owner_id == owner_b)
                .values(owner_id=owner_b)
            ).rowcount
            == 0
        )
        assert (
            connection.execute(
                table.delete().where(table.c.owner_id == owner_b)
            ).rowcount
            == 0
        )
        assert_insert_denied(connection, table, rows[name][owner_b])
        # WITH CHECK also prevents changing an owned row into another owner's row.
        with pytest.raises(DBAPIError) as caught, connection.begin_nested():
            connection.execute(
                table.update()
                .where(table.c.owner_id == owner_a)
                .values(owner_id=owner_b)
            )
        assert caught.value.orig.sqlstate == "42501"


@pytest.mark.parametrize("name", RLS_TABLES)
@pytest.mark.parametrize("owner", [None, "", 9223372036854775807])
def test_missing_empty_or_unknown_owner_fails_closed(rls_data, name, owner) -> None:
    engine, (owner_a, _), tables, rows = rls_data
    with restricted_connection(engine, owner) as connection:
        assert connection.execute(tables[name].select()).all() == []
        assert_insert_denied(connection, tables[name], rows[name][owner_a])


@pytest.mark.parametrize("finish", ["commit", "rollback"])
@pytest.mark.parametrize("context", ["owner", "public"])
def test_identity_does_not_survive_transaction(rls_data, finish, context) -> None:
    engine, (owner_a, _), tables, rows = rls_data
    public_deck = rows["learning_decks"][owner_a]["id"]
    with engine.connect() as connection:
        transaction = connection.begin()
        set_restricted_context(
            connection,
            owner_id=owner_a if context == "owner" else None,
            public_deck_id=public_deck if context == "public" else None,
        )
        assert connection.execute(tables["learning_cards"].select()).all()
        getattr(transaction, finish)()
        with connection.begin():
            set_restricted_context(connection)
            for setting in ("app.user_id", "app.public_deck_id"):
                assert connection.execute(
                    text("SELECT current_setting(:setting, true)"), {"setting": setting}
                ).scalar_one() in (None, "")
            for table in tables.values():
                assert connection.execute(table.select()).all() == []


def test_public_deck_only_grants_select(rls_data) -> None:
    engine, (owner_a, _), tables, rows = rls_data
    deck = rows["learning_decks"][owner_a]["id"]
    with restricted_connection(engine, public_deck_id=deck) as connection:
        for name, table in tables.items():
            visible = connection.execute(table.select()).mappings().all()
            if name in ("learning_decks", "learning_cards"):
                assert [dict(row) for row in visible] == [rows[name][owner_a]]
                assert (
                    connection.execute(table.update().values(owner_id=owner_a)).rowcount
                    == 0
                )
                assert connection.execute(table.delete()).rowcount == 0
            else:
                assert visible == []
            assert_insert_denied(connection, table, rows[name][owner_a])


def test_known_foreign_deck_cannot_expose_cards(rls_data) -> None:
    engine, (owner_a, owner_b), _, rows = rls_data
    with restricted_connection(engine, owner_a) as connection:
        assert (
            connection.execute(
                text("""
                SELECT c.id FROM learning_cards c
                JOIN learning_decks d ON (d.id, d.owner_id) = (c.deck_id, c.owner_id)
                WHERE d.id = :deck
            """),
                {"deck": rows["learning_decks"][owner_b]["id"]},
            ).all()
            == []
        )
