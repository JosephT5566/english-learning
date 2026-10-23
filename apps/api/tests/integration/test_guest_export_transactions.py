"""Real PostgreSQL publication isolation and transaction cleanup."""

import os
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app import guest_export
from app.config import Settings
from app.database import create_database_session_factory
from app.main import create_app
from tests.integration.test_multilingual_domain_fixture import load_multilingual_fixture
from tests.unit.test_guest_export import CONFIG, PATH, claims

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1",
        reason="requires disposable PostgreSQL",
    ),
]
EN = UUID("10000000-0000-0000-0000-000000000001")
JA = UUID("10000000-0000-0000-0000-000000000002")


def snapshot(engine):
    with engine.connect() as connection:
        return {
            table: connection.execute(
                text(f"SELECT to_jsonb(t) FROM {table} AS t ORDER BY to_jsonb(t)::text")
            )
            .scalars()
            .all()
            for table in [
                "users",
                "learning_decks",
                "learning_cards",
                "tags",
                "learning_card_tags",
                "review_states",
                "review_batches",
                "review_events",
            ]
        }


def test_export_scope_archive_and_unchanged_tables(
    migrated_database_engine, monkeypatch
):
    engine = migrated_database_engine
    load_multilingual_fixture(engine)
    with engine.begin() as connection:
        connection.execute(text("UPDATE learning_cards SET note = 'private sentinel'"))
        connection.execute(
            text("""INSERT INTO learning_cards (id, deck_id, owner_id, term, meaning)
            SELECT gen_random_uuid(), d.id, d.owner_id, 'synthetic ' || n, 'meaning'
            FROM learning_decks d CROSS JOIN generate_series(1, 60) n WHERE d.id = :id"""),
            {"id": EN},
        )
    monkeypatch.setattr(
        "app.guest_export.google_id_token.verify_oauth2_token",
        Mock(return_value=claims()),
    )
    before = snapshot(engine)
    with TestClient(create_app()) as client:
        client.app.state.settings = Settings(**{**CONFIG, "guest_export_deck_id": EN})
        browser_verifier = Mock()
        client.app.state.token_verifier = browser_verifier
        headers = {"Authorization": "Bearer synthetic"}
        response = client.get(PATH, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert set(data) == {"schema_version", "generated_at", "items"}
        assert data["schema_version"] == 1
        assert len(data["items"]) == len({card["id"] for card in data["items"]}) == 50
        assert all(card["target_language"] == "en" for card in data["items"])
        assert "private sentinel" not in response.text
        assert set(data["items"][0]) == set(guest_export.PublicReviewCard.model_fields)
        assert snapshot(engine) == before
        browser_verifier.verify.assert_not_called()
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE learning_decks SET archived_at = now() WHERE id = :id"),
                {"id": EN},
            )
        assert client.get(PATH, headers=headers).json()["items"] == []
        for deck in [JA, uuid4()]:
            client.app.state.settings = Settings(
                **{**CONFIG, "guest_export_deck_id": deck}
            )
            assert client.get(PATH, headers=headers).status_code == 422
        client.app.state.settings = Settings(**{**CONFIG, "guest_export_deck_id": EN})
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE learning_decks SET archived_at = NULL WHERE id = :id"),
                {"id": EN},
            )
            connection.execute(
                text(
                    "UPDATE learning_cards SET archived_at = now() WHERE deck_id = :id"
                ),
                {"id": EN},
            )
        assert client.get(PATH, headers=headers).json()["items"] == []
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE learning_cards SET archived_at = NULL, meaning = repeat(chr(30028), 2000), target_language_definition = repeat(chr(30028), 2000) WHERE deck_id = :id"
                ),
                {"id": EN},
            )
        oversized_before = snapshot(engine)
        oversized = client.get(PATH, headers=headers)
        assert oversized.status_code == 422
        assert oversized.json()["error"]["code"] == "export_too_large"
        assert len(oversized.content) < 1024
        assert snapshot(engine) == oversized_before


def test_export_readonly_timeout_and_permit_cleanup(
    migrated_database_engine, monkeypatch
):
    engine = migrated_database_engine
    load_multilingual_fixture(engine)
    pooled = create_engine(engine.url, pool_size=1, max_overflow=0)
    monkeypatch.setattr(
        "app.guest_export.google_id_token.verify_oauth2_token",
        Mock(return_value=claims()),
    )
    try:
        with TestClient(create_app()) as client:
            client.app.state.database_session_factory = create_database_session_factory(
                pooled
            )
            client.app.state.settings = Settings(
                **{**CONFIG, "guest_export_deck_id": EN}
            )
            headers = {"Authorization": "Bearer synthetic"}
            before = snapshot(engine)
            monkeypatch.setattr(
                guest_export,
                "EXPORT_QUERY",
                text("UPDATE learning_cards SET meaning = 'forbidden' RETURNING id"),
            )
            assert client.get(PATH, headers=headers).status_code == 503
            assert snapshot(engine) == before
            client.app.state.settings = client.app.state.settings.model_copy(
                update={"guest_export_query_timeout_ms": 10}
            )
            monkeypatch.setattr(
                guest_export, "EXPORT_QUERY", text("SELECT pg_sleep(0.2)")
            )
            assert client.get(PATH, headers=headers).status_code == 503
            assert client.app.state.guest_export_permit.acquire(blocking=False)
            client.app.state.guest_export_permit.release()
            with pooled.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE learning_cards SET meaning = 'private writes still work' WHERE deck_id = :id"
                    ),
                    {"id": EN},
                )
    finally:
        pooled.dispose()
