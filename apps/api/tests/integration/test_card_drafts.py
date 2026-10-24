"""Owner-safe JSON preview followed by normal idempotent card creation."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from time import monotonic, sleep
from uuid import uuid4

import pytest
from sqlalchemy import event, text

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


@pytest.mark.parametrize("card_count", [1, 3, 20])
def test_bulk_locks_deck_once(api_client, card_count):
    deck_locks = []

    def record_deck_lock(
        connection, cursor, statement, parameters, context, executemany
    ):
        if "FROM learning_decks" in statement and "FOR UPDATE" in statement:
            deck_locks.append(statement)

    engine = api_client.app.state.database_engine
    event.listen(engine, "before_cursor_execute", record_deck_lock)
    try:
        response = api_client.post(
            f"/v1/decks/{FIXTURE_DECK_ID}/cards/bulk",
            json=bulk_payload(*(f"term-{index}" for index in range(card_count))),
            headers=bearer("fixture-token"),
        )
    finally:
        event.remove(engine, "before_cursor_execute", record_deck_lock)

    assert response.status_code == 201
    assert len(response.json()["cards"]) == card_count
    assert len(deck_locks) == 1


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
    before = counts(migrated_database_engine)
    payload = bulk_payload("one", "two")
    responses = submit_bulk_with_deck_contention(
        api_client, migrated_database_engine, [payload, payload]
    )
    assert all(response.status_code == 201 for response in responses)
    assert responses[0].json() == responses[1].json()
    assert counts(migrated_database_engine) == (before[0] + 2, before[1] + 2, before[2])


def test_overlapping_bulk_batches_preserve_order_and_create_shared_card_once(
    api_client, migrated_database_engine
):
    before = counts(migrated_database_engine)
    first = bulk_payload("first", "shared")
    second = bulk_payload("last")
    second["cards"].insert(0, first["cards"][1])
    responses = submit_bulk_with_deck_contention(
        api_client, migrated_database_engine, [first, second]
    )
    assert all(response.status_code == 201 for response in responses)
    results = [response.json()["cards"] for response in responses]
    assert [item["card"]["term"] for item in results[0]] == ["first", "shared"]
    assert [item["card"]["term"] for item in results[1]] == ["shared", "last"]
    assert results[0][1] == results[1][0]
    assert counts(migrated_database_engine) == (before[0] + 3, before[1] + 3, before[2])


def submit_bulk_with_deck_contention(api_client, engine, payloads):
    # Stabilize the fixture email so auth cannot serialize requests on the user row.
    assert api_client.get("/v1/me", headers=bearer("fixture-token")).status_code == 200
    barrier = Barrier(2)
    locked, release = Event(), Event()

    def pause_after_deck_lock(connection, cursor, statement, parameters, context, many):
        if "FROM learning_decks" in statement and "FOR UPDATE" in statement:
            locked.set()
            assert release.wait(timeout=10)

    def submit(payload):
        barrier.wait(timeout=10)
        return api_client.post(
            f"/v1/decks/{FIXTURE_DECK_ID}/cards/bulk",
            json=payload,
            headers=bearer("fixture-token"),
        )

    app_engine = api_client.app.state.database_engine
    event.listen(app_engine, "after_cursor_execute", pause_after_deck_lock)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(submit, payload) for payload in payloads]
            try:
                assert locked.wait(timeout=5)
                wait_for_database_lock(engine, deck_select=True)
            finally:
                release.set()
            return [future.result(timeout=10) for future in futures]
    finally:
        event.remove(app_engine, "after_cursor_execute", pause_after_deck_lock)


def test_bulk_exact_replay_after_archive_and_mixed_new_selection_rejected(
    api_client, migrated_database_engine
):
    payload = bulk_payload("first", "second")
    payload["cards"][0]["idempotency_key"] = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    payload["cards"][1]["idempotency_key"] = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    path = f"/v1/decks/{FIXTURE_DECK_ID}/cards/bulk"
    created = api_client.post(path, json=payload, headers=bearer("fixture-token"))
    assert created.status_code == 201
    assert (
        api_client.delete(
            f"/v1/decks/{FIXTURE_DECK_ID}", headers=bearer("fixture-token")
        ).status_code
        == 204
    )
    before = counts(migrated_database_engine)
    replay = api_client.post(path, json=payload, headers=bearer("fixture-token"))
    assert replay.status_code == 201
    for original, repeated in zip(
        created.json()["cards"], replay.json()["cards"], strict=True
    ):
        assert repeated["idempotency_key"] == original["idempotency_key"]
        assert {
            key: value for key, value in repeated["card"].items() if key != "deck"
        } == {key: value for key, value in original["card"].items() if key != "deck"}
        assert repeated["card"]["deck"]["archived_at"] is not None
    payload["cards"].extend(bulk_payload("new")["cards"])
    payload["cards"][-1]["idempotency_key"] = "ffffffff-ffff-4fff-8fff-ffffffffffff"
    rejected = api_client.post(path, json=payload, headers=bearer("fixture-token"))
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "deck_archived"
    assert counts(migrated_database_engine) == before


def test_bulk_key_cannot_replay_a_card_into_another_deck_or_owner(
    api_client, migrated_database_engine
):
    payload = bulk_payload("shared-key")
    path = f"/v1/decks/{FIXTURE_DECK_ID}/cards/bulk"
    created = api_client.post(path, json=payload, headers=bearer("fixture-token"))
    assert created.status_code == 201
    own_deck = api_client.post(
        "/v1/decks",
        json={"title": "Other", "target_language": "en", "explanation_language": "en"},
        headers=create_headers("fixture-token"),
    )
    assert own_deck.status_code == 201
    before = counts(migrated_database_engine)
    cross_deck = api_client.post(
        f"/v1/decks/{own_deck.json()['id']}/cards/bulk",
        json=payload,
        headers=bearer("fixture-token"),
    )
    foreign_owner = api_client.post(
        path, json=payload, headers=bearer("attacker-token")
    )
    assert cross_deck.status_code == 409
    assert cross_deck.json()["error"]["code"] == "idempotency_key_reused"
    assert foreign_owner.status_code == 404
    assert counts(migrated_database_engine) == before


def wait_for_database_lock(engine, *, deck_select=False):
    deadline = monotonic() + 5
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        while monotonic() < deadline:
            blocked = connection.execute(
                text(
                    """
                    SELECT count(*) FROM pg_stat_activity
                    WHERE datname = current_database() AND wait_event_type = 'Lock'
                      AND (NOT :deck_select OR (
                        query LIKE '%FROM learning_decks%' AND query LIKE '%FOR UPDATE%'
                      ))
                    """
                ),
                {"deck_select": deck_select},
            ).scalar_one()
            if blocked:
                return
            sleep(0.01)
    pytest.fail("Expected a concurrent operation waiting for the deck lock")


@pytest.mark.parametrize("archive_first", [True, False])
def test_bulk_and_archive_serialize_on_the_deck(
    api_client, migrated_database_engine, archive_first
):
    engine = migrated_database_engine
    before = counts(engine)
    locked, release = Event(), Event()

    def pause_bulk_after_lock(connection, cursor, statement, parameters, context, many):
        if "FROM learning_decks" in statement and "FOR UPDATE" in statement:
            locked.set()
            assert release.wait(timeout=10)

    def create():
        return api_client.post(
            f"/v1/decks/{FIXTURE_DECK_ID}/cards/bulk",
            json=bulk_payload("one", "two"),
            headers=bearer("fixture-token"),
        )

    def archive():
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE learning_decks SET archived_at = CURRENT_TIMESTAMP WHERE id = :id"
                ),
                {"id": FIXTURE_DECK_ID},
            )
            locked.set()
            if archive_first:
                assert release.wait(timeout=10)

    app_engine = api_client.app.state.database_engine
    if not archive_first:
        event.listen(app_engine, "after_cursor_execute", pause_bulk_after_lock)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(archive if archive_first else create)
            try:
                assert locked.wait(timeout=5)
                second = executor.submit(create if archive_first else archive)
                wait_for_database_lock(engine)
            finally:
                release.set()
            response = (second if archive_first else first).result(timeout=10)
            (first if archive_first else second).result(timeout=10)
    finally:
        if not archive_first:
            event.remove(app_engine, "after_cursor_execute", pause_bulk_after_lock)
    assert response.status_code == (409 if archive_first else 201)
    if archive_first:
        assert response.json()["error"]["code"] == "deck_archived"
        assert counts(engine) == before
    else:
        assert counts(engine) == (before[0] + 2, before[1] + 2, before[2])


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
