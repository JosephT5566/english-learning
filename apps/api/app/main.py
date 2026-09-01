"""FastAPI application construction and resource lifecycle."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import load_settings
from app.database import (
    create_database_engine,
    create_database_session_factory,
    dispose_database_engine,
)
from app.health import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Create and dispose application-scoped resources.

    Args:
        app: FastAPI application receiving the validated settings and engine.

    Yields:
        Control while the application is serving requests.
    """

    settings = load_settings()
    database_engine = create_database_engine(settings)
    database_session_factory = create_database_session_factory(database_engine)

    try:
        # Expose application-scoped resources to request handlers.
        app.state.settings = settings
        app.state.database_engine = database_engine
        app.state.database_session_factory = database_session_factory
        yield
    finally:
        dispose_database_engine(database_engine)


def create_app() -> FastAPI:
    """Build a new FastAPI application and register its routers.

    Returns:
        A FastAPI application whose resources are owned by lifespan.
    """

    app = FastAPI(title="English Learning API", lifespan=lifespan)
    app.include_router(health_router)
    return app
