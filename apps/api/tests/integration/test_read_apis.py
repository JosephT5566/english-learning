"""HTTP and PostgreSQL contract tests for Issue #9 read APIs."""

import os
from collections.abc import Iterator
from datetime import datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.auth import VerifiedGoogleIdentity
from app.main import create_app
from tests.integration.test_multilingual_domain_fixture import (
    load_multilingual_fixture,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1",
        reason="set RUN_POSTGRES_INTEGRATION_TESTS=1 to run PostgreSQL integration tests",
    ),
]

ENGLISH_DECK_ID = "10000000-0000-0000-0000-000000000001"
JAPANESE_DECK_ID = "10000000-0000-0000-0000-000000000002"
ENGLISH_CARD_ID = "20000000-0000-0000-0000-000000000001"
JAPANESE_CARD_ID = "20000000-0000-0000-0000-000000000002"
CORE_TAG_ID = "30000000-0000-0000-0000-000000000001"


class FixtureTokenVerifier:
    def verify(self, _token: str) -> VerifiedGoogleIdentity:
        return VerifiedGoogleIdentity(
            subject="fixture-google-subject",
            email="fixture.user@example.test",
        )


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
        client.app.state.token_verifier = FixtureTokenVerifier()
        client.headers["Authorization"] = "Bearer fixture-token"
        yield client


def test_deck_list_and_detail_share_one_contract_for_both_languages(
    api_client: TestClient,
) -> None:
    response = api_client.get("/v1/decks", params={"status": "all"})

    assert response.status_code == 200
    body = response.json()
    assert body["next_cursor"] is None
    assert [item["target_language"] for item in body["items"]] == ["ja", "en"]
    assert (
        set(body["items"][0])
        == set(body["items"][1])
        == {
            "id",
            "title",
            "target_language",
            "explanation_language",
            "archived_at",
            "version",
            "created_at",
            "updated_at",
        }
    )

    detail = api_client.get(f"/v1/decks/{ENGLISH_DECK_ID}")
    assert detail.status_code == 200
    assert detail.json()["title"] == "English fixture deck"


def test_card_language_and_tag_filters_use_the_same_summary_contract(
    api_client: TestClient,
) -> None:
    english = api_client.get(
        "/v1/cards",
        params={"target_language": "en", "tag_id": CORE_TAG_ID},
    )
    japanese = api_client.get(
        "/v1/cards",
        params={"target_language": "ja", "tag_id": CORE_TAG_ID},
    )

    assert english.status_code == japanese.status_code == 200
    english_item = english.json()["items"][0]
    japanese_item = japanese.json()["items"][0]
    assert english_item["id"] == ENGLISH_CARD_ID
    assert japanese_item["id"] == JAPANESE_CARD_ID
    assert set(english_item) == set(japanese_item)
    assert english_item["deck"]["target_language"] == "en"
    assert japanese_item["deck"]["target_language"] == "ja"


@pytest.mark.parametrize(
    ("card_id", "expected_language", "expected_specific_field"),
    [
        (ENGLISH_CARD_ID, "en", ("pronunciation", "/ˌser.ənˈdɪp.ə.ti/")),
        (JAPANESE_CARD_ID, "ja", ("reading", "べんきょう")),
    ],
)
def test_card_detail_returns_complete_multilingual_content(
    api_client: TestClient,
    card_id: str,
    expected_language: str,
    expected_specific_field: tuple[str, str],
) -> None:
    response = api_client.get(f"/v1/cards/{card_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["deck"]["target_language"] == expected_language
    assert body[expected_specific_field[0]] == expected_specific_field[1]
    assert body["review_state"]["version"] > 0
    assert [tag["display_name"] for tag in body["tags"]] == sorted(
        tag["display_name"] for tag in body["tags"]
    )


def test_management_cursor_has_no_duplicates_or_skips_in_stable_dataset(
    api_client: TestClient,
) -> None:
    first = api_client.get("/v1/cards", params={"status": "all", "limit": 1})
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["next_cursor"] is not None

    second = api_client.get(
        "/v1/cards",
        params={
            "status": "all",
            "limit": 1,
            "cursor": first_body["next_cursor"],
        },
    )
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["next_cursor"] is None
    ids = [first_body["items"][0]["id"], second_body["items"][0]["id"]]
    assert ids == [JAPANESE_CARD_ID, ENGLISH_CARD_ID]
    assert len(ids) == len(set(ids)) == 2


def test_due_reads_are_ordered_and_cursor_paginated_without_mutation(
    api_client: TestClient,
    migrated_database_engine: Engine,
) -> None:
    with migrated_database_engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO learning_cards (
                    id, deck_id, owner_id, term, meaning, created_at, updated_at
                )
                SELECT
                    fixture.id, CAST(:deck_id AS UUID), users.id,
                    fixture.term, fixture.meaning,
                    TIMESTAMPTZ '2026-09-01 01:00:00+00',
                    TIMESTAMPTZ '2026-09-01 01:00:00+00'
                FROM users
                CROSS JOIN (VALUES
                    (UUID '20000000-0000-0000-0000-000000000003', 'alpha', '甲'),
                    (UUID '20000000-0000-0000-0000-000000000004', 'beta', '乙')
                ) AS fixture(id, term, meaning)
                WHERE users.google_subject = 'fixture-google-subject'
                """
            ),
            {"deck_id": ENGLISH_DECK_ID},
        )
        connection.execute(
            text(
                """
                INSERT INTO review_states (
                    card_id, owner_id, review_stage, ease_factor, interval_days,
                    last_reviewed_at, next_review_at, version
                )
                SELECT
                    c.id, c.owner_id, 1, 2.50, 0,
                    TIMESTAMPTZ '2026-09-01 00:00:00+00',
                    CASE c.id
                        WHEN UUID '20000000-0000-0000-0000-000000000003'
                        THEN TIMESTAMPTZ '2026-09-01 00:00:00+00'
                        ELSE TIMESTAMPTZ '2026-09-02 00:00:00+00'
                    END,
                    1
                FROM learning_cards AS c
                WHERE c.id IN (
                    UUID '20000000-0000-0000-0000-000000000003',
                    UUID '20000000-0000-0000-0000-000000000004'
                )
                """
            )
        )

    ids: list[str] = []
    due_times: list[str] = []
    cursor = None
    while True:
        params = {"target_language": "en", "limit": 1}
        if cursor is not None:
            params["cursor"] = cursor
        response = api_client.get("/v1/reviews/due", params=params)
        assert response.status_code == 200
        body = response.json()
        ids.extend(item["id"] for item in body["items"])
        due_times.extend(
            item["review_state"]["next_review_at"] for item in body["items"]
        )
        cursor = body["next_cursor"]
        if cursor is None:
            break

    assert ids == [
        "20000000-0000-0000-0000-000000000003",
        "20000000-0000-0000-0000-000000000004",
        ENGLISH_CARD_ID,
    ]
    assert len(ids) == len(set(ids)) == 3
    assert due_times == sorted(due_times)


def test_empty_collections_are_successful(api_client: TestClient) -> None:
    decks = api_client.get("/v1/decks", params={"status": "archived"})
    cards = api_client.get("/v1/cards", params={"status": "archived"})

    assert decks.status_code == cards.status_code == 200
    assert decks.json() == cards.json() == {"items": [], "next_cursor": None}


@pytest.mark.parametrize(
    ("path", "params", "expected_status", "expected_code"),
    [
        ("/v1/decks", {"cursor": "not-base64"}, 400, "invalid_cursor"),
        ("/v1/decks", {"cursor": "x" * 2049}, 400, "invalid_cursor"),
        ("/v1/cards", {"unknown": "value"}, 400, "unsupported_filter"),
        (
            f"/v1/cards/{ENGLISH_CARD_ID}",
            {"unknown": "value"},
            400,
            "unsupported_filter",
        ),
        (
            "/v1/cards",
            {"target_language": "fr"},
            422,
            "validation_failed",
        ),
        (
            "/v1/reviews/due",
            {"target_language": "en", "deck_id": [ENGLISH_DECK_ID, ENGLISH_DECK_ID]},
            422,
            "validation_failed",
        ),
    ],
)
def test_invalid_cursors_and_filters_use_stable_client_errors(
    api_client: TestClient,
    path: str,
    params: dict[str, object],
    expected_status: int,
    expected_code: str,
) -> None:
    response = api_client.get(path, params=params)

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code
    assert UUID(response.json()["error"]["request_id"])


def test_cursor_is_rejected_when_query_shape_changes(api_client: TestClient) -> None:
    first = api_client.get("/v1/decks", params={"status": "all", "limit": 1})
    cursor = first.json()["next_cursor"]

    changed = api_client.get(
        "/v1/decks",
        params={"status": "all", "target_language": "en", "limit": 1, "cursor": cursor},
    )

    assert changed.status_code == 400
    assert changed.json()["error"]["code"] == "invalid_cursor"


@pytest.mark.parametrize(
    "path",
    [
        "/v1/decks/90000000-0000-0000-0000-000000000001",
        "/v1/cards/90000000-0000-0000-0000-000000000001",
    ],
)
def test_missing_details_return_non_disclosing_not_found(
    api_client: TestClient,
    path: str,
) -> None:
    response = api_client.get(path)

    assert response.status_code == 404
    assert response.json()["error"]["code"] in {"deck_not_found", "card_not_found"}
    assert "owner" not in response.text


def test_due_scope_rejects_wrong_language_deck(api_client: TestClient) -> None:
    response = api_client.get(
        "/v1/reviews/due",
        params={"target_language": "en", "deck_id": JAPANESE_DECK_ID},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_response_timestamps_are_rfc3339(api_client: TestClient) -> None:
    response = api_client.get(f"/v1/cards/{ENGLISH_CARD_ID}")

    assert datetime.fromisoformat(response.json()["updated_at"]).tzinfo is not None
