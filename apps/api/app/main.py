from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import load_settings
from app.health import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    app.state.settings = load_settings()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="English Learning API", lifespan=lifespan)
    app.include_router(health_router)
    return app
