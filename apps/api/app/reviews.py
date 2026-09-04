"""Atomic, idempotent, and owner-scoped review submissions."""

import hashlib
import json
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Depends, Header, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.auth import CurrentUserDependency
from app.database import database_session
from app.errors import ApiError

router = APIRouter(prefix="/v1")
SessionDependency = Annotated[Session, Depends(database_session)]
Decision = Literal["no", "no_a_bit", "yes_a_bit", "yes"]
ALGORITHM_VERSION = "srs-v1"
TAIPEI = ZoneInfo("Asia/Taipei")
STAGE_INTERVALS = (0, 1, 3, 7, 14, 30)
DECISION_QUALITY: dict[str, int] = {
    "no": 0,
    "no_a_bit": 2,
    "yes_a_bit": 3,
    "yes": 5,
}


class ReviewWriteModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReviewSubmissionItem(ReviewWriteModel):
    card_id: UUID
    decision: Decision
    expected_version: Annotated[int, Field(ge=1)]


class ReviewSubmission(ReviewWriteModel):
    items: Annotated[list[ReviewSubmissionItem], Field(min_length=1, max_length=10)]

    @model_validator(mode="after")
    def require_unique_cards(self) -> "ReviewSubmission":
        card_ids = [item.card_id for item in self.items]
        if len(card_ids) != len(set(card_ids)):
            raise ValueError("card IDs must be unique")
        return self


class TransitionState(BaseModel):
    review_stage: int
    ease_factor: Decimal
    interval_days: int
    last_reviewed_at: datetime | None
    next_review_at: datetime
    version: int


class ReviewResultItem(BaseModel):
    event_id: int
    card_id: UUID
    decision: Decision
    quality: int
    previous_state: TransitionState
    resulting_state: TransitionState


class ReviewResult(BaseModel):
    batch_id: UUID
    reviewed_at: datetime
    algorithm_version: str
    items: list[ReviewResultItem]


def review_clock() -> datetime:
    """Return the backend-authoritative review instant."""

    return datetime.now(UTC)


def after_events_written(_session: Session) -> None:
    """No-op fault-injection seam used to verify transaction rollback."""


def before_batch_insert() -> None:
    """No-op synchronization seam used by deterministic concurrency tests."""


def _idempotency_key(raw_value: str | None) -> UUID:
    if raw_value is None:
        raise _invalid_idempotency_key()
    try:
        return UUID(raw_value)
    except (ValueError, AttributeError):
        raise _invalid_idempotency_key() from None


def _invalid_idempotency_key() -> ApiError:
    return ApiError(
        status_code=400,
        code="invalid_idempotency_key",
        message="A valid Idempotency-Key header is required.",
    )


def _request_hash(payload: ReviewSubmission) -> str:
    normalized = {
        "items": [
            {
                "card_id": str(item.card_id),
                "decision": item.decision,
                "expected_version": item.expected_version,
            }
            for item in payload.items
        ]
    }
    canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"


def _new_ease_factor(quality: int, current: Decimal) -> Decimal:
    missing = Decimal(5 - quality)
    updated = (
        current
        + Decimal("0.1")
        - missing * (Decimal("0.08") + missing * Decimal("0.02"))
    )
    return min(Decimal("2.50"), max(Decimal("1.30"), updated)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def _transition(
    row: object, decision: Decision, reviewed_at: datetime
) -> dict[str, object]:
    quality = DECISION_QUALITY[decision]
    stage_delta = 1 if quality >= 3 else -1
    resulting_stage = min(5, max(1, row.review_stage + stage_delta))
    resulting_ease = _new_ease_factor(quality, row.ease_factor)
    interval = int(
        (Decimal(STAGE_INTERVALS[resulting_stage]) * resulting_ease).quantize(
            Decimal(1), rounding=ROUND_HALF_UP
        )
    )
    due_date: date = reviewed_at.astimezone(TAIPEI).date() + timedelta(days=interval)
    next_review_at = datetime.combine(due_date, time.min, tzinfo=TAIPEI).astimezone(UTC)
    return {
        "quality": quality,
        "resulting_review_stage": resulting_stage,
        "resulting_ease_factor": resulting_ease,
        "resulting_interval_days": interval,
        "resulting_last_reviewed_at": reviewed_at,
        "resulting_next_review_at": next_review_at,
        "resulting_version": row.version + 1,
    }


def _state(
    *,
    review_stage: int,
    ease_factor: Decimal,
    interval_days: int,
    last_reviewed_at: datetime | None,
    next_review_at: datetime,
    version: int,
) -> TransitionState:
    return TransitionState(
        review_stage=review_stage,
        ease_factor=ease_factor,
        interval_days=interval_days,
        last_reviewed_at=last_reviewed_at,
        next_review_at=next_review_at,
        version=version,
    )


def _replay_result(session: Session, batch: object) -> ReviewResult:
    rows = (
        session.execute(
            text(
                """
                SELECT *
                FROM review_events
                WHERE batch_id = :batch_id AND owner_id = :owner_id
                ORDER BY id ASC
                """
            ),
            {"batch_id": batch.id, "owner_id": batch.owner_id},
        )
        .mappings()
        .all()
    )
    items = [
        ReviewResultItem(
            event_id=row.id,
            card_id=row.card_id,
            decision=row.decision,
            quality=row.quality,
            previous_state=_state(
                review_stage=row.previous_review_stage,
                ease_factor=row.previous_ease_factor,
                interval_days=row.previous_interval_days,
                last_reviewed_at=row.previous_last_reviewed_at,
                next_review_at=row.previous_next_review_at,
                version=row.previous_version,
            ),
            resulting_state=_state(
                review_stage=row.resulting_review_stage,
                ease_factor=row.resulting_ease_factor,
                interval_days=row.resulting_interval_days,
                last_reviewed_at=row.resulting_last_reviewed_at,
                next_review_at=row.resulting_next_review_at,
                version=row.resulting_version,
            ),
        )
        for row in rows
    ]
    return ReviewResult(
        batch_id=batch.id,
        reviewed_at=batch.reviewed_at,
        algorithm_version=batch.algorithm_version,
        items=items,
    )


def _item_context(payload: ReviewSubmission, card_id: UUID) -> dict[str, object]:
    index = next(
        index for index, item in enumerate(payload.items) if item.card_id == card_id
    )
    return {"item_index": index, "card_id": str(card_id)}


@router.post("/reviews", response_model=ReviewResult)
def submit_reviews(
    request: Request,
    payload: Annotated[ReviewSubmission, Body()],
    session: SessionDependency,
    user: CurrentUserDependency,
    raw_idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ReviewResult:
    """Commit one bounded review batch or replay its original result."""

    if request.query_params:
        raise ApiError(
            status_code=400,
            code="unsupported_filter",
            message="The request contains an unsupported query filter.",
            details={"filters": sorted(set(request.query_params))},
        )
    idempotency_key = _idempotency_key(raw_idempotency_key)
    request_hash = _request_hash(payload)
    reviewed_at = review_clock()
    before_batch_insert()
    batch = (
        session.execute(
            text(
                """
                INSERT INTO review_batches (
                    owner_id, idempotency_key, request_hash, reviewed_at,
                    algorithm_version, item_count
                ) VALUES (
                    :owner_id, :idempotency_key, :request_hash, :reviewed_at,
                    :algorithm_version, :item_count
                )
                ON CONFLICT (owner_id, idempotency_key) DO NOTHING
                RETURNING id, owner_id, request_hash, reviewed_at, algorithm_version
                """
            ),
            {
                "owner_id": user.id,
                "idempotency_key": idempotency_key,
                "request_hash": request_hash,
                "reviewed_at": reviewed_at,
                "algorithm_version": ALGORITHM_VERSION,
                "item_count": len(payload.items),
            },
        )
        .mappings()
        .one_or_none()
    )
    if batch is None:
        batch = (
            session.execute(
                text(
                    """
                    SELECT id, owner_id, request_hash, reviewed_at, algorithm_version
                    FROM review_batches
                    WHERE owner_id = :owner_id AND idempotency_key = :idempotency_key
                    """
                ),
                {"owner_id": user.id, "idempotency_key": idempotency_key},
            )
            .mappings()
            .one()
        )
        if batch.request_hash != request_hash:
            raise ApiError(
                status_code=409,
                code="idempotency_key_reused",
                message="The idempotency key was already used for different content.",
            )
        return _replay_result(session, batch)

    card_ids = sorted(item.card_id for item in payload.items)
    rows = (
        session.execute(
            text(
                """
                SELECT
                    c.id AS card_id, c.archived_at AS card_archived_at,
                    d.archived_at AS deck_archived_at,
                    s.review_stage, s.ease_factor, s.interval_days,
                    s.last_reviewed_at, s.next_review_at, s.version
                FROM learning_cards AS c
                JOIN learning_decks AS d
                  ON (d.id, d.owner_id) = (c.deck_id, c.owner_id)
                JOIN review_states AS s
                  ON (s.card_id, s.owner_id) = (c.id, c.owner_id)
                WHERE c.owner_id = :owner_id AND c.id IN :card_ids
                ORDER BY c.id ASC
                FOR UPDATE OF c, d, s
                """
            ).bindparams(bindparam("card_ids", expanding=True)),
            {"owner_id": user.id, "card_ids": card_ids},
        )
        .mappings()
        .all()
    )
    if len(rows) != len(card_ids):
        raise ApiError(
            status_code=404,
            code="card_not_found",
            message="The requested card was not found.",
        )

    rows_by_id = {row.card_id: row for row in rows}
    for item in payload.items:
        row = rows_by_id[item.card_id]
        context = _item_context(payload, item.card_id)
        if row.card_archived_at is not None or row.deck_archived_at is not None:
            raise ApiError(
                status_code=409,
                code="review_target_inactive",
                message="A review target is inactive.",
                details=context,
            )
        if row.version != item.expected_version:
            raise ApiError(
                status_code=409,
                code="stale_review_state",
                message="A review state changed since it was read.",
                details={
                    **context,
                    "expected_version": item.expected_version,
                    "current_version": row.version,
                },
            )
        if row.last_reviewed_at is not None and reviewed_at < row.last_reviewed_at:
            raise ApiError(
                status_code=409,
                code="review_time_conflict",
                message="The review time precedes the current state.",
                details=context,
            )

    results: list[ReviewResultItem] = []
    for item in payload.items:
        row = rows_by_id[item.card_id]
        transition = _transition(row, item.decision, reviewed_at)
        event_id = session.execute(
            text(
                """
                INSERT INTO review_events (
                    batch_id, owner_id, card_id, decision, quality,
                    previous_review_stage, resulting_review_stage,
                    previous_ease_factor, resulting_ease_factor,
                    previous_interval_days, resulting_interval_days,
                    previous_last_reviewed_at, resulting_last_reviewed_at,
                    previous_next_review_at, resulting_next_review_at,
                    previous_version, resulting_version,
                    algorithm_version, reviewed_at
                ) VALUES (
                    :batch_id, :owner_id, :card_id, :decision, :quality,
                    :previous_review_stage, :resulting_review_stage,
                    :previous_ease_factor, :resulting_ease_factor,
                    :previous_interval_days, :resulting_interval_days,
                    :previous_last_reviewed_at, :resulting_last_reviewed_at,
                    :previous_next_review_at, :resulting_next_review_at,
                    :previous_version, :resulting_version,
                    :algorithm_version, :reviewed_at
                )
                RETURNING id
                """
            ),
            {
                "batch_id": batch.id,
                "owner_id": user.id,
                "card_id": item.card_id,
                "decision": item.decision,
                "previous_review_stage": row.review_stage,
                "previous_ease_factor": row.ease_factor,
                "previous_interval_days": row.interval_days,
                "previous_last_reviewed_at": row.last_reviewed_at,
                "previous_next_review_at": row.next_review_at,
                "previous_version": row.version,
                "algorithm_version": ALGORITHM_VERSION,
                "reviewed_at": reviewed_at,
                **transition,
            },
        ).scalar_one()
        results.append(
            ReviewResultItem(
                event_id=event_id,
                card_id=item.card_id,
                decision=item.decision,
                quality=transition["quality"],
                previous_state=_state(
                    review_stage=row.review_stage,
                    ease_factor=row.ease_factor,
                    interval_days=row.interval_days,
                    last_reviewed_at=row.last_reviewed_at,
                    next_review_at=row.next_review_at,
                    version=row.version,
                ),
                resulting_state=_state(
                    review_stage=transition["resulting_review_stage"],
                    ease_factor=transition["resulting_ease_factor"],
                    interval_days=transition["resulting_interval_days"],
                    last_reviewed_at=transition["resulting_last_reviewed_at"],
                    next_review_at=transition["resulting_next_review_at"],
                    version=transition["resulting_version"],
                ),
            )
        )

    after_events_written(session)
    for result in results:
        updated = session.execute(
            text(
                """
                UPDATE review_states
                SET review_stage = :review_stage,
                    ease_factor = :ease_factor,
                    interval_days = :interval_days,
                    last_reviewed_at = :last_reviewed_at,
                    next_review_at = :next_review_at,
                    version = :resulting_version,
                    updated_at = CURRENT_TIMESTAMP
                WHERE card_id = :card_id
                  AND owner_id = :owner_id
                  AND version = :previous_version
                """
            ),
            {
                "card_id": result.card_id,
                "owner_id": user.id,
                "review_stage": result.resulting_state.review_stage,
                "ease_factor": result.resulting_state.ease_factor,
                "interval_days": result.resulting_state.interval_days,
                "last_reviewed_at": result.resulting_state.last_reviewed_at,
                "next_review_at": result.resulting_state.next_review_at,
                "previous_version": result.previous_state.version,
                "resulting_version": result.resulting_state.version,
            },
        )
        if updated.rowcount != 1:
            raise RuntimeError("locked review state changed unexpectedly")

    return ReviewResult(
        batch_id=batch.id,
        reviewed_at=reviewed_at,
        algorithm_version=ALGORITHM_VERSION,
        items=results,
    )
