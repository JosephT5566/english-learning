"""PostgreSQL-backed authentication mapping and horizontal-isolation tests."""

import os
from collections.abc import Iterator
from typing import ClassVar
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app import writes
from app.auth import VerifiedGoogleIdentity
from app.embeddings import EmbeddingFailure
from app.main import create_app
from app.semantic_text import DIMENSIONS
from tests.integration.test_multilingual_domain_fixture import load_multilingual_fixture

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1",
        reason="set RUN_POSTGRES_INTEGRATION_TESTS=1 to run PostgreSQL integration tests",
    ),
]

FIXTURE_DECK_ID = "10000000-0000-0000-0000-000000000001"
FIXTURE_CARD_ID = "20000000-0000-0000-0000-000000000001"


class SwitchingTokenVerifier:
    identities: ClassVar[dict[str, VerifiedGoogleIdentity]] = {
        "fixture-token": VerifiedGoogleIdentity(
            "fixture-google-subject", "fixture.user@example.test"
        ),
        "attacker-token": VerifiedGoogleIdentity(
            "attacker-google-subject", "attacker@example.test"
        ),
    }

    def verify(self, token: str) -> VerifiedGoogleIdentity:
        return self.identities[token]


@pytest.fixture
def api_client(
    migrated_database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    load_multilingual_fixture(migrated_database_engine)
    monkeypatch.setenv(
        "DATABASE_URL",
        migrated_database_engine.url.render_as_string(hide_password=False),
    )
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        client.app.state.token_verifier = SwitchingTokenVerifier()
        yield client


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_headers(token: str, key: str | None = None) -> dict[str, str]:
    return {
        **bearer(token),
        "Idempotency-Key": key or str(uuid4()),
    }


def test_google_subject_maps_to_stable_internal_user_and_updates_email(
    api_client: TestClient,
    migrated_database_engine: Engine,
) -> None:
    first = api_client.get("/v1/me", headers=bearer("fixture-token"))
    SwitchingTokenVerifier.identities["fixture-token"] = VerifiedGoogleIdentity(
        "fixture-google-subject", "renamed@example.test"
    )
    try:
        second = api_client.get("/v1/me", headers=bearer("fixture-token"))
    finally:
        SwitchingTokenVerifier.identities["fixture-token"] = VerifiedGoogleIdentity(
            "fixture-google-subject", "fixture.user@example.test"
        )

    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert second.json()["email"] == "renamed@example.test"
    with migrated_database_engine.connect() as connection:
        stored = connection.execute(
            text("SELECT normalized_email FROM users WHERE google_subject = :subject"),
            {"subject": "fixture-google-subject"},
        ).scalar_one()
    assert stored == "renamed@example.test"


def test_backend_allowlist_rejects_disallowed_account_before_user_creation(
    migrated_database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        migrated_database_engine.url.render_as_string(hide_password=False),
    )
    monkeypatch.setenv("GOOGLE_ALLOWED_EMAILS", "fixture.user@example.test")
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        client.app.state.token_verifier = SwitchingTokenVerifier()
        response = client.get("/v1/me", headers=bearer("attacker-token"))
        with migrated_database_engine.connect() as connection:
            count_after_denial = connection.execute(
                text("SELECT count(*) FROM users")
            ).scalar_one()
        allowed = client.get("/v1/me", headers=bearer("fixture-token"))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "account_not_allowed"
    assert count_after_denial == 0
    assert allowed.status_code == 200
    with migrated_database_engine.connect() as connection:
        count = connection.execute(text("SELECT count(*) FROM users")).scalar_one()
    assert count == 1


def test_other_user_cannot_read_deck_card_or_due_review_by_changing_ids(
    api_client: TestClient,
) -> None:
    headers = bearer("attacker-token")

    deck = api_client.get(f"/v1/decks/{FIXTURE_DECK_ID}", headers=headers)
    card = api_client.get(f"/v1/cards/{FIXTURE_CARD_ID}", headers=headers)
    due = api_client.get(
        "/v1/reviews/due",
        params={"target_language": "en", "deck_id": FIXTURE_DECK_ID},
        headers=headers,
    )
    decks = api_client.get("/v1/decks", headers=headers)
    cards = api_client.get("/v1/cards", headers=headers)

    assert deck.status_code == card.status_code == due.status_code == 404
    assert decks.json()["items"] == []
    assert cards.json()["items"] == []


def test_create_derives_owner_and_rejects_client_identity_and_foreign_parent(
    api_client: TestClient,
    migrated_database_engine: Engine,
) -> None:
    headers = bearer("attacker-token")
    rejected = api_client.post(
        "/v1/decks",
        json={
            "title": "Injected owner",
            "target_language": "en",
            "explanation_language": "zh-TW",
            "owner_id": 1,
            "email": "fixture.user@example.test",
        },
        headers=headers,
    )
    assert rejected.status_code == 422

    deck = api_client.post(
        "/v1/decks",
        json={
            "title": "Attacker's own deck",
            "target_language": "ja",
            "explanation_language": "zh-TW",
        },
        headers=create_headers("attacker-token"),
    )
    assert deck.status_code == 201
    deck_id = deck.json()["id"]

    foreign_parent = api_client.post(
        "/v1/cards",
        json={"deck_id": FIXTURE_DECK_ID, "term": "bad", "meaning": "bad"},
        headers=create_headers("attacker-token"),
    )
    assert foreign_parent.status_code == 404
    assert foreign_parent.json()["error"]["code"] == "deck_not_found"

    card = api_client.post(
        "/v1/cards",
        json={"deck_id": deck_id, "term": "勉強", "meaning": "study"},
        headers=create_headers("attacker-token"),
    )
    assert card.status_code == 201
    card_id = card.json()["id"]

    with migrated_database_engine.connect() as connection:
        owners = connection.execute(
            text(
                """
                SELECT d.owner_id, c.owner_id
                FROM learning_decks AS d
                JOIN learning_cards AS c ON c.deck_id = d.id
                JOIN users AS u ON u.id = d.owner_id
                WHERE d.id = :deck_id AND u.google_subject = :subject
                """
            ),
            {"deck_id": deck_id, "subject": "attacker-google-subject"},
        ).one()
        initial_review_state = connection.execute(
            text(
                """
                SELECT review_stage, ease_factor, interval_days,
                       last_reviewed_at, version
                FROM review_states
                WHERE card_id = :card_id AND owner_id = :owner_id
                """
            ),
            {"card_id": card_id, "owner_id": owners[0]},
        ).one()
    assert owners[0] == owners[1]
    assert initial_review_state == (1, 2.50, 0, None, 1)


@pytest.mark.parametrize("value", [None, "not-a-uuid"])
def test_create_requires_valid_idempotency_key(
    api_client: TestClient,
    value: str | None,
) -> None:
    headers = bearer("fixture-token")
    if value is not None:
        headers["Idempotency-Key"] = value

    response = api_client.post(
        "/v1/decks",
        json={
            "title": "Safe retry",
            "target_language": "en",
            "explanation_language": "zh-TW",
        },
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_idempotency_key"


def test_deck_create_replays_exact_request_and_rejects_key_reuse(
    api_client: TestClient,
    migrated_database_engine: Engine,
) -> None:
    key = str(uuid4())
    headers = create_headers("fixture-token", key)
    payload = {
        "title": "Retry-safe English",
        "target_language": "en",
        "explanation_language": "zh-TW",
    }

    created = api_client.post("/v1/decks", json=payload, headers=headers)
    replayed = api_client.post("/v1/decks", json=payload, headers=headers)
    conflict = api_client.post(
        "/v1/decks",
        json={**payload, "title": "Different content"},
        headers=headers,
    )

    assert created.status_code == replayed.status_code == 201
    assert created.json() == replayed.json()
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_key_reused"
    with migrated_database_engine.connect() as connection:
        count = connection.execute(
            text(
                """
                SELECT count(*)
                FROM learning_decks
                WHERE creation_idempotency_key = :key
                """
            ),
            {"key": key},
        ).scalar_one()
    assert count == 1


def test_card_create_replays_card_and_single_initial_state(
    api_client: TestClient,
    migrated_database_engine: Engine,
) -> None:
    key = str(uuid4())
    headers = create_headers("fixture-token", key)
    payload = {
        "deck_id": FIXTURE_DECK_ID,
        "term": "idempotent",
        "meaning": "safe to repeat",
        "learned_on": "2026-09-12",
    }

    created = api_client.post("/v1/cards", json=payload, headers=headers)
    replayed = api_client.post("/v1/cards", json=payload, headers=headers)
    conflict = api_client.post(
        "/v1/cards",
        json={**payload, "meaning": "different content"},
        headers=headers,
    )

    assert created.status_code == replayed.status_code == 201
    assert created.json() == replayed.json()
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_key_reused"
    with migrated_database_engine.connect() as connection:
        counts = connection.execute(
            text(
                """
                SELECT count(*), count(s.card_id)
                FROM learning_cards AS c
                LEFT JOIN review_states AS s
                  ON (s.card_id, s.owner_id) = (c.id, c.owner_id)
                WHERE c.creation_idempotency_key = :key
                """
            ),
            {"key": key},
        ).one()
    assert counts == (1, 1)


def test_card_create_commits_before_provider_timeout_and_replays_once(
    api_client: TestClient,
    migrated_database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api_client.app.state.settings = api_client.app.state.settings.model_copy(
        update={"vertex_project_id": "synthetic-project"}
    )
    calls = []

    def timeout(content: str, **_kwargs: object) -> list[float]:
        calls.append(content)
        raise EmbeddingFailure("provider_timeout")

    monkeypatch.setattr(writes, "vertex_document_embedding", timeout)
    key = str(uuid4())
    payload = {"deck_id": FIXTURE_DECK_ID, "term": "derived", "meaning": "safe card"}
    headers = create_headers("fixture-token", key)
    first = api_client.post("/v1/cards", json=payload, headers=headers)
    replay = api_client.post("/v1/cards", json=payload, headers=headers)
    assert first.status_code == replay.status_code == 201
    assert first.json()["id"] == replay.json()["id"]
    assert len(calls) == 1
    with migrated_database_engine.connect() as connection:
        row = connection.execute(
            text("""
                SELECT count(*), count(s.card_id), max(e.state)
                FROM learning_cards c
                LEFT JOIN review_states s ON (s.card_id, s.owner_id) = (c.id, c.owner_id)
                LEFT JOIN card_embeddings e ON (e.card_id, e.owner_id) = (c.id, c.owner_id)
                WHERE c.creation_idempotency_key = :key
            """),
            {"key": key},
        ).one()
    assert row == (1, 1, "retryable")


def test_only_semantic_card_edits_call_provider(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api_client.app.state.settings = api_client.app.state.settings.model_copy(
        update={"vertex_project_id": "synthetic-project"}
    )
    calls = []

    def embed(content: str, **_kwargs: object) -> list[float]:
        calls.append(content)
        return [1.0] * DIMENSIONS

    monkeypatch.setattr(writes, "vertex_document_embedding", embed)
    headers = bearer("fixture-token")
    original = api_client.get(f"/v1/cards/{FIXTURE_CARD_ID}", headers=headers).json()
    note = api_client.patch(
        f"/v1/cards/{FIXTURE_CARD_ID}",
        json={"version": original["version"], "note": "a note"},
        headers=headers,
    )
    assert note.status_code == 200
    assert calls == []
    semantic = api_client.patch(
        f"/v1/cards/{FIXTURE_CARD_ID}",
        json={"version": note.json()["version"], "meaning": "changed meaning"},
        headers=headers,
    )
    assert semantic.status_code == 200
    assert len(calls) == 1
    unchanged = api_client.patch(
        f"/v1/cards/{FIXTURE_CARD_ID}",
        json={"version": semantic.json()["version"], "meaning": "changed meaning"},
        headers=headers,
    )
    assert unchanged.status_code == 200
    assert len(calls) == 1


def test_other_user_cannot_edit_or_archive_resources_by_changing_ids(
    api_client: TestClient,
    migrated_database_engine: Engine,
) -> None:
    headers = bearer("attacker-token")
    deck_patch = api_client.patch(
        f"/v1/decks/{FIXTURE_DECK_ID}",
        json={"version": 1, "title": "stolen"},
        headers=headers,
    )
    card_patch = api_client.patch(
        f"/v1/cards/{FIXTURE_CARD_ID}",
        json={"version": 1, "term": "stolen"},
        headers=headers,
    )
    card_archive = api_client.delete(f"/v1/cards/{FIXTURE_CARD_ID}", headers=headers)
    deck_archive = api_client.delete(f"/v1/decks/{FIXTURE_DECK_ID}", headers=headers)

    assert {
        response.status_code
        for response in (deck_patch, card_patch, card_archive, deck_archive)
    } == {404}
    with migrated_database_engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT d.title, d.archived_at, c.term, c.archived_at
                FROM learning_decks AS d
                JOIN learning_cards AS c ON c.deck_id = d.id
                WHERE d.id = :deck_id AND c.id = :card_id
                """
            ),
            {"deck_id": FIXTURE_DECK_ID, "card_id": FIXTURE_CARD_ID},
        ).one()
    assert row == ("English fixture deck", None, "serendipity", None)


def test_owner_can_edit_and_archive_with_version_conflict_protection(
    api_client: TestClient,
) -> None:
    headers = bearer("fixture-token")
    deck = api_client.patch(
        f"/v1/decks/{FIXTURE_DECK_ID}",
        json={"version": 1, "title": "Renamed deck"},
        headers=headers,
    )
    card = api_client.patch(
        f"/v1/cards/{FIXTURE_CARD_ID}",
        json={"version": 1, "meaning": "a fortunate discovery"},
        headers=headers,
    )
    stale = api_client.patch(
        f"/v1/cards/{FIXTURE_CARD_ID}",
        json={"version": 1, "meaning": "stale overwrite"},
        headers=headers,
    )
    archived_card = api_client.delete(f"/v1/cards/{FIXTURE_CARD_ID}", headers=headers)
    archived_deck = api_client.delete(f"/v1/decks/{FIXTURE_DECK_ID}", headers=headers)

    assert deck.status_code == card.status_code == 200
    assert deck.json()["version"] == card.json()["version"] == 2
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "version_conflict"
    assert archived_card.status_code == archived_deck.status_code == 204
