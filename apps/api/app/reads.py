"""Owner-scoped multilingual deck, card, and due-review read APIs."""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import bindparam, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.pagination import (
    cursor_datetime,
    decode_cursor,
    encode_cursor,
    parse_cursor_datetime,
    parse_cursor_uuid,
    query_fingerprint,
)

router = APIRouter(prefix="/v1")

# Authentication is Issue #10. Keeping the temporary owner at one named composition
# boundary prevents clients from choosing it and keeps every SQL query owner-scoped.
TEMPORARY_TEST_OWNER_ID = 1
MANAGEMENT_LIMIT = Annotated[int, Query(ge=1, le=100)]
DUE_LIMIT = Annotated[int, Query(ge=1, le=10)]
TargetLanguage = Literal["en", "ja"]
ArchiveStatus = Literal["active", "archived", "all"]


class Page[Item: BaseModel](BaseModel):
    """Shared successful collection envelope."""

    items: list[Item]
    next_cursor: str | None


class Deck(BaseModel):
    id: UUID
    title: str
    target_language: TargetLanguage
    explanation_language: Literal["en", "ja", "zh-TW"]
    archived_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class DeckSummary(BaseModel):
    id: UUID
    title: str
    target_language: TargetLanguage
    explanation_language: Literal["en", "ja", "zh-TW"]
    archived_at: datetime | None


class TagSummary(BaseModel):
    id: UUID
    display_name: str


class ReviewState(BaseModel):
    review_stage: int
    ease_factor: Decimal
    interval_days: int
    last_reviewed_at: datetime | None
    next_review_at: datetime
    version: int


class CardSummary(BaseModel):
    id: UUID
    deck: DeckSummary
    term: str
    meaning: str
    reading: str | None
    pronunciation: str | None
    romanization: str | None
    part_of_speech: str | None
    archived_at: datetime | None
    version: int
    updated_at: datetime


class CardDetail(CardSummary):
    target_language_definition: str | None
    example_sentence: str | None
    example_translation: str | None
    example_source: str | None
    synonyms: list[str]
    antonyms: list[str]
    part_of_speech_detail: str | None
    note: str | None
    supplementary_note: str | None
    learned_on: date | None
    created_at: datetime
    tags: list[TagSummary]
    review_state: ReviewState | None


class DueCard(CardDetail):
    """A complete review-ready card; review_state is always populated."""

    review_state: ReviewState


def current_owner_id() -> int:
    """Return the explicit temporary owner until server authentication lands."""

    return TEMPORARY_TEST_OWNER_ID


def database_session(request: Request) -> Iterator[Session]:
    """Yield one read session and translate database errors at the API boundary."""

    session = request.app.state.database_session_factory()
    try:
        yield session
    except SQLAlchemyError:
        raise ApiError(
            status_code=503,
            code="database_unavailable",
            message="The database is temporarily unavailable.",
            retryable=True,
        ) from None
    finally:
        session.close()


SessionDependency = Annotated[Session, Depends(database_session)]
OwnerDependency = Annotated[int, Depends(current_owner_id)]


def _reject_unknown_filters(request: Request, allowed: set[str]) -> None:
    unknown = sorted(set(request.query_params) - allowed)
    if unknown:
        raise ApiError(
            status_code=400,
            code="unsupported_filter",
            message="The request contains an unsupported query filter.",
            details={"filters": unknown},
        )


def _not_found(resource: str) -> ApiError:
    return ApiError(
        status_code=404,
        code=f"{resource}_not_found",
        message=f"The requested {resource} was not found.",
    )


def _archive_clause(status: ArchiveStatus, alias: str) -> str:
    return {
        "active": f"{alias}.archived_at IS NULL",
        "archived": f"{alias}.archived_at IS NOT NULL",
        "all": "TRUE",
    }[status]


def _validate_owned_resource(
    session: Session,
    *,
    table: str,
    resource_id: UUID,
    owner_id: int,
    resource: str,
) -> None:
    found = session.execute(
        text(f"SELECT 1 FROM {table} WHERE id = :id AND owner_id = :owner_id"),
        {"id": resource_id, "owner_id": owner_id},
    ).scalar_one_or_none()
    if found is None:
        raise _not_found(resource)


DECK_COLUMNS = """
    d.id, d.title, d.target_language, d.explanation_language,
    d.archived_at, d.version, d.created_at, d.updated_at
"""


@router.get("/decks", response_model=Page[Deck])
def list_decks(
    request: Request,
    session: SessionDependency,
    owner_id: OwnerDependency,
    target_language: Annotated[TargetLanguage | None, Query()] = None,
    status: Annotated[ArchiveStatus, Query()] = "active",
    limit: MANAGEMENT_LIMIT = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> Page[Deck]:
    """List owned decks in stable most-recently-updated order."""

    _reject_unknown_filters(request, {"target_language", "status", "limit", "cursor"})
    filters = {"target_language": target_language, "status": status}
    fingerprint = query_fingerprint(filters, limit)
    cursor_updated_at = cursor_id = None
    if cursor is not None:
        position, _ = decode_cursor(
            cursor,
            kind="decks",
            fingerprint=fingerprint,
            position_fields={"updated_at", "id"},
        )
        cursor_updated_at = parse_cursor_datetime(position["updated_at"])
        cursor_id = parse_cursor_uuid(position["id"])

    conditions = ["d.owner_id = :owner_id", _archive_clause(status, "d")]
    if target_language is not None:
        conditions.append("d.target_language = :target_language")
    if cursor_updated_at is not None:
        conditions.append("(d.updated_at, d.id) < (:cursor_updated_at, :cursor_id)")
    rows = (
        session.execute(
            text(
                f"""
            SELECT {DECK_COLUMNS}
            FROM learning_decks AS d
            WHERE {" AND ".join(conditions)}
            ORDER BY d.updated_at DESC, d.id DESC
            LIMIT :fetch_limit
            """
            ),
            {
                "owner_id": owner_id,
                "target_language": target_language,
                "cursor_updated_at": cursor_updated_at,
                "cursor_id": cursor_id,
                "fetch_limit": limit + 1,
            },
        )
        .mappings()
        .all()
    )
    return _page(rows, limit, Deck, "decks", fingerprint, "updated_at")


@router.get("/decks/{deck_id}", response_model=Deck)
def get_deck(
    deck_id: UUID,
    request: Request,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> Deck:
    """Return one owned deck without disclosing cross-owner existence."""

    _reject_unknown_filters(request, set())
    row = (
        session.execute(
            text(
                f"SELECT {DECK_COLUMNS} FROM learning_decks AS d WHERE d.id = :id AND d.owner_id = :owner_id"
            ),
            {"id": deck_id, "owner_id": owner_id},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise _not_found("deck")
    return Deck.model_validate(row)


CARD_COLUMNS = """
    c.id,
    jsonb_build_object(
        'id', d.id, 'title', d.title, 'target_language', d.target_language,
        'explanation_language', d.explanation_language, 'archived_at', d.archived_at
    ) AS deck,
    c.term, c.meaning, c.reading, c.pronunciation, c.romanization,
    c.part_of_speech, c.archived_at, c.version, c.updated_at
"""

CARD_DETAIL_COLUMNS = (
    CARD_COLUMNS
    + """,
    c.target_language_definition, c.example_sentence, c.example_translation,
    c.example_source, c.synonyms, c.antonyms, c.part_of_speech_detail,
    c.note, c.supplementary_note, c.learned_on, c.created_at,
    COALESCE(
        (SELECT jsonb_agg(
            jsonb_build_object('id', t.id, 'display_name', t.display_name)
            ORDER BY lower(t.display_name), t.id
        )
        FROM learning_card_tags AS ct
        JOIN tags AS t ON (t.id, t.owner_id) = (ct.tag_id, ct.owner_id)
        WHERE ct.card_id = c.id AND ct.owner_id = c.owner_id),
        '[]'::jsonb
    ) AS tags,
    CASE WHEN s.card_id IS NULL THEN NULL ELSE jsonb_build_object(
        'review_stage', s.review_stage, 'ease_factor', s.ease_factor,
        'interval_days', s.interval_days, 'last_reviewed_at', s.last_reviewed_at,
        'next_review_at', s.next_review_at, 'version', s.version
    ) END AS review_state
"""
)


@router.get("/cards", response_model=Page[CardSummary])
def list_cards(
    request: Request,
    session: SessionDependency,
    owner_id: OwnerDependency,
    deck_id: Annotated[UUID | None, Query()] = None,
    target_language: Annotated[TargetLanguage | None, Query()] = None,
    status: Annotated[ArchiveStatus, Query()] = "active",
    tag_id: Annotated[UUID | None, Query()] = None,
    limit: MANAGEMENT_LIMIT = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> Page[CardSummary]:
    """List compact owned card summaries with language and tag filtering."""

    _reject_unknown_filters(
        request,
        {"deck_id", "target_language", "status", "tag_id", "limit", "cursor"},
    )
    if deck_id is not None:
        _validate_owned_resource(
            session,
            table="learning_decks",
            resource_id=deck_id,
            owner_id=owner_id,
            resource="deck",
        )
    if tag_id is not None:
        _validate_owned_resource(
            session,
            table="tags",
            resource_id=tag_id,
            owner_id=owner_id,
            resource="tag",
        )
    filters = {
        "deck_id": str(deck_id) if deck_id else None,
        "target_language": target_language,
        "status": status,
        "tag_id": str(tag_id) if tag_id else None,
    }
    fingerprint = query_fingerprint(filters, limit)
    cursor_updated_at = cursor_id = None
    if cursor is not None:
        position, _ = decode_cursor(
            cursor,
            kind="cards",
            fingerprint=fingerprint,
            position_fields={"updated_at", "id"},
        )
        cursor_updated_at = parse_cursor_datetime(position["updated_at"])
        cursor_id = parse_cursor_uuid(position["id"])

    conditions = ["c.owner_id = :owner_id", _archive_clause(status, "c")]
    if deck_id is not None:
        conditions.append("c.deck_id = :deck_id")
    if target_language is not None:
        conditions.append("d.target_language = :target_language")
    if tag_id is not None:
        conditions.append(
            "EXISTS (SELECT 1 FROM learning_card_tags AS filter_ct "
            "WHERE filter_ct.card_id = c.id AND filter_ct.owner_id = c.owner_id "
            "AND filter_ct.tag_id = :tag_id)"
        )
    if cursor_updated_at is not None:
        conditions.append("(c.updated_at, c.id) < (:cursor_updated_at, :cursor_id)")
    rows = (
        session.execute(
            text(
                f"""
            SELECT {CARD_COLUMNS}
            FROM learning_cards AS c
            JOIN learning_decks AS d
              ON (d.id, d.owner_id) = (c.deck_id, c.owner_id)
            WHERE {" AND ".join(conditions)}
            ORDER BY c.updated_at DESC, c.id DESC
            LIMIT :fetch_limit
            """
            ),
            {
                "owner_id": owner_id,
                "deck_id": deck_id,
                "target_language": target_language,
                "tag_id": tag_id,
                "cursor_updated_at": cursor_updated_at,
                "cursor_id": cursor_id,
                "fetch_limit": limit + 1,
            },
        )
        .mappings()
        .all()
    )
    return _page(rows, limit, CardSummary, "cards", fingerprint, "updated_at")


@router.get("/cards/{card_id}", response_model=CardDetail)
def get_card(
    card_id: UUID,
    request: Request,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> CardDetail:
    """Return complete multilingual content for one owned card."""

    _reject_unknown_filters(request, set())
    row = (
        session.execute(
            text(
                f"""
            SELECT {CARD_DETAIL_COLUMNS}
            FROM learning_cards AS c
            JOIN learning_decks AS d
              ON (d.id, d.owner_id) = (c.deck_id, c.owner_id)
            LEFT JOIN review_states AS s
              ON (s.card_id, s.owner_id) = (c.id, c.owner_id)
            WHERE c.id = :id AND c.owner_id = :owner_id
            """
            ),
            {"id": card_id, "owner_id": owner_id},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise _not_found("card")
    return CardDetail.model_validate(row)


@router.get("/reviews/due", response_model=Page[DueCard])
def list_due_reviews(
    request: Request,
    session: SessionDependency,
    owner_id: OwnerDependency,
    target_language: Annotated[TargetLanguage, Query()],
    deck_id: Annotated[list[UUID] | None, Query()] = None,
    limit: DUE_LIMIT = 10,
    cursor: Annotated[str | None, Query()] = None,
) -> Page[DueCard]:
    """Return active due cards using one server-time snapshot across pages."""

    _reject_unknown_filters(request, {"target_language", "deck_id", "limit", "cursor"})
    deck_ids = deck_id or []
    if len(deck_ids) > 20:
        raise _validation_error("deck_id", "too_many_items", "Select at most 20 decks.")
    if len(set(deck_ids)) != len(deck_ids):
        raise _validation_error("deck_id", "duplicate", "Deck IDs must be unique.")
    if deck_ids:
        rows = (
            session.execute(
                text(
                    """
                SELECT id, target_language, archived_at
                FROM learning_decks
                WHERE owner_id = :owner_id AND id IN :deck_ids
                """
                ).bindparams(bindparam("deck_ids", expanding=True)),
                {"owner_id": owner_id, "deck_ids": deck_ids},
            )
            .mappings()
            .all()
        )
        if len(rows) != len(deck_ids):
            raise _not_found("deck")
        if any(row.target_language != target_language for row in rows):
            raise _validation_error(
                "deck_id",
                "invalid_choice",
                "Every deck must match the target language.",
            )
        if any(row.archived_at is not None for row in rows):
            raise ApiError(
                status_code=409,
                code="review_scope_inactive",
                message="A selected review deck is archived.",
            )

    normalized_decks = sorted(str(value) for value in deck_ids)
    filters = {"target_language": target_language, "deck_ids": normalized_decks}
    fingerprint = query_fingerprint(filters, limit)
    cursor_due_at = cursor_id = None
    if cursor is None:
        as_of = datetime.now(UTC)
    else:
        position, snapshot = decode_cursor(
            cursor,
            kind="due_reviews",
            fingerprint=fingerprint,
            position_fields={"next_review_at", "id"},
            snapshot_fields={"as_of"},
        )
        cursor_due_at = parse_cursor_datetime(position["next_review_at"])
        cursor_id = parse_cursor_uuid(position["id"])
        assert snapshot is not None
        as_of = parse_cursor_datetime(snapshot["as_of"])

    conditions = [
        "s.owner_id = :owner_id",
        "s.next_review_at <= :as_of",
        "c.archived_at IS NULL",
        "d.archived_at IS NULL",
        "d.target_language = :target_language",
    ]
    statement = f"""
        SELECT {CARD_DETAIL_COLUMNS}, s.next_review_at AS next_review_at
        FROM review_states AS s
        JOIN learning_cards AS c
          ON (c.id, c.owner_id) = (s.card_id, s.owner_id)
        JOIN learning_decks AS d
          ON (d.id, d.owner_id) = (c.deck_id, c.owner_id)
        WHERE {{conditions}}
        ORDER BY s.next_review_at ASC, c.id ASC
        LIMIT :fetch_limit
    """
    if deck_ids:
        conditions.append("c.deck_id IN :deck_ids")
    if cursor_due_at is not None:
        conditions.append("(s.next_review_at, c.id) > (:cursor_due_at, :cursor_id)")
    query = text(statement.format(conditions=" AND ".join(conditions)))
    if deck_ids:
        query = query.bindparams(bindparam("deck_ids", expanding=True))
    rows = (
        session.execute(
            query,
            {
                "owner_id": owner_id,
                "target_language": target_language,
                "as_of": as_of,
                "deck_ids": deck_ids,
                "cursor_due_at": cursor_due_at,
                "cursor_id": cursor_id,
                "fetch_limit": limit + 1,
            },
        )
        .mappings()
        .all()
    )
    return _page(
        rows,
        limit,
        DueCard,
        "due_reviews",
        fingerprint,
        "next_review_at",
        snapshot={"as_of": cursor_datetime(as_of)},
    )


def _validation_error(field: str, code: str, message: str) -> ApiError:
    return ApiError(
        status_code=422,
        code="validation_failed",
        message="The request did not pass validation.",
        details={
            "fields": [{"path": ["query", field], "code": code, "message": message}]
        },
    )


def _page(
    rows: list[object],
    limit: int,
    model: type[BaseModel],
    kind: str,
    fingerprint: str,
    sort_field: str,
    *,
    snapshot: dict[str, str] | None = None,
) -> Page[BaseModel]:
    has_more = len(rows) > limit
    selected = rows[:limit]
    items = [model.model_validate(row) for row in selected]
    next_cursor = None
    if has_more:
        last = selected[-1]
        next_cursor = encode_cursor(
            kind=kind,
            fingerprint=fingerprint,
            position={
                sort_field: cursor_datetime(last[sort_field]),
                "id": str(last["id"]),
            },
            snapshot=snapshot,
        )
    return Page(items=items, next_cursor=next_cursor)
