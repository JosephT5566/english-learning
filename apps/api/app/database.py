from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.config import Settings


def create_database_engine(settings: Settings) -> Engine:
    return create_engine(
        settings.database_url.get_secret_value(),
        connect_args={
            "connect_timeout": settings.database_connect_timeout_seconds,
        },
        pool_pre_ping=True,
    )


def dispose_database_engine(engine: Engine) -> None:
    engine.dispose()
