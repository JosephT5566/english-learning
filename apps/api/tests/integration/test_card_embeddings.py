"""PostgreSQL lifecycle checks for retryable derived embeddings."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy import Engine, MetaData, Table, text

from app import embedding_backfill
from app.database import create_database_session_factory
from app.embedding_backfill import run as run_backfill
from app.embeddings import EmbeddingFailure, process_card
from app.semantic_text import DIMENSIONS, MODEL_VERSION
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


def fixture_card(engine: Engine) -> tuple[int, object]:
    owner_id = insert_user(engine)
    deck_id = insert_deck(engine, owner_id=owner_id)
    table = Table("learning_cards", MetaData(), autoload_with=engine)
    card_id = insert_card(
        engine, table, valid_card_values(deck_id=deck_id, owner_id=owner_id)
    )
    return owner_id, card_id


def embedding_row(engine: Engine, card_id: object) -> dict:
    with engine.connect() as connection:
        return dict(
            connection.execute(
                text("""
            SELECT state, content_hash, attempt_count, last_error_code
            FROM card_embeddings WHERE card_id = :id AND model_version = :model
        """),
                {"id": card_id, "model": MODEL_VERSION},
            )
            .mappings()
            .one()
        )


def test_failure_retry_current_and_semantic_edit(
    migrated_database_engine: Engine,
) -> None:
    engine = migrated_database_engine
    owner_id, card_id = fixture_card(engine)
    factory = create_database_session_factory(engine)

    def fail(_content: str) -> list[float]:
        raise EmbeddingFailure("provider_timeout")

    assert process_card(factory, card_id, owner_id, fail) == "provider_timeout"
    assert embedding_row(engine, card_id)["state"] == "retryable"
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT term FROM learning_cards WHERE id = :id"), {"id": card_id}
            ).scalar_one()
            == "example"
        )
    calls = []

    def embed(content: str) -> list[float]:
        calls.append(content)
        return [1.0] * DIMENSIONS

    assert process_card(factory, card_id, owner_id, embed, force=True) == "ready"
    assert process_card(factory, card_id, owner_id, embed) == "current"
    assert len(calls) == 1
    original_hash = embedding_row(engine, card_id)["content_hash"]
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE learning_cards SET meaning = 'new meaning' WHERE id = :id"),
            {"id": card_id},
        )
    assert process_card(factory, card_id, owner_id, embed) == "ready"
    assert len(calls) == 2
    assert embedding_row(engine, card_id)["content_hash"] != original_hash


def test_old_provider_result_cannot_overwrite_new_content(
    migrated_database_engine: Engine,
) -> None:
    engine = migrated_database_engine
    owner_id, card_id = fixture_card(engine)
    factory = create_database_session_factory(engine)

    def overtaken(_content: str) -> list[float]:
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE learning_cards SET meaning = 'new' WHERE id = :id"),
                {"id": card_id},
            )
        return [1.0] * DIMENSIONS

    assert process_card(factory, card_id, owner_id, overtaken) == "stale"
    assert embedding_row(engine, card_id)["state"] == "pending"
    assert (
        process_card(factory, card_id, owner_id, lambda _: [1.0] * DIMENSIONS)
        == "ready"
    )


def test_owner_and_archive_skip(migrated_database_engine: Engine) -> None:
    engine = migrated_database_engine
    owner_id, card_id = fixture_card(engine)
    factory = create_database_session_factory(engine)
    called = []
    embed = lambda content: called.append(content) or [1.0] * DIMENSIONS
    assert process_card(factory, card_id, owner_id + 100, embed) == "skipped"
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE learning_cards SET archived_at = CURRENT_TIMESTAMP WHERE id = :id"
            ),
            {"id": card_id},
        )
    assert process_card(factory, card_id, owner_id, embed) == "skipped"
    assert called == []


def test_bounded_dry_run_replays_from_cursor(
    migrated_database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = migrated_database_engine
    owner_id, card_id = fixture_card(engine)
    monkeypatch.setenv("DATABASE_URL", engine.url.render_as_string(hide_password=False))
    first = run_backfill(owner_id=owner_id, cursor=None, limit=1, dry_run=True)
    assert first["counts"] == {"eligible": 1}
    assert first["next_cursor"] == str(card_id)
    resumed = run_backfill(owner_id=owner_id, cursor=card_id, limit=1, dry_run=True)
    assert resumed["counts"] == {}


def test_concurrent_old_call_cannot_replace_new_embedding(
    migrated_database_engine: Engine,
) -> None:
    engine = migrated_database_engine
    owner_id, card_id = fixture_card(engine)
    factory = create_database_session_factory(engine)
    entered, release = Event(), Event()

    def old_provider(_content: str) -> list[float]:
        entered.set()
        assert release.wait(5)
        return [1.0] * DIMENSIONS

    with ThreadPoolExecutor(max_workers=1) as pool:
        old_result = pool.submit(process_card, factory, card_id, owner_id, old_provider)
        assert entered.wait(5)
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE learning_cards SET meaning = 'newer' WHERE id = :id"),
                {"id": card_id},
            )
        assert (
            process_card(factory, card_id, owner_id, lambda _: [2.0] * DIMENSIONS)
            == "ready"
        )
        release.set()
        assert old_result.result(timeout=5) == "stale"
    assert embedding_row(engine, card_id)["state"] == "ready"
    with engine.connect() as connection:
        stored = connection.execute(
            text("SELECT embedding::text FROM card_embeddings WHERE card_id = :id"),
            {"id": card_id},
        ).scalar_one()
    assert stored.startswith("[2,")


def test_sanitized_backfill_failure_and_retry_rehearsal(
    migrated_database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = migrated_database_engine
    owner_id, card_id = fixture_card(engine)
    monkeypatch.setenv("DATABASE_URL", engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("VERTEX_PROJECT_ID", "synthetic-project")

    def fail(*_args: object, **_kwargs: object) -> list[float]:
        raise EmbeddingFailure("provider_timeout")

    monkeypatch.setattr(embedding_backfill, "vertex_document_embedding", fail)
    first = run_backfill(owner_id=owner_id, cursor=None, limit=1)
    assert first["counts"] == {"provider_timeout": 1}
    assert embedding_row(engine, card_id)["state"] == "retryable"
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE card_embeddings SET next_retry_at = CURRENT_TIMESTAMP - INTERVAL '1 second' WHERE card_id = :id"
            ),
            {"id": card_id},
        )
    monkeypatch.setattr(
        embedding_backfill,
        "vertex_document_embedding",
        lambda *_args, **_kwargs: [1.0] * DIMENSIONS,
    )
    second = run_backfill(owner_id=owner_id, cursor=None, limit=1)
    assert second["counts"] == {"ready": 1}
    assert embedding_row(engine, card_id)["state"] == "ready"
