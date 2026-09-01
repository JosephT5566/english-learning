from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import load_settings
from app.database import create_database_engine, dispose_database_engine
from app.health import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = load_settings()
    database_engine = create_database_engine(settings)

    try:
        # save application-level state to app.
        app.state.settings = settings
        app.state.database_engine = database_engine
        yield
    finally:
        dispose_database_engine(database_engine)


def create_app() -> FastAPI:
    app = FastAPI(title="English Learning API", lifespan=lifespan)
    app.include_router(health_router)
    return app
