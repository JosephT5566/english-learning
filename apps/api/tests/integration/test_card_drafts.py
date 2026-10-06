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


def bulk_payload(*terms):
    return {
        "cards": [
            {"idempotency_key": str(uuid4()), "fields": {"term": term, "meaning": term}}
            for term in terms
        ]
    }


def test_bulk_creates_atomic_fresh_states_and_replays(
    api_client, migrated_database_engine
):
    before = counts(migrated_database_engine)
    payload = bulk_payload("second", "first")
    path = f"/v1/decks/{FIXTURE_DECK_ID}/cards/bulk"
    created = api_client.post(path, json=payload, headers=bearer("fixture-token"))
    replay = api_client.post(path, json=payload, headers=bearer("fixture-token"))
    assert created.status_code == replay.status_code == 201
    assert created.json() == replay.json()
    results = created.json()["cards"]
    assert [item["card"]["term"] for item in results] == ["second", "first"]
    assert [item["idempotency_key"] for item in results] == [
        item["idempotency_key"] for item in payload["cards"]
    ]
    assert all(item["card"]["review_state"]["review_stage"] == 1 for item in results)
    assert counts(migrated_database_engine) == (before[0] + 2, before[1] + 2, before[2])
    with migrated_database_engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM learning_cards WHERE id IN (:first, :second) AND semantic_content_hash IS NOT NULL"
                ),
                {"first": results[0]["card"]["id"], "second": results[1]["card"]["id"]},
            ).scalar_one()
            == 2
        )


def test_bulk_conflict_rolls_back_earlier_insert_and_replays_legacy_card(
    api_client, migrated_database_engine
):
    key = "ffffffff-ffff-4fff-8fff-ffffffffffff"
    existing = api_client.post(
        "/v1/cards",
        json={"deck_id": FIXTURE_DECK_ID, "term": "old", "meaning": "old"},
        headers=create_headers("fixture-token", key),
    )
    assert existing.status_code == 201
    before = counts(migrated_database_engine)
    payload = bulk_payload("new", "changed")
    payload["cards"][0]["idempotency_key"] = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    payload["cards"][1]["idempotency_key"] = key
    path = f"/v1/decks/{FIXTURE_DECK_ID}/cards/bulk"
    rejected = api_client.post(path, json=payload, headers=bearer("fixture-token"))
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "idempotency_key_reused"
    assert counts(migrated_database_engine) == before
    payload["cards"][1]["fields"] = {"term": "old", "meaning": "old"}
    accepted = api_client.post(path, json=payload, headers=bearer("fixture-token"))
    assert accepted.status_code == 201
    assert accepted.json()["cards"][1]["card"]["id"] == existing.json()["id"]
    assert counts(migrated_database_engine) == (before[0] + 1, before[1] + 1, before[2])


def test_bulk_rejects_foreign_archived_and_invalid_without_writes(
    api_client, migrated_database_engine
):
    before = counts(migrated_database_engine)
    path = f"/v1/decks/{FIXTURE_DECK_ID}/cards/bulk"
    payload = bulk_payload("valid", "invalid")
    assert (
        api_client.post(
            path, json=payload, headers=bearer("attacker-token")
        ).status_code
        == 404
    )
    assert api_client.post(path, json=payload).status_code == 401
    payload["cards"][1]["fields"]["meaning"] = " "
    assert (
        api_client.post(path, json=payload, headers=bearer("fixture-token")).status_code
        == 422
    )
    payload = bulk_payload("one", "two")
    payload["cards"][1]["idempotency_key"] = payload["cards"][0]["idempotency_key"]
    assert (
        api_client.post(path, json=payload, headers=bearer("fixture-token")).status_code
        == 422
    )
    api_client.delete(f"/v1/decks/{FIXTURE_DECK_ID}", headers=bearer("fixture-token"))
    assert (
        api_client.post(
            path, json=bulk_payload("one"), headers=bearer("fixture-token")
        ).status_code
        == 409
    )
    assert counts(migrated_database_engine) == before


def test_concurrent_bulk_replay_creates_each_card_once(
    api_client, migrated_database_engine
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    before = counts(migrated_database_engine)
    payload = bulk_payload("one", "two")
    barrier = Barrier(2)

    def submit():
        barrier.wait(timeout=10)
        return api_client.post(
            f"/v1/decks/{FIXTURE_DECK_ID}/cards/bulk",
            json=payload,
            headers=bearer("fixture-token"),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: submit(), range(2)))
    assert all(response.status_code == 201 for response in responses)
    assert responses[0].json() == responses[1].json()
    assert counts(migrated_database_engine) == (before[0] + 2, before[1] + 2, before[2])


def test_bulk_embedding_failure_keeps_committed_cards(
    api_client, migrated_database_engine, monkeypatch
):
    from app import writes

    before = counts(migrated_database_engine)
    observed = []
    api_client.app.state.settings = api_client.app.state.settings.model_copy(
        update={"vertex_project_id": "test-project"}
    )

    def fail_embedding(*args, **kwargs):
        observed.append(counts(migrated_database_engine))
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(writes, "process_card", fail_embedding)
    response = api_client.post(
        f"/v1/decks/{FIXTURE_DECK_ID}/cards/bulk",
        json=bulk_payload("one", "two"),
        headers=bearer("fixture-token"),
    )
    assert response.status_code == 201
    expected = (before[0] + 2, before[1] + 2, before[2])
    assert observed == [expected, expected]
    assert counts(migrated_database_engine) == expected
