"""HTTP/PostgreSQL tests for atomic and idempotent review submissions."""

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from typing import ClassVar
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

import app.reviews as reviews_module
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

ENGLISH_CARD_ID = "20000000-0000-0000-0000-000000000001"
JAPANESE_CARD_ID = "20000000-0000-0000-0000-000000000002"
REVIEWED_AT = datetime(2026, 9, 4, 16, 30, tzinfo=UTC)


class FixtureTokenVerifier:
    identities: ClassVar[dict[str, VerifiedGoogleIdentity]] = {
        "fixture-token": VerifiedGoogleIdentity(
            "fixture-google-subject", "fixture@example.test"
        ),
        "other-token": VerifiedGoogleIdentity(
            "other-google-subject", "other@example.test"
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
    monkeypatch.setattr(reviews_module, "review_clock", lambda: REVIEWED_AT)
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        client.app.state.token_verifier = FixtureTokenVerifier()
        client.headers["Authorization"] = "Bearer fixture-token"
        yield client


def review_body(
    *,
    card_id: str = ENGLISH_CARD_ID,
    decision: str = "yes",
    expected_version: int = 2,
) -> dict[str, object]:
    return {
        "items": [
            {
                "card_id": card_id,
                "decision": decision,
                "expected_version": expected_version,
            }
        ]
    }


def post_review(
    client: TestClient,
    *,
    key: str,
    body: dict[str, object] | None = None,
    token: str = "fixture-token",
):
    return client.post(
        "/v1/reviews",
        json=body or review_body(),
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": key,
        },
    )


def review_counts(engine: Engine) -> tuple[int, int]:
    with engine.connect() as connection:
        return connection.execute(
            text(
                """
                SELECT
                    (SELECT count(*) FROM review_batches),
                    (SELECT count(*) FROM review_events)
                """
            )
        ).one()


def test_success_writes_one_event_and_matching_state_transition(
    api_client: TestClient,
    migrated_database_engine: Engine,
) -> None:
    response = post_review(api_client, key=str(uuid4()))

    assert response.status_code == 200
    body = response.json()
    assert body["reviewed_at"] == "2026-09-04T16:30:00Z"
    assert body["algorithm_version"] == "srs-v1"
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["card_id"] == ENGLISH_CARD_ID
    assert item["previous_state"]["version"] == 2
    assert item["resulting_state"] == {
        "review_stage": 3,
        "ease_factor": "2.50",
        "interval_days": 18,
        "last_reviewed_at": "2026-09-04T16:30:00Z",
        "next_review_at": "2026-09-22T16:00:00Z",
        "version": 3,
    }
    assert review_counts(migrated_database_engine) == (2, 3)

    with migrated_database_engine.connect() as connection:
        state_and_event = connection.execute(
            text(
                """
                SELECT
                    s.review_stage, s.ease_factor, s.interval_days,
                    s.last_reviewed_at, s.next_review_at, s.version,
                    e.resulting_review_stage, e.resulting_ease_factor,
                    e.resulting_interval_days, e.resulting_last_reviewed_at,
                    e.resulting_next_review_at, e.resulting_version
                FROM review_states AS s
                JOIN review_events AS e ON e.card_id = s.card_id
                WHERE s.card_id = :card_id
                ORDER BY e.id DESC
                LIMIT 1
                """
            ),
            {"card_id": ENGLISH_CARD_ID},
        ).one()
    assert state_and_event[:6] == state_and_event[6:]


def test_same_key_and_body_replays_exact_result_without_duplicate_effects(
    api_client: TestClient,
    migrated_database_engine: Engine,
) -> None:
    key = str(uuid4())
    first = post_review(api_client, key=key)
    replay = post_review(api_client, key=key)

    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert review_counts(migrated_database_engine) == (2, 3)


def test_multi_item_batch_preserves_request_order_on_commit_and_replay(
    api_client: TestClient,
    migrated_database_engine: Engine,
) -> None:
    key = str(uuid4())
    body = {
        "items": [
            {
                "card_id": JAPANESE_CARD_ID,
                "decision": "yes_a_bit",
                "expected_version": 4,
            },
            {
                "card_id": ENGLISH_CARD_ID,
                "decision": "no_a_bit",
                "expected_version": 2,
            },
        ]
    }

    first = post_review(api_client, key=key, body=body)
    replay = post_review(api_client, key=key, body=body)

    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert [item["card_id"] for item in first.json()["items"]] == [
        JAPANESE_CARD_ID,
        ENGLISH_CARD_ID,
    ]
    assert [item["resulting_state"]["version"] for item in first.json()["items"]] == [
        5,
        3,
    ]
    assert review_counts(migrated_database_engine) == (2, 4)


def test_same_key_with_different_content_is_rejected_without_new_effect(
    api_client: TestClient,
    migrated_database_engine: Engine,
) -> None:
    key = str(uuid4())
    first = post_review(api_client, key=key)
    conflict = post_review(
        api_client,
        key=key,
        body=review_body(decision="no"),
    )

    assert first.status_code == 200
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_key_reused"
    assert review_counts(migrated_database_engine) == (2, 3)


@pytest.mark.parametrize("key", [None, "not-a-uuid"])
def test_missing_or_malformed_idempotency_key_is_rejected(
    api_client: TestClient,
    key: str | None,
) -> None:
    headers = {}
    if key is not None:
        headers["Idempotency-Key"] = key
    response = api_client.post("/v1/reviews", json=review_body(), headers=headers)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_idempotency_key"


def test_duplicate_card_validation_writes_nothing(
    api_client: TestClient,
    migrated_database_engine: Engine,
) -> None:
    item = review_body()["items"][0]
    response = post_review(
        api_client,
        key=str(uuid4()),
        body={"items": [item, item]},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"
    assert review_counts(migrated_database_engine) == (1, 2)


def test_stale_item_rolls_back_entire_batch(
    api_client: TestClient,
    migrated_database_engine: Engine,
) -> None:
    response = post_review(
        api_client,
        key=str(uuid4()),
        body={
            "items": [
                {
                    "card_id": ENGLISH_CARD_ID,
                    "decision": "yes",
                    "expected_version": 2,
                },
                {
                    "card_id": JAPANESE_CARD_ID,
                    "decision": "yes",
                    "expected_version": 3,
                },
            ]
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "stale_review_state"
    assert response.json()["error"]["details"] == {
        "item_index": 1,
        "card_id": JAPANESE_CARD_ID,
        "expected_version": 3,
        "current_version": 4,
    }
    assert review_counts(migrated_database_engine) == (1, 2)


def test_other_users_card_and_archived_target_are_rejected_without_history(
    api_client: TestClient,
    migrated_database_engine: Engine,
) -> None:
    foreign = post_review(
        api_client,
        key=str(uuid4()),
        token="other-token",
    )
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "card_not_found"

    with migrated_database_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE learning_cards SET archived_at = CURRENT_TIMESTAMP WHERE id = :id"
            ),
            {"id": ENGLISH_CARD_ID},
        )
    inactive = post_review(api_client, key=str(uuid4()))

    assert inactive.status_code == 409
    assert inactive.json()["error"]["code"] == "review_target_inactive"
    assert review_counts(migrated_database_engine) == (1, 2)


def test_injected_failure_between_event_and_state_rolls_back_everything(
    api_client: TestClient,
    migrated_database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(_session: object) -> None:
        raise RuntimeError("injected after event insert")

    monkeypatch.setattr(reviews_module, "after_events_written", fail)
    response = post_review(api_client, key=str(uuid4()))

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert review_counts(migrated_database_engine) == (1, 2)
    with migrated_database_engine.connect() as connection:
        version = connection.execute(
            text("SELECT version FROM review_states WHERE card_id = :id"),
            {"id": ENGLISH_CARD_ID},
        ).scalar_one()
    assert version == 2


def test_concurrent_different_keys_produce_one_transition_and_one_stale_conflict(
    api_client: TestClient,
    migrated_database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del api_client  # Fixture establishes the migrated data and deterministic clock.
    keys = [str(uuid4()), str(uuid4())]
    start = Barrier(2)
    monkeypatch.setattr(reviews_module, "before_batch_insert", start.wait)
    first_app = create_app()
    second_app = create_app()
    first_app.openapi()
    second_app.openapi()
    with (
        TestClient(first_app, raise_server_exceptions=False) as first_client,
        TestClient(second_app, raise_server_exceptions=False) as second_client,
    ):
        first_client.app.state.token_verifier = FixtureTokenVerifier()
        second_client.app.state.token_verifier = FixtureTokenVerifier()
        clients = [first_client, second_client]
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(
                    lambda pair: post_review(pair[0], key=pair[1]),
                    zip(clients, keys, strict=True),
                )
            )

    assert sorted(response.status_code for response in responses) == [200, 409]
    assert [
        response.json()["error"]["code"]
        for response in responses
        if response.status_code == 409
    ] == ["stale_review_state"]
    assert review_counts(migrated_database_engine) == (2, 3)


def test_concurrent_same_key_replays_one_committed_result(
    api_client: TestClient,
    migrated_database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del api_client  # Fixture establishes the migrated data and deterministic clock.
    key = str(uuid4())
    start = Barrier(2)
    monkeypatch.setattr(reviews_module, "before_batch_insert", start.wait)
    first_app = create_app()
    second_app = create_app()
    first_app.openapi()
    second_app.openapi()
    with (
        TestClient(first_app, raise_server_exceptions=False) as first_client,
        TestClient(second_app, raise_server_exceptions=False) as second_client,
    ):
        first_client.app.state.token_verifier = FixtureTokenVerifier()
        second_client.app.state.token_verifier = FixtureTokenVerifier()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(
                    lambda client: post_review(client, key=key),
                    [first_client, second_client],
                )
            )

    assert [response.status_code for response in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    assert review_counts(migrated_database_engine) == (2, 3)
