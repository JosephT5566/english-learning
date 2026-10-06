"""Owner-safe JSON preview followed by normal idempotent card creation."""

import os
from uuid import uuid4

import pytest
from sqlalchemy import text

from tests.integration.test_auth_and_authorization import (
    FIXTURE_DECK_ID,
    bearer,
    create_headers,
)
from tests.integration.test_auth_and_authorization import (
    api_client as owned_client_fixture,
)

api_client = owned_client_fixture

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1",
        reason="PostgreSQL tests are opt-in",
    ),
]


def counts(engine):
    with engine.connect() as connection:
        return tuple(
            connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            for table in ("learning_cards", "review_states", "review_events")
        )


def test_preview_never_writes_and_confirmed_cards_replay_once(
    api_client, migrated_database_engine
):
    before = counts(migrated_database_engine)
    payload = {
        "cards": [
            {"term": "first", "meaning": "one"},
            {"term": "second", "meaning": "two"},
        ]
    }
    preview = api_client.post(
        f"/v1/decks/{FIXTURE_DECK_ID}/card-drafts/validate",
        json=payload,
        headers=bearer("fixture-token"),
    )
    assert preview.status_code == 200
    assert counts(migrated_database_engine) == before
    ids = []
    for fields in preview.json()["cards"]:
        headers = create_headers("fixture-token")
        command = {**fields, "deck_id": FIXTURE_DECK_ID}
        created = api_client.post("/v1/cards", json=command, headers=headers)
        replay = api_client.post("/v1/cards", json=command, headers=headers)
        assert created.status_code == replay.status_code == 201
        assert created.json()["id"] == replay.json()["id"]
        assert created.json()["review_state"]["review_stage"] == 1
        ids.append(created.json()["id"])
    assert len(set(ids)) == 2
    assert counts(migrated_database_engine) == (before[0] + 2, before[1] + 2, before[2])


def test_invalid_foreign_and_archived_decks_create_no_learning_data(
    api_client, migrated_database_engine
):
    before = counts(migrated_database_engine)
    payload = {"cards": [{"term": "test", "meaning": "test"}]}
    path = f"/v1/decks/{FIXTURE_DECK_ID}/card-drafts/validate"
    foreign = api_client.post(path, json=payload, headers=bearer("attacker-token"))
    missing = api_client.post(
        f"/v1/decks/{uuid4()}/card-drafts/validate",
        json=payload,
        headers=bearer("attacker-token"),
    )
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["error"]["code"] == missing.json()["error"]["code"]
    assert (
        api_client.post(
            path,
            json={"cards": [{"term": "", "meaning": "test"}]},
            headers=bearer("fixture-token"),
        ).status_code
        == 422
    )
    assert (
        api_client.delete(
            f"/v1/decks/{FIXTURE_DECK_ID}", headers=bearer("fixture-token")
        ).status_code
        == 204
    )
    assert (
        api_client.post(path, json=payload, headers=bearer("fixture-token")).status_code
        == 409
    )
    assert counts(migrated_database_engine) == before
