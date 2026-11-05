"""Run production semantic_search SQL on frozen synthetic embeddings, with no network."""

import json
import os
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import MetaData, Table, text
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.auth import AuthenticatedUser
from app.database import bind_owner, create_database_session_factory
from app.embeddings import process_card
from app.semantic_search import SemanticSearchRequest, semantic_search
from app.semantic_text import canonical_text
from tests.eval.retrieval_eval import (
    LABELS,
    THRESHOLD,
    evaluate,
    initial_report,
    load_vectors,
    score_rankings,
    write_report,
)
from tests.integration.test_learning_cards import (
    insert_card,
    insert_deck,
    insert_user,
    valid_card_values,
)


class FrozenQueryProvider:
    def __init__(self, queries: dict):
        self.queries = queries

    def query_embedding(
        self, content: str, *, project: str, location: str
    ) -> list[float]:
        return self.queries[content]


def retrieve_rankings(engine, labels: dict, vectors: dict) -> dict:
    owner = insert_user(engine)
    # Frozen synthetic vectors only: consent is required before process_card embeds.
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE users SET genai_consent_at = now() WHERE id = :id"),
            {"id": owner},
        )
    deck = insert_deck(engine, owner_id=owner)
    table = Table("learning_cards", MetaData(), autoload_with=engine)
    factory = create_database_session_factory(engine)
    id_map = {}
    for index, card in enumerate(labels["cards"], start=1):
        fields = {key: value for key, value in card.items() if key != "id"}
        identifier = insert_card(
            engine,
            table,
            valid_card_values(
                id=UUID(int=index), deck_id=deck, owner_id=owner, **fields
            ),
        )
        id_map[identifier] = card["id"]

        def embed(content, card=card, fields=fields):
            # These synthetic cards contain exactly the fields in the manual runner's text.
            assert content == canonical_text({"language": "en", **fields})
            return vectors["cards"][card["id"]]

        assert process_card(factory, identifier, owner, embed) == "ready"

    app = SimpleNamespace(
        state=SimpleNamespace(
            settings=SimpleNamespace(
                vertex_project_id="offline-synthetic", vertex_location="us-central1"
            ),
            embedding_provider=FrozenQueryProvider(vectors["queries"]),
        )
    )
    request = Request({"type": "http", "app": app})
    user = AuthenticatedUser(owner, "synthetic-eval", "eval@example.invalid")

    def search(session):
        rankings = {}
        for query in labels["queries"]:
            result = semantic_search(
                SemanticSearchRequest(
                    query=query["text"], target_language="en", limit=10
                ),
                request,
                session,
                user,
            )
            assert result.index_status == "complete"
            assert result.indexed_count == result.eligible_count == 10
            rankings[query["text"]] = [id_map[item.id] for item in result.items]
        return rankings

    with Session(engine) as session:
        owner_rankings = search(session)
    with factory() as session:
        bind_owner(session, owner)
        assert session.scalar(text("SELECT current_user")) == "app_rls_test"
        rankings = search(session)
    assert rankings == owner_rankings
    return rankings


@pytest.mark.integration
def test_frozen_retrieval_ndcg(request):
    labels = json.loads(LABELS.read_text(encoding="utf-8"))
    report = initial_report(labels)
    try:
        # Load first: a missing fixture must fail even when PostgreSQL is not enabled.
        vectors = load_vectors(labels, report)
        assert os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") == "1", (
            "set RUN_POSTGRES_INTEGRATION_TESTS=1 and provide disposable PostgreSQL/pgvector"
        )
        engine = request.getfixturevalue("migrated_database_engine")
        rankings = retrieve_rankings(engine, labels, vectors)
        score_rankings(labels, rankings, report)
        assert report["macro_ndcg_at_5"] >= THRESHOLD, (
            f"macro nDCG@5 {report['macro_ndcg_at_5']} < {THRESHOLD}"
        )
    except BaseException as error:
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        write_report(report)


def test_deliberately_broken_ranking_fails_gate():
    labels = json.loads(LABELS.read_text(encoding="utf-8"))
    ideal = {
        query["text"]: sorted(
            (card["id"] for card in labels["cards"]),
            key=lambda identifier: (-query["relevance"].get(identifier, 0), identifier),
        )
        for query in labels["queries"]
    }
    broken = {query: list(reversed(ids)) for query, ids in ideal.items()}
    assert evaluate(labels, ideal)["macro_ndcg_at_5"] == 1.0
    assert evaluate(labels, broken)["macro_ndcg_at_5"] < THRESHOLD
