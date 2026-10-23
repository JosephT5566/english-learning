"""Machine-authenticated, bounded and read-only static publication export."""

import threading
from datetime import UTC, datetime
from typing import Annotated, Literal

import anyio
from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token as google_id_token
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database import database_transaction
from app.errors import ApiError, ErrorResponse
from app.public_content import PUBLIC_CARD_PROJECTION, PublicReviewCard

EXPORT_PATH = "/v1/internal/guest-cards/export"
MAX_SNAPSHOT_BYTES = 512 * 1024
router = APIRouter()
bearer = HTTPBearer(auto_error=False)
EXPORT_QUERY = text(
    PUBLIC_CARD_PROJECTION
    + """
    WHERE d.id = :deck_id AND d.target_language = 'en'
      AND d.archived_at IS NULL AND c.archived_at IS NULL
    ORDER BY random(), c.id
    LIMIT 50
"""
)


class GuestSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    generated_at: AwareDatetime
    items: list[PublicReviewCard] = Field(max_length=50)

    @field_validator("items")
    @classmethod
    def english_unique_cards(
        cls, items: list[PublicReviewCard]
    ) -> list[PublicReviewCard]:
        if any(card.target_language != "en" for card in items) or len(
            {card.id for card in items}
        ) != len(items):
            raise ValueError("export requires distinct English cards")
        return items


class _BoundedGoogleRequest(GoogleAuthRequest):
    def __call__(self, *args, **kwargs):
        kwargs["timeout"] = 5
        return super().__call__(*args, **kwargs)


def export_identity(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    settings = request.app.state.settings
    if settings.guest_export_deck_id is None:
        raise ApiError(
            status_code=503, code="export_disabled", message="Export is not configured."
        )
    invalid = ApiError(
        status_code=401,
        code="invalid_authentication",
        message="Export authentication is required.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise invalid
    try:
        claims = google_id_token.verify_oauth2_token(
            credentials.credentials,
            _BoundedGoogleRequest(),
            settings.guest_export_audience,
        )
    except ValueError:
        raise invalid from None
    except GoogleAuthError:
        raise ApiError(
            status_code=503,
            code="identity_provider_unavailable",
            message="Authentication is temporarily unavailable.",
            retryable=True,
        ) from None
    if (
        claims.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}
        or claims.get("aud") != settings.guest_export_audience
        or claims.get("sub") != settings.guest_export_subject
        or claims.get("email") != settings.guest_export_email
        or claims.get("email_verified") is not True
    ):
        raise invalid


def _read_export(request: Request) -> GuestSnapshot:
    settings = request.app.state.settings
    try:
        with database_transaction(
            request.app.state.database_session_factory
        ) as session:
            session.execute(text("SET TRANSACTION READ ONLY"))
            session.execute(
                text("SELECT set_config('statement_timeout', :timeout, true)"),
                {"timeout": str(settings.guest_export_query_timeout_ms)},
            )
            deck = (
                session.execute(
                    text(
                        "SELECT target_language, archived_at FROM learning_decks WHERE id = :id"
                    ),
                    {"id": settings.guest_export_deck_id},
                )
                .mappings()
                .one_or_none()
            )
            if deck is None or deck["target_language"] != "en":
                raise ApiError(
                    status_code=422,
                    code="invalid_export_deck",
                    message="The configured export deck must exist and be English.",
                )
            rows = (
                []
                if deck["archived_at"] is not None
                else session.execute(
                    EXPORT_QUERY, {"deck_id": settings.guest_export_deck_id}
                ).mappings()
            )
            snapshot = GuestSnapshot(
                schema_version=1,
                generated_at=datetime.now(UTC),
                items=[PublicReviewCard.model_validate(row) for row in rows],
            )
            if len(snapshot.model_dump_json().encode("utf-8")) > MAX_SNAPSHOT_BYTES:
                raise ApiError(
                    status_code=422,
                    code="export_too_large",
                    message="The export exceeds the publication size limit.",
                )
            return snapshot
    except SQLAlchemyError:
        raise ApiError(
            status_code=503,
            code="database_unavailable",
            message="The database is temporarily unavailable.",
            retryable=True,
        ) from None


@router.get(
    EXPORT_PATH,
    response_model=GuestSnapshot,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def export_guest_cards(
    request: Request,
    response: Response,
    _identity: Annotated[None, Depends(export_identity)],
) -> GuestSnapshot:
    response.headers["Cache-Control"] = "no-store"
    if request.query_params:
        raise ApiError(
            status_code=400,
            code="unsupported_filter",
            message="Export does not accept filters.",
        )
    permit: threading.BoundedSemaphore = request.app.state.guest_export_permit
    if not permit.acquire(blocking=False):
        raise ApiError(
            status_code=503,
            code="export_busy",
            message="An export is already in progress.",
            retryable=True,
            headers={"Retry-After": "1"},
        )
    try:
        with anyio.CancelScope(shield=True):
            return await anyio.to_thread.run_sync(
                _read_export, request, abandon_on_cancel=False
            )
    finally:
        permit.release()
