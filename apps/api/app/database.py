"""SQLAlchemy engine lifecycle and PostgreSQL readiness operations."""

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings


def create_database_engine(settings: Settings) -> Engine:
    """Create a lazy SQLAlchemy engine without opening a database connection.

    Args:
        settings: Validated settings containing the secret URL and timeout.

    Returns:
        An engine configured for Psycopg connections and stale-pool checks.
    """

    return create_engine(
        settings.database_url.get_secret_value(),
        connect_args={
            "connect_timeout": settings.database_connect_timeout_seconds,
        },
        pool_pre_ping=True,
    )


def dispose_database_engine(engine: Engine) -> None:
    """Dispose the engine and close all pooled database connections."""

    engine.dispose()


def check_database_readiness(engine: Engine) -> bool:
    """Return whether PostgreSQL successfully executes a lightweight query.

    Database exceptions are intentionally converted to `False` so callers do not
    expose internal connection details in readiness responses.

    Args:
        engine: Application-scoped SQLAlchemy engine.

    Returns:
        `True` when `SELECT 1` succeeds; otherwise `False`.
    """

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False

    return True
