"""CORS policy sourced from validated lifespan configuration."""

from collections.abc import Awaitable, Callable
from typing import Any

from starlette.middleware.cors import CORSMiddleware

# A middleware is itself an ASGI application: it receives one scope and delegates to
# the next application through the same receive/send callables.
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
        # Lifespan runs before settings are available. Forward lifespan and any future
        # non-HTTP protocols unchanged so this wrapper only owns browser HTTP policy.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Settings are loaded into app.state during lifespan startup. Build the standard
        # Starlette middleware on the first HTTP request, then reuse its immutable policy.
        if self.configured_app is None:
            settings = scope["app"].state.settings
            self.configured_app = CORSMiddleware(
                app=self.app,
                allow_origins=list(settings.cors_allowed_origins),
                # Authentication uses an Authorization bearer token, not browser cookies.
                allow_credentials=False,
                allow_methods=["GET", "POST", "PATCH", "DELETE"],
                allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
                # Let the frontend include the correlation ID in support diagnostics.
                expose_headers=["X-Request-ID"],
                # Browsers may cache a successful preflight for ten minutes.
                max_age=600,
            )

        # CORSMiddleware answers valid OPTIONS preflights itself and delegates ordinary
        # requests to the request-ID middleware and router registered inside it.
        await self.configured_app(scope, receive, send)
