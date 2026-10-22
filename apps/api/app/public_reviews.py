"""Anonymous, explicitly projected, transactionally read-only card batches."""

from typing import Annotated
from uuid import UUID

import anyio
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import Uuid, bindparam, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.database import database_transaction
from app.errors import ApiError, ErrorResponse
from app.public_admission import AdmissionRejection
from app.reads import TargetLanguage

PUBLIC_REVIEW_PATH = "/v1/public/review-cards"
router = APIRouter()


class PublicReviewCard(BaseModel):
    id: UUID
    target_language: TargetLanguage
    term: str
    meaning: str
    pronunciation: str | None
    reading: str | None
    romanization: str | None
    part_of_speech: str | None
    part_of_speech_detail: str | None
    target_language_definition: str | None
    example_sentence: str | None
    example_translation: str | None
    synonyms: list[str]
    antonyms: list[str]


class PublicReviewCards(BaseModel):
    items: list[PublicReviewCard]


PUBLIC_CARDS_QUERY = text("""
    SELECT c.id, d.target_language, c.term, c.meaning,
           c.pronunciation, c.reading, c.romanization,
           c.part_of_speech, c.part_of_speech_detail,
           c.target_language_definition, c.example_sentence, c.example_translation,
           c.synonyms, c.antonyms
    FROM learning_cards AS c
    JOIN learning_decks AS d ON d.id = c.deck_id AND d.owner_id = c.owner_id
    WHERE d.id IN :deck_ids
      AND d.archived_at IS NULL AND c.archived_at IS NULL
    ORDER BY random(), c.id
    LIMIT 10
""").bindparams(bindparam("deck_ids", expanding=True, type_=Uuid))


def _read_batch(request: Request) -> PublicReviewCards:
    settings = request.app.state.settings
    try:
        with database_transaction(
            request.app.state.database_session_factory
        ) as session:
            session.execute(text("SET TRANSACTION READ ONLY"))
            session.execute(
                text("SELECT set_config('statement_timeout', :timeout, true)"),
                {"timeout": str(settings.public_review_query_timeout_ms)},
            )
            rows = session.execute(
                PUBLIC_CARDS_QUERY, {"deck_ids": settings.public_review_deck_ids}
            ).mappings()
            return PublicReviewCards(
                items=[PublicReviewCard.model_validate(row) for row in rows]
            )
    except IntegrityError:
        raise ApiError(
            status_code=422,
            code="validation_failed",
            message="The request did not pass validation.",
        ) from None
    except SQLAlchemyError:
        raise ApiError(
            status_code=503,
            code="database_unavailable",
            message="The database is temporarily unavailable.",
            retryable=True,
        ) from None


async def public_batch(request: Request) -> PublicReviewCards:
    if request.query_params:
        raise ApiError(
            status_code=400,
            code="unsupported_filter",
            message="The request contains an unsupported query filter.",
        )
    admission = request.app.state.public_admission
    peer = request.client.host if request.client else None
    permit = admission.try_acquire(admission.client_key(peer))
    if isinstance(permit, AdmissionRejection):
        rate_limited = permit.reason == "rate_limited"
        raise ApiError(
            status_code=429 if rate_limited else 503,
            code="rate_limited" if rate_limited else "public_review_busy",
            message=(
                "Please wait before requesting another batch."
                if rate_limited
                else "Public review is temporarily busy."
            ),
            retryable=True,
            headers={"Retry-After": str(permit.retry_after_seconds)},
        )
    try:
        # Cancellation cannot abandon a synchronous query or release its permit early.
        with anyio.CancelScope(shield=True):
            return await anyio.to_thread.run_sync(
                _read_batch, request, abandon_on_cancel=False
            )
    finally:
        permit.release()


@router.get(
    PUBLIC_REVIEW_PATH,
    response_model=PublicReviewCards,
    responses={
        400: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def get_public_review_cards(
    batch: Annotated[PublicReviewCards, Depends(public_batch)],
) -> PublicReviewCards:
    return batch
