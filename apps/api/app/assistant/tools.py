"""Fixed readonly registry. Provider schemas are minimal and unverified on Vertex."""

import time
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.genai_consent import require_genai_consent
from app.generation import GenerationFailure
from app.reads import DUE_CONDITION, get_due_cards
from app.semantic_search import SemanticSearchRequest, search_cards


class Filters(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    deck_id: UUID | None = None
    target_language: Literal["en", "ja"] | None = None


class DueArguments(Filters):
    target_language: Literal["en", "ja"]
    limit: int = 5


class SearchArguments(DueArguments):
    target_language: Literal["en"]
    query: str = Field(min_length=2, max_length=500)


# Only these keywords cross the provider boundary. Server models enforce UUIDs,
# lengths, extra-field rejection and limits. Tool schema acceptance is unverified.
FILTER_SCHEMA = {
    "deck_id": {"type": "string"},
    "target_language": {"type": "string", "enum": ["en", "ja"]},
}
TOOL_SCHEMAS = [
    {
        "name": "search_cards",
        "description": "Search owned English cards by meaning.",
        "parameters": {
            "type": "object",
            "properties": {
                **FILTER_SCHEMA,
                "target_language": {"type": "string", "enum": ["en"]},
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query", "target_language"],
        },
    },
    {
        "name": "get_due_cards",
        "description": "Read the first page of owned due cards.",
        "parameters": {
            "type": "object",
            "properties": {**FILTER_SCHEMA, "limit": {"type": "integer"}},
            "required": ["target_language"],
        },
    },
    {
        "name": "get_review_stats",
        "description": "Count owned active and due cards.",
        "parameters": {"type": "object", "properties": FILTER_SCHEMA},
    },
]
ARGUMENT_MODELS = {
    "search_cards": SearchArguments,
    "get_due_cards": DueArguments,
    "get_review_stats": Filters,
}


def validate_call(name: str, arguments: dict, settings: Settings) -> dict:
    """Validate external JSON strictly; owner context is never accepted as data."""
    model = ARGUMENT_MODELS.get(name)
    if model is None:
        raise ValueError("invalid_tool_call")
    # UUIDs arrive as JSON strings. Pydantic's JSON mode keeps other strict checks.
    import json

    try:
        validated = model.model_validate_json(json.dumps(arguments))
        if isinstance(validated, SearchArguments):
            normalized = SemanticSearchRequest(
                query=validated.query, target_language="en"
            )
            validated.query = normalized.query
    except (ValidationError, TypeError, ValueError):
        raise ValueError("invalid_tool_call") from None
    if isinstance(validated, DueArguments):
        validated.limit = min(settings.assistant_tool_limit, max(1, validated.limit))
    return validated.model_dump(mode="json", exclude_none=True)


def get_review_stats(
    session, owner_id, *, deck_id=None, target_language=None, as_of=None
):
    """Count active cards with exactly the paginated read's due predicate."""
    row = (
        session.execute(
            text(f"""
        SELECT count(*) AS total_count,
               count(*) FILTER (WHERE {DUE_CONDITION}) AS due_count
        FROM learning_cards c
        JOIN learning_decks d ON (d.id, d.owner_id) = (c.deck_id, c.owner_id)
        LEFT JOIN review_states s ON (s.card_id, s.owner_id) = (c.id, c.owner_id)
        WHERE c.owner_id = :owner_id AND d.owner_id = :owner_id
          AND c.archived_at IS NULL AND d.archived_at IS NULL
          AND (CAST(:deck_id AS uuid) IS NULL OR c.deck_id = CAST(:deck_id AS uuid))
          AND (CAST(:language AS text) IS NULL OR d.target_language = :language)
    """),
            {
                "owner_id": owner_id,
                "deck_id": deck_id,
                "language": target_language,
                "as_of": as_of or datetime.now(UTC),
            },
        )
        .mappings()
        .one()
    )
    return dict(row)


class AssistantDeadlineExceeded(GenerationFailure):
    """A local assistant budget elapsed or its request was cancelled."""

    def __init__(self):
        super().__init__("provider_timeout")


def check_budget(deadline, cancelled=None):
    if (cancelled is not None and cancelled()) or time.monotonic() >= deadline:
        raise AssistantDeadlineExceeded()


def set_query_budget(session, deadline, *, readonly=False, cancelled=None):
    """Apply the remaining SQL budget; recheck after any pool/connection wait."""
    check_budget(deadline, cancelled)
    if readonly:
        session.execute(text("SET TRANSACTION READ ONLY"))
    check_budget(deadline, cancelled)
    remaining = deadline - time.monotonic()
    session.execute(
        text("SELECT set_config('statement_timeout', :value, true)"),
        {"value": str(max(1, int(remaining * 1000)))},
    )
    check_budget(deadline, cancelled)


class SessionTools:
    """Execute only validated registry calls in the request's RLS-bound session."""

    def __init__(
        self, session, owner_id, settings, embedding_provider, *, cancelled=None
    ):
        self.session = session
        self.owner_id = owner_id
        self.settings = settings
        self.embedding_provider = embedding_provider
        self.cancelled = cancelled
        self.as_of = datetime.now(UTC)

    def __call__(self, name, arguments, deadline):
        session = self.session

        def readonly_query():
            set_query_budget(session, deadline, readonly=True, cancelled=self.cancelled)

        try:
            # Recheck consent before transmitting a query to the embedding provider.
            # The lock is released before the readonly tool transaction begins.
            if name == "search_cards":
                set_query_budget(session, deadline, cancelled=self.cancelled)
                require_genai_consent(session, self.owner_id)
                session.commit()
            readonly_query()
            if name == "get_review_stats":
                return get_review_stats(
                    session, self.owner_id, **arguments, as_of=self.as_of
                )
            if name == "get_due_cards":
                page = get_due_cards(
                    session,
                    self.owner_id,
                    arguments["target_language"],
                    [UUID(arguments["deck_id"])] if arguments.get("deck_id") else None,
                    arguments["limit"],
                    as_of=self.as_of,
                )
                # Expose content only, not review internals or pagination cursors.
                return {
                    "items": [
                        {
                            "id": str(card.id),
                            "deck_id": str(card.deck.id),
                            "term": card.term,
                            "meaning": card.meaning,
                            "note": card.note,
                        }
                        for card in page.items
                    ]
                }
            if name == "search_cards":
                # Embedding has its own transport timeout. This wrapper also bounds
                # waiting through the same provider-only deadline helper as generation.
                from app.assistant.loop import bounded_call

                provider = self.embedding_provider
                options = (
                    {"cancelled": self.cancelled} if self.cancelled is not None else {}
                )

                class BoundedEmbedding:
                    def query_embedding(inner, *args, **kwargs):
                        check_budget(deadline, self.cancelled)
                        return bounded_call(
                            lambda: provider.query_embedding(
                                *args, deadline=deadline, **kwargs, **options
                            ),
                            deadline - time.monotonic(),
                        )

                result = search_cards(
                    SemanticSearchRequest(**arguments),
                    session,
                    self.owner_id,
                    self.settings,
                    BoundedEmbedding(),
                    release_transaction=True,
                    before_ranking=readonly_query,
                )
                return result.model_dump(mode="json")
            raise ValueError("invalid_tool_call")
        except SQLAlchemyError as error:
            if getattr(getattr(error, "orig", None), "sqlstate", None) == "57014":
                raise AssistantDeadlineExceeded() from None
            raise
        finally:
            # Release every readonly transaction, including failed queries.
            session.rollback()
