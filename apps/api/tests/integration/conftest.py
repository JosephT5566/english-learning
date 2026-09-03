"""Shared real-PostgreSQL integration fixtures."""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine, make_url

from app.config import DEFAULT_DATABASE_URL


def database_url_for(database_name: str) -> URL:
    """Return the disposable local URL with a selected database name."""

    return make_url(DEFAULT_DATABASE_URL).set(database=database_name)


def execute_database_ddl(engine: Engine, statement: str) -> None:
    """Execute database-level DDL outside a transaction."""

    with engine.connect() as connection:
        connection.exec_driver_sql(statement)


@pytest.fixture
def temporary_database_url() -> Iterator[str]:
    """Create and remove an isolated PostgreSQL database for one test."""

    database_name = f"api_test_{uuid4().hex}"
    admin_engine = create_engine(
        database_url_for("postgres"),
        isolation_level="AUTOCOMMIT",
    )
    execute_database_ddl(admin_engine, f'CREATE DATABASE "{database_name}"')

    try:
        yield database_url_for(database_name).render_as_string(hide_password=False)
    finally:
        execute_database_ddl(admin_engine, f'DROP DATABASE "{database_name}"')
        admin_engine.dispose()
