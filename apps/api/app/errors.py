"""Stable, non-disclosing API error responses."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorBody(BaseModel):
    """Machine-readable error data returned to API clients."""

    code: str
    message: str
    retryable: bool
    request_id: UUID
    details: dict[str, object] | None = None


class ErrorResponse(BaseModel):
    """Top-level envelope shared by API failures."""

    error: ErrorBody


class ApiError(Exception):
    """Expected API failure with explicitly selected public fields."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        retryable: bool = False,
        details: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = dict(details) if details is not None else None
        self.headers = dict(headers) if headers is not None else None


def _request_id(request: Request) -> UUID:
    """Return the request UUID established by request middleware."""

    return request.state.request_id


def error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    retryable: bool = False,
    details: dict[str, object] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Build an error envelope from allowlisted public values."""

    request_id = _request_id(request)
    response_headers = dict(headers) if headers is not None else {}
    response_headers["X-Request-ID"] = str(request_id)
    body = ErrorResponse(
        error=ErrorBody(
            code=code,
            message=message,
            retryable=retryable,
            request_id=request_id,
            details=details,
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json", exclude_none=True),
        headers=response_headers,
    )


def _validation_field(error: dict[str, Any]) -> dict[str, object]:
    """Translate one validation failure without echoing rejected input."""

    error_type = str(error.get("type", ""))
    code, message = {
        "missing": ("required", "This field is required."),
        "string_too_short": ("too_short", "This value is too short."),
        "string_too_long": ("too_long", "This value is too long."),
        "too_short": ("too_few_items", "This collection has too few items."),
        "too_long": ("too_many_items", "This collection has too many items."),
        "literal_error": ("invalid_choice", "Select a supported value."),
        "enum": ("invalid_choice", "Select a supported value."),
    }.get(error_type, ("invalid_format", "This value has an invalid format."))

    return {
        "path": [
            str(part) if not isinstance(part, int) else part for part in error["loc"]
        ],
        "code": code,
        "message": message,
    }


async def handle_api_error(request: Request, error: ApiError) -> JSONResponse:
    """Return an explicitly defined application error."""

    return error_response(
        request,
        status_code=error.status_code,
        code=error.code,
        message=error.message,
        retryable=error.retryable,
        details=error.details,
        headers=error.headers,
    )


async def handle_validation_error(
    request: Request,
    error: RequestValidationError,
) -> JSONResponse:
    """Return safe field failures without rejected values or Pydantic context."""

    return error_response(
        request,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="validation_failed",
        message="The request did not pass validation.",
        details={"fields": [_validation_field(detail) for detail in error.errors()]},
    )


async def handle_http_error(
    request: Request,
    error: StarletteHTTPException,
) -> JSONResponse:
    """Replace framework exception details with stable public fallbacks."""

    code, message, retryable = {
        status.HTTP_400_BAD_REQUEST: (
            "invalid_request",
            "The request could not be understood.",
            False,
        ),
        status.HTTP_401_UNAUTHORIZED: (
            "authentication_required",
            "Authentication is required.",
            False,
        ),
        status.HTTP_403_FORBIDDEN: (
            "operation_forbidden",
            "This operation is not permitted.",
            False,
        ),
        status.HTTP_404_NOT_FOUND: (
            "endpoint_not_found",
            "The requested endpoint was not found.",
            False,
        ),
        status.HTTP_405_METHOD_NOT_ALLOWED: (
            "method_not_allowed",
            "This HTTP method is not supported for the endpoint.",
            False,
        ),
        status.HTTP_429_TOO_MANY_REQUESTS: (
            "rate_limited",
            "Too many requests were received.",
            True,
        ),
        status.HTTP_503_SERVICE_UNAVAILABLE: (
            "service_unavailable",
            "The service is temporarily unavailable.",
            True,
        ),
    }.get(
        error.status_code,
        ("request_rejected", "The request was rejected.", False),
    )
    return error_response(
        request,
        status_code=error.status_code,
        code=code,
        message=message,
        retryable=retryable,
        headers=error.headers,
    )


async def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
    """Return a generic response without serializing the internal exception."""

    return error_response(
        request,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="internal_error",
        message="An unexpected error occurred.",
    )


def register_error_handlers(app: FastAPI) -> None:
    """Install the shared application and framework exception handlers."""

    app.add_exception_handler(ApiError, handle_api_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
