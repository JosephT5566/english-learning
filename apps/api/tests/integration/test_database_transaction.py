"""PostgreSQL integration tests for transaction ownership."""

import os

import pytest
from sqlalchemy import text

from app.config import Settings
from app.database import (
    create_database_engine,
    create_database_session_factory,
    database_transaction,
    dispose_database_engine,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1",
        reason="set RUN_POSTGRES_INTEGRATION_TESTS=1 to run PostgreSQL integration tests",
    ),
]


def test_transaction_commits_success_and_rolls_back_failure_in_postgres(
    temporary_database_url: str,
) -> None:
    settings = Settings.model_validate(
        {
            "app_env": "test",
            "database_url": temporary_database_url,
        }
    )
    engine = create_database_engine(settings)
    session_factory = create_database_session_factory(engine)

    try:
        with engine.begin() as connection:
            connection.execute(
                text("CREATE TABLE transaction_probe (value INTEGER NOT NULL)")
            )

        with database_transaction(session_factory) as session:
            session.execute(text("INSERT INTO transaction_probe VALUES (1)"))

        with (
            pytest.raises(RuntimeError, match="rollback probe"),
            database_transaction(session_factory) as session,
        ):
            session.execute(text("INSERT INTO transaction_probe VALUES (2)"))
            raise RuntimeError("rollback probe")

        with engine.connect() as connection:
            values = connection.execute(
                text("SELECT value FROM transaction_probe ORDER BY value")
            ).scalars()
            assert list(values) == [1]
    finally:
        dispose_database_engine(engine)
