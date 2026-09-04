"""PostgreSQL-backed authentication mapping and horizontal-isolation tests."""

import os
from collections.abc import Iterator
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.auth import VerifiedGoogleIdentity
from app.main import create_app
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
        headers=headers,
    )
    assert deck.status_code == 201
    deck_id = deck.json()["id"]

    foreign_parent = api_client.post(
        "/v1/cards",
        json={"deck_id": FIXTURE_DECK_ID, "term": "bad", "meaning": "bad"},
        headers=headers,
    )
    assert foreign_parent.status_code == 404
    assert foreign_parent.json()["error"]["code"] == "deck_not_found"

    card = api_client.post(
        "/v1/cards",
        json={"deck_id": deck_id, "term": "勉強", "meaning": "study"},
        headers=headers,
    )
    assert card.status_code == 201

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
    assert owners[0] == owners[1]


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
