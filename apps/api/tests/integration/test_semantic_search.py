"""Real pgvector checks for authenticated semantic retrieval."""

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, MetaData, Table, event, text

from app.auth import VerifiedGoogleIdentity
from app.database import create_database_session_factory
from app.embeddings import EmbeddingFailure, process_card
from app.main import create_app
from app.semantic_text import DIMENSIONS
from tests.integration.test_learning_cards import (
    insert_card,
    insert_deck,
    insert_user,
    valid_card_values,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1",
        reason="set RUN_POSTGRES_INTEGRATION_TESTS=1 to run PostgreSQL integration tests",
    ),
]


class Verifier:
    def verify(self, token: str) -> VerifiedGoogleIdentity:
        if token != "owner-token":
            raise ValueError("invalid")
        return VerifiedGoogleIdentity("search-owner", "search@example.test")


@pytest.fixture
def search_client(
    migrated_database_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    monkeypatch.setenv(
        "DATABASE_URL",
        migrated_database_engine.url.render_as_string(hide_password=False),
    )
    monkeypatch.setenv("VERTEX_PROJECT_ID", "synthetic-project")
    monkeypatch.setenv("GOOGLE_ALLOWED_EMAILS", "search@example.test")
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        client.app.state.token_verifier = Verifier()
        yield client


def headers() -> dict[str, str]:
    return {"Authorization": "Bearer owner-token"}


def owner_id(engine: Engine) -> int:
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT id FROM users WHERE google_subject = 'search-owner'")
        ).scalar_one()


def add_indexed_card(
    engine: Engine, owner: int, deck_id: object, term: str, vector: list[float]
) -> object:
    table = Table("learning_cards", MetaData(), autoload_with=engine)
    card_id = insert_card(
        engine,
        table,
        valid_card_values(
            deck_id=deck_id, owner_id=owner, term=term, meaning=f"{term} meaning"
        ),
    )
    factory = create_database_session_factory(engine)
    assert process_card(factory, card_id, owner, lambda _: vector) == "ready"
    return card_id


def test_ranked_results_are_owner_and_eligibility_scoped(
    search_client: TestClient,
    migrated_database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert search_client.get("/v1/me", headers=headers()).status_code == 200
    owner = owner_id(migrated_database_engine)
    deck = insert_deck(migrated_database_engine, owner_id=owner)
    nearest = add_indexed_card(
        migrated_database_engine,
        owner,
        deck,
        "nearest",
        [1.0] + [0.0] * (DIMENSIONS - 1),
    )
    second = add_indexed_card(
        migrated_database_engine,
        owner,
        deck,
        "second",
        [1.0, 1.0] + [0.0] * (DIMENSIONS - 2),
    )
    missing_table = Table(
        "learning_cards", MetaData(), autoload_with=migrated_database_engine
    )
    insert_card(
        migrated_database_engine,
        missing_table,
        valid_card_values(
            deck_id=deck, owner_id=owner, term="missing", meaning="not indexed"
        ),
    )
    foreign_owner = insert_user(migrated_database_engine)
    foreign_deck = insert_deck(migrated_database_engine, owner_id=foreign_owner)
    add_indexed_card(
        migrated_database_engine,
        foreign_owner,
        foreign_deck,
        "foreign",
        [1.0] + [0.0] * (DIMENSIONS - 1),
    )
    other_deck = insert_deck(migrated_database_engine, owner_id=owner)
    add_indexed_card(
        migrated_database_engine,
        owner,
        other_deck,
        "other deck",
        [1.0] + [0.0] * (DIMENSIONS - 1),
    )
    japanese_deck = insert_deck(
        migrated_database_engine, owner_id=owner, target_language="ja"
    )
    add_indexed_card(
        migrated_database_engine,
        owner,
        japanese_deck,
        "wrong language",
        [1.0] + [0.0] * (DIMENSIONS - 1),
    )
    stale = add_indexed_card(
        migrated_database_engine,
        owner,
        deck,
        "stale model",
        [1.0] + [0.0] * (DIMENSIONS - 1),
    )
    archived = add_indexed_card(
        migrated_database_engine,
        owner,
        deck,
        "archived",
        [1.0] + [0.0] * (DIMENSIONS - 1),
    )
    with migrated_database_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE learning_cards SET archived_at = CURRENT_TIMESTAMP WHERE id = :id"
            ),
            {"id": archived},
        )
        connection.execute(
            text(
                "UPDATE card_embeddings SET model_version = 'stale-model' WHERE card_id = :id"
            ),
            {"id": stale},
        )
    monkeypatch.setattr(
        search_client.app.state.embedding_provider,
        "query_embedding",
        lambda *_args, **_kwargs: [1.0] + [0.0] * (DIMENSIONS - 1),
    )

    response = search_client.post(
        "/v1/cards/semantic-search",
        headers=headers(),
        json={
            "query": "similar idea",
            "target_language": "en",
            "deck_id": str(deck),
            "limit": 10,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["id"] for item in body["items"]] == [str(nearest), str(second)]
    assert body["items"][0]["score"] > body["items"][1]["score"]
    assert body["index_status"] == "partial"
    assert body["eligible_count"] == 4
    assert body["indexed_count"] == 2


def test_invalid_auth_and_body_do_not_call_provider(
    search_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []
    monkeypatch.setattr(
        search_client.app.state.embedding_provider,
        "query_embedding",
        lambda *_args, **_kwargs: calls.append(True) or [1.0] * DIMENSIONS,
    )
    unauthenticated = search_client.post(
        "/v1/cards/semantic-search",
        json={"query": "valid query", "target_language": "en"},
    )
    malformed = search_client.post(
        "/v1/cards/semantic-search",
        headers=headers(),
        json={"query": " ", "target_language": "en", "limit": 21},
    )
    assert unauthenticated.status_code == 401
    assert malformed.status_code == 422
    assert calls == []


def test_provider_failure_is_retryable_not_empty(
    search_client: TestClient,
    migrated_database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert search_client.get("/v1/me", headers=headers()).status_code == 200
    owner = owner_id(migrated_database_engine)
    deck = insert_deck(migrated_database_engine, owner_id=owner)
    add_indexed_card(
        migrated_database_engine,
        owner,
        deck,
        "indexed",
        [1.0] + [0.0] * (DIMENSIONS - 1),
    )
    monkeypatch.setattr(
        search_client.app.state.embedding_provider,
        "query_embedding",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            EmbeddingFailure("provider_timeout")
        ),
    )
    response = search_client.post(
        "/v1/cards/semantic-search",
        headers=headers(),
        json={"query": "valid query", "target_language": "en"},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "semantic_search_provider_unavailable"
    assert response.json()["error"]["retryable"] is True


@pytest.mark.parametrize("corpus", ["empty", "unindexed", "stale_hash", "stale_model"])
def test_corpus_without_current_embeddings_skips_provider_and_ranking(
    search_client: TestClient,
    migrated_database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    corpus: str,
) -> None:
    assert search_client.get("/v1/me", headers=headers()).status_code == 200
    owner = owner_id(migrated_database_engine)
    deck = insert_deck(migrated_database_engine, owner_id=owner)
    if corpus == "unindexed":
        cards = Table(
            "learning_cards", MetaData(), autoload_with=migrated_database_engine
        )
        insert_card(
            migrated_database_engine,
            cards,
            valid_card_values(
                deck_id=deck,
                owner_id=owner,
                term="unindexed",
                meaning="eligible without an embedding",
            ),
        )
    elif corpus in {"stale_hash", "stale_model"}:
        card = add_indexed_card(
            migrated_database_engine,
            owner,
            deck,
            "stale",
            [1.0] + [0.0] * (DIMENSIONS - 1),
        )
        with migrated_database_engine.begin() as connection:
            if corpus == "stale_hash":
                connection.execute(
                    text(
                        "UPDATE card_embeddings SET content_hash = :hash WHERE card_id = :id"
                    ),
                    {"hash": "0" * 64, "id": card},
                )
            else:
                connection.execute(
                    text(
                        "UPDATE card_embeddings SET model_version = 'stale-model' WHERE card_id = :id"
                    ),
                    {"id": card},
                )
    calls: list[str] = []
    monkeypatch.setattr(
        search_client.app.state.embedding_provider,
        "query_embedding",
        lambda query, **_kwargs: (
            calls.append(query) or [1.0] + [0.0] * (DIMENSIONS - 1)
        ),
    )

    ranking_statements: list[str] = []

    def record_ranking(_conn, _cursor, statement, _parameters, _context, _executemany):
        if "<=>" in statement:
            ranking_statements.append(statement)

    event.listen(Engine, "before_cursor_execute", record_ranking)
    try:
        response = search_client.post(
            "/v1/cards/semantic-search",
            headers=headers(),
            json={"query": "nothing indexed", "target_language": "en"},
        )
    finally:
        event.remove(Engine, "before_cursor_execute", record_ranking)

    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "index_status": "empty",
        "eligible_count": 0 if corpus == "empty" else 1,
        "indexed_count": 0,
    }
    assert (calls, ranking_statements) == ([], [])


def test_unconfigured_provider_still_reports_unavailable_for_empty_corpus(
    search_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    search_client.app.state.settings = search_client.app.state.settings.model_copy(
        update={"vertex_project_id": None}
    )
    calls: list[str] = []
    monkeypatch.setattr(
        search_client.app.state.embedding_provider,
        "query_embedding",
        lambda query, **_kwargs: calls.append(query) or [1.0] * DIMENSIONS,
    )

    response = search_client.post(
        "/v1/cards/semantic-search",
        headers=headers(),
        json={"query": "nothing indexed", "target_language": "en"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "semantic_search_not_configured"
    assert calls == []


def test_foreign_and_archived_decks_stop_before_provider(
    search_client: TestClient,
    migrated_database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert search_client.get("/v1/me", headers=headers()).status_code == 200
    owner = owner_id(migrated_database_engine)
    foreign_owner = insert_user(migrated_database_engine)
    foreign_deck = insert_deck(migrated_database_engine, owner_id=foreign_owner)
    archived_deck = insert_deck(migrated_database_engine, owner_id=owner)
    with migrated_database_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE learning_decks SET archived_at = CURRENT_TIMESTAMP WHERE id = :id"
            ),
            {"id": archived_deck},
        )
    calls: list[str] = []
    monkeypatch.setattr(
        search_client.app.state.embedding_provider,
        "query_embedding",
        lambda query, **_kwargs: (
            calls.append(query) or [1.0] + [0.0] * (DIMENSIONS - 1)
        ),
    )

    foreign_response = search_client.post(
        "/v1/cards/semantic-search",
        headers=headers(),
        json={
            "query": "foreign deck",
            "target_language": "en",
            "deck_id": str(foreign_deck),
        },
    )
    assert foreign_response.status_code == 404
    assert foreign_response.json()["error"]["code"] == "deck_not_found"

    archived_response = search_client.post(
        "/v1/cards/semantic-search",
        headers=headers(),
        json={
            "query": "archived deck",
            "target_language": "en",
            "deck_id": str(archived_deck),
        },
    )
    assert archived_response.status_code == 200
    assert archived_response.json() == {
        "items": [],
        "index_status": "empty",
        "eligible_count": 0,
        "indexed_count": 0,
    }
    assert calls == []
