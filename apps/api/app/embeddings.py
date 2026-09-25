"""Retryable derived embeddings; provider calls never join card transactions."""

import json
import math
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.database import database_transaction
from app.semantic_text import DIMENSIONS, MODEL_VERSION, canonical_text, content_hash

CARD_SELECT = """
SELECT c.id, c.owner_id, c.semantic_content_hash, c.archived_at,
       d.archived_at AS deck_archived_at, d.target_language AS language,
       c.term, c.meaning, c.part_of_speech, c.part_of_speech_detail,
       c.reading, c.pronunciation, c.romanization, c.target_language_definition,
       c.example_sentence, c.example_translation, c.synonyms, c.antonyms
FROM learning_cards c JOIN learning_decks d
  ON (d.id, d.owner_id) = (c.deck_id, c.owner_id)
WHERE c.id = :card_id AND c.owner_id = :owner_id
"""


class EmbeddingFailure(Exception):
    """A bounded provider or contract failure with a safe code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def validate_vector(values: Sequence[float]) -> list[float]:
    if not isinstance(values, (list, tuple)) or len(values) != DIMENSIONS:
        raise EmbeddingFailure("invalid_dimension")
    if any(
        isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)
        for x in values
    ):
        raise EmbeddingFailure("invalid_value")
    if not any(x != 0 for x in values):
        raise EmbeddingFailure("zero_vector")
    return [float(x) for x in values]


def _vertex_embedding(
    content: str, *, task_type: str, project: str, location: str
) -> list[float]:
    """Use workload identity via ADC; never log request/response content."""

    import google.auth
    import requests
    from google.auth.transport.requests import Request as AuthRequest

    try:
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(AuthRequest())
        url = (
            f"https://{location}-aiplatform.googleapis.com/v1/projects/{project}"
            f"/locations/{location}/publishers/google/models/gemini-embedding-001:predict"
        )
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {credentials.token}"},
            json={
                "instances": [{"content": content, "task_type": task_type}],
                "parameters": {
                    "autoTruncate": False,
                    "outputDimensionality": DIMENSIONS,
                },
            },
            timeout=8,
        )
        response.raise_for_status()
        embedding = response.json()["predictions"][0]["embeddings"]
        stats = embedding["statistics"]
        if stats["truncated"] is not False:
            raise EmbeddingFailure("truncated_input")
        if (
            isinstance(stats["token_count"], bool)
            or not isinstance(stats["token_count"], int)
            or stats["token_count"] < 0
        ):
            raise EmbeddingFailure("invalid_response")
        return validate_vector(embedding["values"])
    except EmbeddingFailure:
        raise
    except requests.Timeout:
        raise EmbeddingFailure("provider_timeout") from None
    except requests.HTTPError as error:
        status = error.response.status_code if error.response is not None else None
        if status == 429:
            raise EmbeddingFailure("provider_rate_limited") from None
        raise EmbeddingFailure(
            "provider_unavailable"
            if status and status >= 500
            else "provider_http_error"
        ) from None
    except requests.RequestException:
        raise EmbeddingFailure("provider_http_error") from None
    except (KeyError, IndexError, TypeError, ValueError):
        raise EmbeddingFailure("invalid_response") from None
    except google.auth.exceptions.GoogleAuthError:
        raise EmbeddingFailure("provider_auth_error") from None


def vertex_document_embedding(
    content: str, *, project: str, location: str
) -> list[float]:
    return _vertex_embedding(
        content,
        task_type="RETRIEVAL_DOCUMENT",
        project=project,
        location=location,
    )


def vertex_query_embedding(content: str, *, project: str, location: str) -> list[float]:
    return _vertex_embedding(
        content,
        task_type="RETRIEVAL_QUERY",
        project=project,
        location=location,
    )


def process_card(
    session_factory: sessionmaker[Session],
    card_id: UUID,
    owner_id: int,
    embed: Callable[[str], Sequence[float]],
    *,
    force: bool = False,
) -> str:
    """Claim once, call provider outside transactions, then reject stale results."""

    with database_transaction(session_factory) as session:
        row = (
            session.execute(
                text(CARD_SELECT + " FOR UPDATE OF c"),
                {"card_id": card_id, "owner_id": owner_id},
            )
            .mappings()
            .one_or_none()
        )
        if (
            row is None
            or row.archived_at is not None
            or row.deck_archived_at is not None
        ):
            return "skipped"
        fields = dict(row)
        expected_hash = content_hash(fields)
        if row.semantic_content_hash != expected_hash:
            session.execute(
                text(
                    "UPDATE learning_cards SET semantic_content_hash = :hash WHERE id = :id AND owner_id = :owner_id"
                ),
                {"hash": expected_hash, "id": card_id, "owner_id": owner_id},
            )
        state = (
            session.execute(
                text("""
            SELECT content_hash, state, attempt_count, next_retry_at, last_attempt_at
            FROM card_embeddings
            WHERE card_id = :id AND owner_id = :owner_id AND model_version = :model
            FOR UPDATE
        """),
                {"id": card_id, "owner_id": owner_id, "model": MODEL_VERSION},
            )
            .mappings()
            .one_or_none()
        )
        if state and state.content_hash == expected_hash:
            if state.state == "ready":
                return "current"
            if (
                state.state == "pending"
                and state.last_attempt_at
                and (datetime.now(UTC) - state.last_attempt_at).total_seconds() < 120
            ):
                return "claimed"
            if not force and (
                state.state == "exhausted"
                or (state.next_retry_at and state.next_retry_at > datetime.now(UTC))
            ):
                return "deferred"
        attempt = min(
            (state.attempt_count + 1)
            if state and state.content_hash == expected_hash
            else 1,
            3,
        )
        claim_token = uuid4()
        session.execute(
            text("""
            INSERT INTO card_embeddings (card_id, owner_id, model_version, content_hash, state, attempt_count, last_attempt_at, claim_token)
            VALUES (:id, :owner_id, :model, :hash, 'pending', :attempt, CURRENT_TIMESTAMP, :claim_token)
            ON CONFLICT (card_id, owner_id, model_version) DO UPDATE
            SET content_hash = EXCLUDED.content_hash, state = 'pending', embedding = NULL,
                attempt_count = EXCLUDED.attempt_count, last_attempt_at = CURRENT_TIMESTAMP,
                next_retry_at = NULL, last_error_code = NULL, embedded_at = NULL,
                claim_token = EXCLUDED.claim_token
        """),
            {
                "id": card_id,
                "owner_id": owner_id,
                "model": MODEL_VERSION,
                "hash": expected_hash,
                "attempt": attempt,
                "claim_token": claim_token,
            },
        )
        content = canonical_text(fields)

    try:
        vector = validate_vector(embed(content))
        error_code = None
    except EmbeddingFailure as error:
        vector, error_code = None, error.code
    except Exception:  # noqa: BLE001 - provider adapters are untrusted
        vector, error_code = None, "provider_error"

    with database_transaction(session_factory) as session:
        current = (
            session.execute(
                text(CARD_SELECT + " FOR UPDATE OF c"),
                {"card_id": card_id, "owner_id": owner_id},
            )
            .mappings()
            .one_or_none()
        )
        if (
            current is None
            or current.archived_at is not None
            or current.deck_archived_at is not None
            or content_hash(dict(current)) != expected_hash
        ):
            return "stale"
        if error_code:
            session.execute(
                text("""
                UPDATE card_embeddings SET state = CASE WHEN attempt_count >= 3 THEN 'exhausted' ELSE 'retryable' END,
                    last_error_code = :code,
                    next_retry_at = CASE WHEN attempt_count >= 3 THEN NULL
                        ELSE CURRENT_TIMESTAMP + CASE attempt_count WHEN 1 THEN INTERVAL '1 minute' WHEN 2 THEN INTERVAL '4 minutes' ELSE INTERVAL '16 minutes' END * (1 + random() * 0.2) END
                WHERE card_id = :id AND owner_id = :owner_id AND model_version = :model
                  AND content_hash = :hash AND state = 'pending' AND claim_token = :claim_token
            """),
                {
                    "code": error_code,
                    "id": card_id,
                    "owner_id": owner_id,
                    "model": MODEL_VERSION,
                    "hash": expected_hash,
                    "claim_token": claim_token,
                },
            )
            return error_code
        result = session.execute(
            text("""
            UPDATE card_embeddings SET embedding = CAST(:vector AS vector(512)), state = 'ready',
                embedded_at = CURRENT_TIMESTAMP, next_retry_at = NULL, last_error_code = NULL
            WHERE card_id = :id AND owner_id = :owner_id AND model_version = :model
              AND content_hash = :hash AND state = 'pending' AND claim_token = :claim_token
        """),
            {
                "vector": json.dumps(vector),
                "id": card_id,
                "owner_id": owner_id,
                "model": MODEL_VERSION,
                "hash": expected_hash,
                "claim_token": claim_token,
            },
        )
        return "ready" if result.rowcount else "stale"
