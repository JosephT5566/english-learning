"""Consent gates against real PostgreSQL with synthetic provider responses only."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, MetaData, Table, inspect, text

from app.auth import VerifiedGoogleIdentity
from app.database import create_database_session_factory
from app.embedding_backfill import run as run_backfill
from app.embeddings import process_card
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
CONSENT = "/v1/me/genai-consent"
SEARCH = "/v1/cards/semantic-search"


class Verifier:
    def verify(self, token: str) -> VerifiedGoogleIdentity:
        return VerifiedGoogleIdentity(token, f"{token}@example.test")


def headers(token: str = "alice") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(migrated_database_engine: Engine, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        migrated_database_engine.url.render_as_string(hide_password=False),
    )
    monkeypatch.setenv("VERTEX_PROJECT_ID", "synthetic-project")
    monkeypatch.setenv("GOOGLE_ALLOWED_EMAILS", "")
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        client.app.state.token_verifier = Verifier()
        yield client


def card_for(engine: Engine, owner: int):
    deck = insert_deck(engine, owner_id=owner)
    card = insert_card(
        engine,
        Table("learning_cards", MetaData(), autoload_with=engine),
        valid_card_values(deck_id=deck, owner_id=owner),
    )
    return deck, card


def count_embeddings(engine: Engine, owner: int) -> int:
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT count(*) FROM card_embeddings WHERE owner_id = :owner"),
            {"owner": owner},
        ).scalar_one()


def test_new_user_grant_and_withdraw(
    client: TestClient, migrated_database_engine: Engine
):
    response = client.get(CONSENT, headers=headers())
    assert response.status_code == 200
    assert response.json() == {"genai_consent_at": None}
    with migrated_database_engine.connect() as connection:
        assert (
            connection.execute(text("SELECT genai_consent_at FROM users")).scalar_one()
            is None
        )
    grant = client.put(CONSENT, headers=headers())
    assert grant.status_code == 200
    assert (
        datetime.fromisoformat(grant.json()["genai_consent_at"]).utcoffset() is not None
    )
    assert client.put(CONSENT, headers=headers()).json() == grant.json()
    assert client.get(CONSENT, headers=headers()).json() == grant.json()
    withdrawal = client.delete(CONSENT, headers=headers())
    assert withdrawal.status_code == 200
    assert withdrawal.json() == {"genai_consent_at": None}
    assert client.get(CONSENT, headers=headers()).json() == withdrawal.json()


def test_search_without_consent_never_calls_provider(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    calls = []
    monkeypatch.setattr(
        client.app.state.embedding_provider,
        "query_embedding",
        lambda *a, **kw: calls.append(a) or [1.0] * DIMENSIONS,
    )
    response = client.post(
        SEARCH, headers=headers(), json={"query": "an idea", "target_language": "en"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "genai_consent_required"
    assert calls == []


@pytest.mark.parametrize("consented", [False, True])
def test_card_writes_only_embed_with_consent(
    client: TestClient,
    migrated_database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    consented: bool,
):
    owner = client.get("/v1/me", headers=headers()).json()["id"]
    if consented:
        assert client.put(CONSENT, headers=headers()).status_code == 200
    deck = insert_deck(migrated_database_engine, owner_id=owner)
    calls = []
    monkeypatch.setattr(
        client.app.state.embedding_provider,
        "document_embedding",
        lambda *a, **kw: calls.append(a) or [1.0] * DIMENSIONS,
    )
    response = client.post(
        "/v1/cards",
        headers={**headers(), "Idempotency-Key": str(uuid4())},
        json={"deck_id": str(deck), "term": "example", "meaning": "first"},
    )
    assert response.status_code == 201
    updated = client.patch(
        f"/v1/cards/{response.json()['id']}",
        headers=headers(),
        json={"version": response.json()["version"], "meaning": "second"},
    )
    assert updated.status_code == 200
    assert len(calls) == (2 if consented else 0)
    assert count_embeddings(migrated_database_engine, owner) == (1 if consented else 0)


def test_backfill_and_processor_skip_unconsented_owner(
    migrated_database_engine: Engine, monkeypatch: pytest.MonkeyPatch
):
    engine = migrated_database_engine
    owner = insert_user(engine)
    _, card = card_for(engine, owner)
    calls = []
    outcome = process_card(
        create_database_session_factory(engine),
        card,
        owner,
        lambda content: calls.append(content) or [1.0] * DIMENSIONS,
    )
    assert outcome == "skipped"
    assert calls == []
    assert count_embeddings(engine, owner) == 0
    monkeypatch.setenv("DATABASE_URL", engine.url.render_as_string(hide_password=False))
    assert (
        run_backfill(owner_id=owner, cursor=None, limit=10, dry_run=True)["counts"]
        == {}
    )


def test_withdraw_deletes_only_own_embeddings_and_blocks_search(
    client: TestClient,
    migrated_database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
):
    engine = migrated_database_engine
    owners = []
    for token in ("alice", "bob"):
        owner = client.get("/v1/me", headers=headers(token)).json()["id"]
        owners.append(owner)
        assert client.put(CONSENT, headers=headers(token)).status_code == 200
        _, card = card_for(engine, owner)
        assert (
            process_card(
                create_database_session_factory(engine),
                card,
                owner,
                lambda _: [1.0] * DIMENSIONS,
            )
            == "ready"
        )
    calls = []
    monkeypatch.setattr(
        client.app.state.embedding_provider,
        "query_embedding",
        lambda *a, **kw: calls.append(a) or [1.0] * DIMENSIONS,
    )
    payload = {"query": "an idea", "target_language": "en"}
    assert client.post(SEARCH, headers=headers(), json=payload).status_code == 200
    assert len(calls) == 1
    assert client.delete(CONSENT, headers=headers()).status_code == 200
    assert count_embeddings(engine, owners[0]) == 0
    assert count_embeddings(engine, owners[1]) == 1
    assert client.post(SEARCH, headers=headers(), json=payload).status_code == 403
    assert len(calls) == 1
    assert (
        client.get(CONSENT, headers=headers("bob")).json()["genai_consent_at"]
        is not None
    )


def test_consent_routes_cannot_target_another_user(client: TestClient):
    bob = client.get("/v1/me", headers=headers("bob")).json()["id"]
    assert client.put(CONSENT, headers=headers("bob")).status_code == 200
    for method in ("get", "put", "delete"):
        assert client.request(method, CONSENT).status_code == 401
        assert (
            client.request(
                method, f"/v1/users/{bob}/genai-consent", headers=headers()
            ).status_code
            == 404
        )
        response = client.request(
            method, CONSENT, headers=headers(), params={"owner_id": bob}
        )
        assert response.status_code == 200
        assert (
            client.get(CONSENT, headers=headers("bob")).json()["genai_consent_at"]
            is not None
        )
    assert client.get(CONSENT, headers=headers()).json()["genai_consent_at"] is None


@pytest.mark.parametrize("regrant", [False, True])
def test_running_embedding_cannot_undo_withdrawal(
    client: TestClient, migrated_database_engine: Engine, regrant: bool
):
    engine = migrated_database_engine
    owner = client.get("/v1/me", headers=headers()).json()["id"]
    assert client.put(CONSENT, headers=headers()).status_code == 200
    _, card = card_for(engine, owner)
    entered, release = Event(), Event()

    def embed(_content):
        entered.set()
        assert release.wait(10)
        return [1.0] * DIMENSIONS

    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(
            process_card, create_database_session_factory(engine), card, owner, embed
        )
        try:
            assert entered.wait(10)
            assert client.delete(CONSENT, headers=headers()).status_code == 200
            assert count_embeddings(engine, owner) == 0
            if regrant:
                assert client.put(CONSENT, headers=headers()).status_code == 200
        finally:
            release.set()
        assert result.result(timeout=10) in {"skipped", "stale"}
    assert count_embeddings(engine, owner) == 0


def test_consent_migration_round_trip(
    temporary_database_url: str, monkeypatch: pytest.MonkeyPatch
):
    from sqlalchemy import create_engine

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", temporary_database_url)
    config = Config(Path(__file__).parents[2] / "alembic.ini")
    engine = create_engine(temporary_database_url)
    try:
        command.upgrade(config, "head")
        columns = {
            column["name"]: column for column in inspect(engine).get_columns("users")
        }
        assert columns["genai_consent_at"]["nullable"] is True
        assert columns["genai_consent_at"]["type"].timezone is True
        owner = insert_user(engine)
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT genai_consent_at FROM users WHERE id = :id"),
                    {"id": owner},
                ).scalar_one()
                is None
            )
        command.downgrade(config, "20260920_0006")
        assert "genai_consent_at" not in {
            column["name"] for column in inspect(engine).get_columns("users")
        }
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT genai_consent_at FROM users WHERE id = :id"),
                    {"id": owner},
                ).scalar_one()
                is None
            )
    finally:
        engine.dispose()
