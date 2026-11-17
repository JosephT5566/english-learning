"""PostgreSQL integration tests for the Alembic migration lifecycle."""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from tests.integration.rls import (
    AUTH_TABLES,
    RLS_TABLES,
    grant_restricted_role,
    restricted_connection,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1",
        reason="set RUN_POSTGRES_INTEGRATION_TESTS=1 to run PostgreSQL integration tests",
    ),
]

ALEMBIC_CONFIG_PATH = Path(__file__).parents[2] / "alembic.ini"
BASELINE_REVISION = "20260901_0001"
CONSENT_REVISION = "20261105_0007"
RLS_REVISION = "20261105_0008"
AUTH_REVISION = "20261117_0009"


EXPECTED_HEAD_TABLES = {
    "alembic_version",
    "card_embeddings",
    "confirmed_import_mappings",
    "confirmed_import_runs",
    "import_items",
    "import_runs",
    "learning_card_tags",
    "learning_cards",
    "learning_decks",
    "review_batches",
    "review_events",
    "review_states",
    "tags",
    "users",
    "auth_sessions",
    "auth_refresh_tokens",
    "auth_access_tokens",
}


def current_revision(engine: Engine) -> str | None:
    """Read the sole current Alembic revision, if one is recorded."""

    with engine.connect() as connection:
        return connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one_or_none()


def test_clean_postgres_database_supports_reversible_migration_cycle(
    monkeypatch: pytest.MonkeyPatch,
    temporary_database_url: str,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", temporary_database_url)
    alembic_config = Config(ALEMBIC_CONFIG_PATH)
    database_engine = create_engine(temporary_database_url)

    try:
        assert inspect(database_engine).get_table_names() == []

        command.upgrade(alembic_config, "head")

        assert set(inspect(database_engine).get_table_names()) == EXPECTED_HEAD_TABLES
        assert current_revision(database_engine) == AUTH_REVISION

        command.downgrade(alembic_config, BASELINE_REVISION)

        assert inspect(database_engine).get_table_names() == ["alembic_version"]
        assert current_revision(database_engine) == BASELINE_REVISION

        command.upgrade(alembic_config, "head")

        assert set(inspect(database_engine).get_table_names()) == EXPECTED_HEAD_TABLES
        assert current_revision(database_engine) == AUTH_REVISION

        command.downgrade(alembic_config, "base")

        assert inspect(database_engine).get_table_names() == ["alembic_version"]
        assert current_revision(database_engine) is None

        command.upgrade(alembic_config, "head")

        assert set(inspect(database_engine).get_table_names()) == EXPECTED_HEAD_TABLES
        assert current_revision(database_engine) == AUTH_REVISION
    finally:
        database_engine.dispose()


def assert_rls_catalog(engine: Engine, *, enabled: bool) -> None:
    """Check flags, policy scope, and predicates independently of migration constants."""

    with engine.connect() as connection:
        flags = connection.execute(
            text("""
            SELECT relname, relrowsecurity, relforcerowsecurity
            FROM pg_class JOIN pg_namespace n ON n.oid = relnamespace
            WHERE n.nspname = 'public' AND relname = ANY(:tables)
        """),
            {"tables": list(RLS_TABLES)},
        ).all()
        policies = (
            connection.execute(
                text("""
            SELECT tablename, policyname, permissive, roles, cmd, qual, with_check
            FROM pg_policies WHERE schemaname = 'public'
        """)
            )
            .mappings()
            .all()
        )
    assert len(flags) == 11
    assert all(row.relrowsecurity == enabled for row in flags)
    assert all(not row.relforcerowsecurity for row in flags)
    if not enabled:
        assert policies == []
        return
    expected = {(name, f"{name}_owner_isolation") for name in RLS_TABLES}
    expected |= {
        (name, f"{name}_public_deck_read")
        for name in ("learning_decks", "learning_cards")
    }
    assert {(p["tablename"], p["policyname"]) for p in policies} == expected
    for policy in policies:
        assert policy["permissive"] == "PERMISSIVE"
        assert policy["roles"] == ["public"]
        if policy["policyname"].endswith("_owner_isolation"):
            assert policy["cmd"] == "ALL"
            assert policy["qual"] == policy["with_check"]
            expression = policy["qual"]
            assert "owner_id =" in expression
            assert (
                "NULLIF(current_setting('app.user_id'::text, true), ''::text)"
                in expression
            )
            assert "::bigint" in expression
        else:
            assert policy["cmd"] == "SELECT"
            assert policy["with_check"] is None
            column = "id" if policy["tablename"] == "learning_decks" else "deck_id"
            assert policy["qual"] == (
                f"({column} = (NULLIF(current_setting('app.public_deck_id'::text, "
                "true), ''::text))::uuid)"
            )


def test_rls_upgrade_downgrade_and_reupgrade(
    migrated_database_engine: Engine,
) -> None:
    engine = migrated_database_engine
    config = Config(ALEMBIC_CONFIG_PATH)
    assert_rls_catalog(engine, enabled=True)
    command.downgrade(config, CONSENT_REVISION)
    assert current_revision(engine) == CONSENT_REVISION
    assert_rls_catalog(engine, enabled=False)
    command.upgrade(config, "head")
    assert current_revision(engine) == AUTH_REVISION
    assert_rls_catalog(engine, enabled=True)


def test_auth_revision_inherits_runtime_grants_and_reverses_cleanly(
    monkeypatch: pytest.MonkeyPatch,
    temporary_database_url: str,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", temporary_database_url)
    config = Config(ALEMBIC_CONFIG_PATH)
    engine = create_engine(temporary_database_url)
    try:
        command.upgrade(config, RLS_REVISION)
        grant_restricted_role(engine)
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rls_test"
            )
        command.upgrade(config, AUTH_REVISION)
        inspector = inspect(engine)
        assert {c["name"] for c in inspector.get_columns("auth_sessions")} == {
            "id",
            "user_id",
            "principal_kind",
            "created_at",
            "last_refreshed_at",
            "idle_expires_at",
            "absolute_expires_at",
            "revoked_at",
            "revoked_reason",
        }
        assert {c["name"] for c in inspector.get_columns("auth_refresh_tokens")} == {
            "token_hash",
            "session_id",
            "issued_at",
            "rotated_at",
        }
        assert {c["name"] for c in inspector.get_columns("auth_access_tokens")} == {
            "token_hash",
            "session_id",
            "expires_at",
        }
        for table in AUTH_TABLES:
            for fk in inspector.get_foreign_keys(table):
                assert fk["options"]["ondelete"] == "CASCADE"
        for table in ("auth_access_tokens", "auth_refresh_tokens"):
            assert inspector.get_pk_constraint(table)["constrained_columns"] == [
                "token_hash"
            ]
        indexes = {i["name"]: i for i in inspector.get_indexes("auth_refresh_tokens")}
        assert indexes["uq_auth_refresh_current"]["unique"]
        assert "rotated_at IS NULL" in str(
            indexes["uq_auth_refresh_current"]["dialect_options"]["postgresql_where"]
        )
        assert any(
            i["column_names"] == ["expires_at"]
            for i in inspector.get_indexes("auth_access_tokens")
        )
        with restricted_connection(engine) as connection:
            flags = (
                connection.execute(
                    text("""
                SELECT relrowsecurity FROM pg_class WHERE relname = ANY(:tables)
            """),
                    {"tables": list(AUTH_TABLES)},
                )
                .scalars()
                .all()
            )
            assert flags == [False] * 3
            for table in AUTH_TABLES:
                assert (
                    connection.execute(
                        text(f"SELECT count(*) FROM {table}")
                    ).scalar_one()
                    == 0
                )
                for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                    assert connection.execute(
                        text(
                            "SELECT has_table_privilege(current_user, :table, :privilege)"
                        ),
                        {"table": table, "privilege": privilege},
                    ).scalar_one()
        command.downgrade(config, RLS_REVISION)
        assert not set(AUTH_TABLES) & set(inspect(engine).get_table_names())
        assert_rls_catalog(engine, enabled=True)
        command.upgrade(config, AUTH_REVISION)
        assert set(inspect(engine).get_table_names()) == EXPECTED_HEAD_TABLES
    finally:
        engine.dispose()
