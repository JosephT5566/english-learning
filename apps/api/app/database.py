"""SQLAlchemy engine, session, transaction, and readiness operations."""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from fastapi import Request
from sqlalchemy import Connection, create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, SessionTransaction, sessionmaker

from app.config import Settings
from app.errors import ApiError
from app.request_context import emit_review_outcome


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


def _apply_identity(session: Session, connection: Connection) -> None:
    if "owner_id" in session.info:
        connection.execute(
            text("SELECT set_config('app.user_id', :owner_id, true)"),
            {"owner_id": str(session.info["owner_id"])},
        )
    elif "public_deck_id" in session.info:
        connection.execute(
            text("SELECT set_config('app.public_deck_id', :deck_id, true)"),
            {"deck_id": str(session.info["public_deck_id"])},
        )


@event.listens_for(Session, "after_begin")
def _bind_transaction_identity(
    session: Session, _transaction: SessionTransaction, connection: Connection
) -> None:
    """Reapply transaction-local identity after every commit or rollback."""

    _apply_identity(session, connection)


def _bind_identity(session: Session, key: str, value: int | UUID) -> None:
    other = "public_deck_id" if key == "owner_id" else "owner_id"
    if other in session.info or (key in session.info and session.info[key] != value):
        raise ValueError("A session cannot change its database identity")
    session.info[key] = value
    if session.in_transaction():
        # Authentication may already have queried the unprotected users table.
        _apply_identity(session, session.connection())


def bind_owner(session: Session, owner_id: int) -> None:
    """Bind a positive internal owner to this short-lived session's transactions."""

    if type(owner_id) is not int or owner_id < 1:
        raise ValueError("owner_id must be a positive integer")
    _bind_identity(session, "owner_id", owner_id)


def bind_public_deck(session: Session, deck_id: UUID) -> None:
    """Bind only the export deck, after SET TRANSACTION READ ONLY has executed."""

    if not isinstance(deck_id, UUID):
        raise TypeError("deck_id must be a UUID")
    _bind_identity(session, "public_deck_id", deck_id)


def database_session(request: Request) -> Iterator[Session]:
    """Own one request transaction and sanitize database failures."""

    session = request.app.state.database_session_factory()
    try:
        yield session
        session.commit()
        emit_review_outcome(request)
    except IntegrityError:
        session.rollback()
        raise ApiError(
            status_code=422,
            code="validation_failed",
            message="The request did not pass validation.",
        ) from None
    except SQLAlchemyError:
        session.rollback()
        raise ApiError(
            status_code=503,
            code="database_unavailable",
            message="The database is temporarily unavailable.",
            retryable=True,
        ) from None
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def database_transaction(
    session_factory: sessionmaker[Session],
    *,
    owner_id: int | None = None,
) -> Iterator[Session]:
    """Own one session and transaction from creation through cleanup.

    The unit of work commits only after its caller completes successfully. Any
    exception, including a failed commit, triggers a rollback before the original
    exception is re-raised. The session is closed in every outcome.

    Args:
        session_factory: Application-scoped factory used to create one session.
        owner_id: Optional positive owner; omission leaves RLS fail-closed.

    Yields:
        The session participating in the owned transaction.

    Raises:
        Exception: Re-raises any error from the caller or transaction commit.
    """

    session = session_factory()
    try:
        if owner_id is not None:
            bind_owner(session, owner_id)
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
