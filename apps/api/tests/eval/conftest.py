"""Reuse the disposable, migrated PostgreSQL fixtures without moving existing tests."""

from tests.integration.conftest import (  # noqa: F401
    migrated_database_engine,
    temporary_database_url,
)
