"""Authenticated owner-safe semantic card retrieval."""

import json
import unicodedata
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth import CurrentUserDependency
from app.database import database_session
from app.embeddings import EmbeddingFailure, vertex_query_embedding
from app.errors import ApiError
from app.semantic_text import MODEL_VERSION

router = APIRouter(prefix="/v1/cards")
SessionDependency = Annotated[Session, Depends(database_session, scope="function")]


class SemanticSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=2, max_length=500)
    target_language: Literal["en"]
    deck_id: UUID | None = None
    limit: int = Field(default=10, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = unicodedata.normalize("NFC", value).strip()
        if not 2 <= len(normalized) <= 500:
            raise ValueError(
                "query must contain 2 through 500 characters after trimming"
            )
        return normalized


class SemanticSearchItem(BaseModel):
    id: UUID
    deck_id: UUID
    term: str
    meaning: str
    reading: str | None
    pronunciation: str | None
    romanization: str | None
    part_of_speech: str | None
    distance: float = Field(ge=0, le=2)
    score: float = Field(ge=-1, le=1)


class SemanticSearchResponse(BaseModel):
    items: list[SemanticSearchItem]
    index_status: Literal["complete", "partial", "empty"]
    eligible_count: int = Field(ge=0)
    indexed_count: int = Field(ge=0)


def _provider_error(error: EmbeddingFailure) -> ApiError:
    retryable = error.code in {
        "provider_timeout",
        "provider_rate_limited",
        "provider_unavailable",
        "provider_http_error",
        "provider_error",
    }
    return ApiError(
        status_code=503,
        code="semantic_search_provider_unavailable",
        message="Semantic search is temporarily unavailable.",
        retryable=retryable,
    )


@router.post("/semantic-search", response_model=SemanticSearchResponse)
def semantic_search(
    payload: SemanticSearchRequest,
    request: Request,
    session: SessionDependency,
    user: CurrentUserDependency,
) -> SemanticSearchResponse:
    """Rank only current embeddings belonging to the authenticated owner."""

    if payload.deck_id is not None:
        try:
            deck = (
                session.execute(
                    text("""
                    SELECT archived_at, target_language FROM learning_decks
                    WHERE id = :deck_id AND owner_id = :owner_id
                """),
                    {"deck_id": payload.deck_id, "owner_id": user.id},
                )
                .mappings()
                .one_or_none()
            )
        except SQLAlchemyError:
            raise ApiError(
                status_code=503,
                code="database_unavailable",
                message="The service cannot access learning data right now.",
                retryable=True,
            ) from None
        if deck is None:
            raise ApiError(
                status_code=404,
                code="deck_not_found",
                message="The requested deck was not found.",
            )
        if (
            deck.archived_at is not None
            or deck.target_language != payload.target_language
        ):
            return SemanticSearchResponse(
                items=[], index_status="empty", eligible_count=0, indexed_count=0
            )

    settings = request.app.state.settings
    if not settings.vertex_project_id:
        raise ApiError(
            status_code=503,
            code="semantic_search_not_configured",
            message="Semantic search is temporarily unavailable.",
            retryable=False,
        )
    try:
        query_vector = vertex_query_embedding(
            payload.query,
            project=settings.vertex_project_id,
            location=settings.vertex_location,
        )
        parameters = {
            "owner_id": user.id,
            "language": payload.target_language,
            "deck_id": payload.deck_id,
            "model": MODEL_VERSION,
            "vector": json.dumps(query_vector),
            "limit": payload.limit,
        }
        coverage = (
            session.execute(
                text("""
                SELECT count(*) AS eligible_count,
                       count(e.card_id) FILTER (
                         WHERE e.state = 'ready' AND e.embedding IS NOT NULL
                           AND e.content_hash = c.semantic_content_hash
                       ) AS indexed_count
                FROM learning_cards c
                JOIN learning_decks d ON (d.id, d.owner_id) = (c.deck_id, c.owner_id)
                LEFT JOIN card_embeddings e
                  ON e.card_id = c.id AND e.owner_id = c.owner_id
                 AND e.model_version = :model
                WHERE c.owner_id = :owner_id AND d.owner_id = :owner_id
                  AND c.archived_at IS NULL AND d.archived_at IS NULL
                  AND d.target_language = :language
                  AND (CAST(:deck_id AS uuid) IS NULL OR c.deck_id = CAST(:deck_id AS uuid))
            """),
                parameters,
            )
            .mappings()
            .one()
        )
        rows = (
            session.execute(
                text("""
                SELECT c.id, c.deck_id, c.term, c.meaning, c.reading,
                       c.pronunciation, c.romanization, c.part_of_speech,
                       (e.embedding <=> CAST(:vector AS vector(512)))::float AS distance,
                       (1 - (e.embedding <=> CAST(:vector AS vector(512))))::float AS score
                FROM learning_cards c
                JOIN learning_decks d ON (d.id, d.owner_id) = (c.deck_id, c.owner_id)
                JOIN card_embeddings e ON (e.card_id, e.owner_id) = (c.id, c.owner_id)
                WHERE c.owner_id = :owner_id AND d.owner_id = :owner_id
                  AND c.archived_at IS NULL AND d.archived_at IS NULL
                  AND d.target_language = :language
                  AND (CAST(:deck_id AS uuid) IS NULL OR c.deck_id = CAST(:deck_id AS uuid))
                  AND e.model_version = :model AND e.state = 'ready'
                  AND e.embedding IS NOT NULL
                  AND e.content_hash = c.semantic_content_hash
                ORDER BY e.embedding <=> CAST(:vector AS vector(512)), c.id
                LIMIT :limit
            """),
                parameters,
            )
            .mappings()
            .all()
        )
    except EmbeddingFailure as error:
        raise _provider_error(error) from None
    except SQLAlchemyError:
        raise ApiError(
            status_code=503,
            code="database_unavailable",
            message="The service cannot access learning data right now.",
            retryable=True,
        ) from None

    eligible_count = int(coverage.eligible_count)
    indexed_count = int(coverage.indexed_count)
    status: Literal["complete", "partial", "empty"] = (
        "empty"
        if eligible_count == 0 or indexed_count == 0
        else "complete"
        if indexed_count == eligible_count
        else "partial"
    )
    return SemanticSearchResponse(
        items=[SemanticSearchItem.model_validate(row) for row in rows],
        index_status=status,
        eligible_count=eligible_count,
        indexed_count=indexed_count,
    )
