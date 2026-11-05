"""Transaction-local app identities on a reused non-owner PostgreSQL connection."""

import os
from uuid import uuid4

import pytest
from sqlalchemy import text

from app import database
from tests.integration.rls import RLS_TABLES
from tests.integration.test_multilingual_domain_fixture import load_multilingual_fixture

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1",
        reason="requires disposable PostgreSQL",
    ),
]


def identity(session):
    return session.execute(
        text("""
        SELECT pg_backend_pid(), current_user,
               current_setting('app.user_id', true),
               current_setting('app.public_deck_id', true)
    """)
    ).one()


@pytest.mark.parametrize("finish", ["commit", "rollback"])
def test_owner_survives_new_transactions_without_leaking_to_next_session(
    migrated_database_engine, finish
):
    load_multilingual_fixture(migrated_database_engine)
    factory = database.create_database_session_factory(migrated_database_engine)
    with migrated_database_engine.connect() as owner_connection:
        assert owner_connection.scalar(text("SELECT count(*) FROM learning_decks")) > 0
    with factory() as session:
        session.execute(text("SELECT id FROM users"))
        database.bind_owner(session, 1)
        first = identity(session)
        assert first[1:] == ("app_rls_test", "1", None)
        getattr(session, finish)()
        assert identity(session) == first
        assert session.scalar(text("SELECT count(*) FROM learning_decks")) > 0
    with factory() as session:
        clean = identity(session)
        assert clean[:2] == first[:2]
        assert not clean[2] and not clean[3]
        for table in RLS_TABLES:
            assert session.scalar(text(f"SELECT count(*) FROM {table}")) == 0
        database.bind_owner(session, 2)
        assert identity(session)[2] == "2"
        assert session.scalar(text("SELECT count(*) FROM learning_decks")) == 0


def test_transaction_helper_binds_before_first_query(migrated_database_engine):
    factory = database.create_database_session_factory(migrated_database_engine)
    with database.database_transaction(factory, owner_id=7) as session:
        assert identity(session)[2:] == ("7", None)
        session.commit()
        assert identity(session)[2:] == ("7", None)


def test_public_deck_context_is_readonly_and_excludes_owner(migrated_database_engine):
    factory = database.create_database_session_factory(migrated_database_engine)
    deck = uuid4()
    with database.database_transaction(factory) as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        database.bind_public_deck(session, deck)
        assert identity(session)[2:] == (None, str(deck))
        assert session.scalar(text("SHOW transaction_read_only")) == "on"
        with pytest.raises(ValueError, match="identity"):
            database.bind_owner(session, 1)
    with (
        database.database_transaction(factory, owner_id=1) as session,
        pytest.raises(ValueError, match="identity"),
    ):
        database.bind_public_deck(session, deck)
    with factory() as session:
        assert not identity(session)[2] and not identity(session)[3]
