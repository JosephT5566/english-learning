"""Shared real-PostgreSQL integration fixtures."""

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine, make_url

import app.embedding_backfill as backfill
from app import confirmed_imports, database, imports, main
from app.config import DEFAULT_DATABASE_URL
from tests.integration.rls import (
    grant_restricted_role,
    owner_session_factory,
    restrict_engine,
)

ALEMBIC_CONFIG_PATH = Path(__file__).parents[2] / "alembic.ini"


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


@pytest.fixture
def migrated_database_engine(
    monkeypatch: pytest.MonkeyPatch,
    temporary_database_url: str,
) -> Iterator[Engine]:
    """Yield an isolated PostgreSQL database migrated to the current head."""

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", temporary_database_url)
    command.upgrade(Config(ALEMBIC_CONFIG_PATH), "head")
    engine = create_engine(temporary_database_url)

    grant_restricted_role(engine)
    runtime_engines = []
    original_sessionmaker = database.sessionmaker
    original_create_engine = database.create_database_engine

    def restricted_sessionmaker(*, bind, **options):
        if bind not in runtime_engines:
            # Seed, schema and inspection operations keep using the owner engine.
            runtime = create_engine(bind.url, pool_size=1, max_overflow=0)
            restrict_engine(runtime)
            runtime_engines.append(runtime)
            bind = runtime
        return original_sessionmaker(bind=bind, **options)

    def runtime_engine(settings):
        runtime = original_create_engine(settings)
        restrict_engine(runtime)
        runtime_engines.append(runtime)
        return runtime

    monkeypatch.setattr(main, "create_database_engine", runtime_engine)
    monkeypatch.setattr(backfill, "create_database_engine", runtime_engine)
    # Retired operator imports are tested only as owner maintenance operations.
    monkeypatch.setattr(
        confirmed_imports, "create_database_session_factory", owner_session_factory
    )
    monkeypatch.setattr(
        imports, "create_database_session_factory", owner_session_factory
    )

    monkeypatch.setattr(database, "sessionmaker", restricted_sessionmaker)
    try:
        yield engine
    finally:
        for runtime in runtime_engines:
            runtime.dispose()
        engine.dispose()
