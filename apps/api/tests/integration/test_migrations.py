"""PostgreSQL integration tests for the Alembic migration lifecycle."""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1",
        reason="set RUN_POSTGRES_INTEGRATION_TESTS=1 to run PostgreSQL integration tests",
    ),
]

ALEMBIC_CONFIG_PATH = Path(__file__).parents[2] / "alembic.ini"
BASELINE_REVISION = "20260901_0001"
DOMAIN_REVISION = "20260902_0002"


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

        assert set(inspect(database_engine).get_table_names()) == {
            "alembic_version",
            "learning_cards",
            "learning_decks",
            "users",
        }
        assert current_revision(database_engine) == DOMAIN_REVISION

        command.downgrade(alembic_config, BASELINE_REVISION)

        assert inspect(database_engine).get_table_names() == ["alembic_version"]
        assert current_revision(database_engine) == BASELINE_REVISION

        command.upgrade(alembic_config, "head")

        assert set(inspect(database_engine).get_table_names()) == {
            "alembic_version",
            "learning_cards",
            "learning_decks",
            "users",
        }
        assert current_revision(database_engine) == DOMAIN_REVISION

        command.downgrade(alembic_config, "base")

        assert inspect(database_engine).get_table_names() == ["alembic_version"]
        assert current_revision(database_engine) is None

        command.upgrade(alembic_config, "head")

        assert set(inspect(database_engine).get_table_names()) == {
            "alembic_version",
            "learning_cards",
            "learning_decks",
            "users",
        }
        assert current_revision(database_engine) == DOMAIN_REVISION
    finally:
        database_engine.dispose()
