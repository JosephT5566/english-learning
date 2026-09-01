"""SQLAlchemy engine, session, transaction, and readiness operations."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

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


def create_database_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create the application-scoped factory for short-lived database sessions.

    Args:
        engine: Application-scoped SQLAlchemy engine used by every session.

    Returns:
        A factory configured to keep loaded values usable after a commit.
    """

    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def database_transaction(
    session_factory: sessionmaker[Session],
) -> Iterator[Session]:
    """Own one session and transaction from creation through cleanup.

    The unit of work commits only after its caller completes successfully. Any
    exception, including a failed commit, triggers a rollback before the original
    exception is re-raised. The session is closed in every outcome.

    Args:
        session_factory: Application-scoped factory used to create one session.

    Yields:
        The session participating in the owned transaction.

    Raises:
        Exception: Re-raises any error from the caller or transaction commit.
    """

    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


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
