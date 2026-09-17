"""Per-request correlation and allowlisted operational events."""

import json
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import Request, Response

from app.errors import error_response


def _failure_class(status_code: int, error_code: str | None) -> str:
    if status_code < 400:
        return "success"
    if error_code in {
        "authentication_required",
        "invalid_authentication",
        "identity_provider_unavailable",
    }:
        return "authentication"
    if error_code == "database_unavailable":
        return "database"
    if status_code == 409:
        return "conflict"
    if status_code == 422 or error_code == "invalid_request":
        return "validation"
    if status_code >= 500:
        return "unexpected"
    return "client_error"


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "unmatched"


def _method(request: Request) -> str:
    return (
        request.method
        if request.method
        in {"GET", "POST", "PATCH", "DELETE", "PUT", "HEAD", "OPTIONS"}
        else "OTHER"
    )


def _emit_request_event(request: Request, response: Response, elapsed_ms: int) -> None:
    """Write one bounded JSON line without any request or exception values."""

    error_code = getattr(request.state, "error_code", None)
    event: dict[str, str | int] = {
        "event": "http_request_completed",
        "request_id": str(request.state.request_id),
        "method": _method(request),
        "route": _route_template(request),
        "status_code": response.status_code,
        "duration_ms": elapsed_ms,
        "outcome": _failure_class(response.status_code, error_code),
    }
    if isinstance(error_code, str):
        event["error_code"] = error_code
    try:
        print(json.dumps(event, separators=(",", ":")), flush=True)
    except OSError:
        # A logging sink failure must not turn a completed card or review write
        # into an ambiguous HTTP failure.
        pass


async def add_request_id(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Correlate a response with one privacy-safe request completion event."""

    request_id = uuid4()
    request.state.request_id = request_id
    started_at = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:  # noqa: BLE001 - redact unexpected endpoint failures
        # Handle unanticipated endpoint failures inside this middleware so the
        # server does not print an exception traceback containing private values.
        response = error_response(
            request,
            status_code=500,
            code="internal_error",
            message="An unexpected error occurred.",
        )
    response.headers["X-Request-ID"] = str(request_id)
    elapsed_ms = max(0, round((time.perf_counter() - started_at) * 1000))
    _emit_request_event(request, response, elapsed_ms)
    return response
