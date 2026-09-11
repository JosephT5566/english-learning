"""CORS policy sourced from validated lifespan configuration."""

from collections.abc import Awaitable, Callable
from typing import Any

from starlette.middleware.cors import CORSMiddleware

ASGIApp = Callable[
    [
        dict[str, Any],
        Callable[[], Awaitable[dict[str, Any]]],
        Callable[[dict[str, Any]], Awaitable[None]],
    ],
    Awaitable[None],
]


class ConfiguredCORSMiddleware:
    """Initialize Starlette CORS lazily after application settings are loaded."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.configured_app: ASGIApp | None = None

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if self.configured_app is None:
            settings = scope["app"].state.settings
            self.configured_app = CORSMiddleware(
                app=self.app,
                allow_origins=list(settings.cors_allowed_origins),
                allow_credentials=False,
                allow_methods=["GET", "POST"],
                allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
                expose_headers=["X-Request-ID"],
                max_age=600,
            )
        await self.configured_app(scope, receive, send)
