"""Per-request context shared by responses, errors, and future logs."""

from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import Request, Response


async def add_request_id(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Generate a request UUID and expose it in the response header."""

    request_id = uuid4()
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = str(request_id)
    return response
