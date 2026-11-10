"""Per-request correlation and allowlisted operational events."""

import json
import time
from uuid import uuid4

from fastapi import Request
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

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


def emit_operational_event(event: dict) -> None:
    """Write an allowlisted event without affecting the operation on sink failure."""
    try:
        print(json.dumps(event, separators=(",", ":")), flush=True)
    except OSError:
        pass


def _emit_request_event(request: Request, status_code: int, elapsed_ms: int) -> None:
    """Write one bounded JSON line without any request or exception values."""

    error_code = getattr(request.state, "error_code", None)
    event: dict[str, str | int] = {
        "event": "http_request_completed",
        "request_id": str(request.state.request_id),
        "method": _method(request),
        "route": _route_template(request),
        "status_code": status_code,
        "duration_ms": elapsed_ms,
        "outcome": _failure_class(status_code, error_code),
    }
    if isinstance(error_code, str):
        event["error_code"] = error_code
    emit_operational_event(event)


def emit_review_outcome(request: Request) -> None:
    """Record a review result only after its request transaction commits."""

    outcome = getattr(request.state, "review_outcome", None)
    item_count = getattr(request.state, "review_item_count", None)
    if outcome not in {"committed", "replayed"} or not isinstance(item_count, int):
        return
    event = {
        "event": "review_submission_completed",
        "request_id": str(request.state.request_id),
        "outcome": outcome,
        "item_count": item_count,
    }
    emit_operational_event(event)


def _emit_completion_events(
    request: Request, status_code: int, elapsed_ms: int
) -> None:
    """Record completion at response headers, excluding body delivery time."""

    request_id = request.state.request_id
    if _route_template(request) == "/v1/decks/{deck_id}/card-drafts/extract":
        try:
            from uuid import UUID

            deck_id = str(UUID(str(request.path_params.get("deck_id"))))
        except ValueError:
            deck_id = None
        event = {
            "event": "card_extraction_completed",
            "request_id": str(request_id),
            "deck_id": deck_id,
            "adjustment": getattr(request.state, "extraction_adjustment", False),
            "duration_ms": elapsed_ms,
            "usage": getattr(request.state, "extraction_usage", None),
            "model_id": getattr(request.state, "extraction_model_id", None),
            "result_code": getattr(request.state, "error_code", "ok"),
        }
        http_status = getattr(request.state, "generation_http_status", None)
        if http_status is not None:
            event["http_status"] = http_status
        emit_operational_event(event)
    _emit_request_event(request, status_code, elapsed_ms)


class RequestContextMiddleware:
    """Correlate requests without buffering or moving response sends to another task."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        request.state.request_id = uuid4()
        started_at = time.perf_counter()
        response_started = False

        async def send_with_context(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                MutableHeaders(scope=message)["X-Request-ID"] = str(
                    request.state.request_id
                )
                elapsed_ms = max(0, round((time.perf_counter() - started_at) * 1000))
                _emit_completion_events(request, message["status"], elapsed_ms)
            await send(message)

        try:
            await self.app(scope, receive, send_with_context)
        except Exception:
            if response_started:
                # Headers already crossed the transport boundary; never start a second response.
                raise
            response = error_response(
                request,
                status_code=500,
                code="internal_error",
                message="An unexpected error occurred.",
            )
            await response(scope, receive, send_with_context)
