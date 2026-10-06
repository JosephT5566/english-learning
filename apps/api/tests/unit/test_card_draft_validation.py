"""JSON authoring validation at the public HTTP boundary, without card writes."""

from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.auth import AuthenticatedUser, current_user
from app.config import DEFAULT_DATABASE_URL
from app.database import database_session
from app.main import create_app

DECK_ID = "10000000-0000-0000-0000-000000000001"
PATH = f"/v1/decks/{DECK_ID}/card-drafts/validate"


class ReadOnlySession:
    def __init__(self, archived: bool = False, missing: bool = False):
        self.archived = archived
        self.missing = missing
        self.lookups = 0

    def execute(self, statement, parameters):
        assert str(statement).startswith("SELECT archived_at FROM learning_decks")
        assert parameters == {"id": UUID(DECK_ID), "owner_id": 7}
        self.lookups += 1
        return self

    def one_or_none(self):
        return (
            None
            if self.missing
            else SimpleNamespace(archived_at="archived" if self.archived else None)
        )


@pytest.fixture(autouse=True)
def test_settings(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", DEFAULT_DATABASE_URL)


@pytest.fixture
def client():
    session = ReadOnlySession()
    app = create_app()
    app.dependency_overrides[current_user] = lambda: AuthenticatedUser(
        id=7, google_subject="test-subject", email="user@example.test"
    )
    app.dependency_overrides[database_session] = lambda: session
    with TestClient(app) as client:
        yield client, session


def test_valid_drafts_are_normalized_without_writes(client):
    http, session = client
    response = http.post(
        PATH,
        json={
            "cards": [
                {"term": " learn ", "meaning": " study "},
                {
                    "term": "学ぶ",
                    "meaning": "學習",
                    "reading": "まなぶ",
                    "learned_on": "2026-10-06",
                },
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["cards"][0]["term"] == "learn"
    assert response.json()["cards"][0]["synonyms"] == []
    assert session.lookups == 1


@pytest.mark.parametrize(
    "payload, path",
    [
        ([], ["body"]),
        ({"cards": []}, ["body", "cards"]),
        ({"cards": [{"term": "x", "meaning": "y"}] * 21}, ["body", "cards"]),
        ({"cards": [{"term": "x"}]}, ["body", "cards", 0, "meaning"]),
        (
            {"cards": [{"term": " ", "meaning": "private-marker"}]},
            ["body", "cards", 0, "term"],
        ),
        ({"cards": [{"term": 12, "meaning": "y"}]}, ["body", "cards", 0, "term"]),
        (
            {"cards": [{"term": "x", "meaning": "y", "owner_id": 42}]},
            ["body", "cards", 0, "owner_id"],
        ),
        (
            {"cards": [{"term": "x", "meaning": "y", "synonyms": "no"}]},
            ["body", "cards", 0, "synonyms"],
        ),
        (
            {"cards": [{"term": "x", "meaning": "y", "antonyms": None}]},
            ["body", "cards", 0, "antonyms"],
        ),
        (
            {"cards": [{"term": "x", "meaning": "y", "part_of_speech": "unknown"}]},
            ["body", "cards", 0, "part_of_speech"],
        ),
        (
            {"cards": [{"term": "x", "meaning": "y", "learned_on": "2026-99-99"}]},
            ["body", "cards", 0, "learned_on"],
        ),
        (
            {
                "cards": [
                    {
                        "term": "x",
                        "meaning": "y",
                        "example_translation": "private-marker",
                    }
                ]
            },
            ["body", "cards", 0],
        ),
        (
            {"cards": [{"term": "x", "meaning": "y", "part_of_speech": "other"}]},
            ["body", "cards", 0],
        ),
        (
            {"cards": [{"term": "x", "meaning": "y"}], "target_language": "ja"},
            ["body", "target_language"],
        ),
    ],
)
def test_invalid_json_has_safe_indexed_errors(client, payload, path):
    http, session = client
    response = http.post(PATH, json=payload)
    assert response.status_code == 422
    assert path in [
        field["path"] for field in response.json()["error"]["details"]["fields"]
    ]
    assert "private-marker" not in response.text
    assert session.lookups == 0


def test_malformed_and_oversized_json(client):
    http, session = client
    assert (
        http.post(
            PATH, content="{", headers={"Content-Type": "application/json"}
        ).status_code
        == 422
    )
    response = http.post(
        PATH,
        content=" " * 100_000 + '{"cards":[{"term":"x","meaning":"y"}]}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert session.lookups == 0


@pytest.mark.parametrize(
    "missing, archived, status", [(True, False, 404), (False, True, 409)]
)
def test_deck_must_be_owned_and_active(client, missing, archived, status):
    http, session = client
    session.missing = missing
    session.archived = archived
    assert (
        http.post(PATH, json={"cards": [{"term": "x", "meaning": "y"}]}).status_code
        == status
    )


def test_authentication_is_required():
    with TestClient(create_app()) as http:
        assert (
            http.post(PATH, json={"cards": [{"term": "x", "meaning": "y"}]}).status_code
            == 401
        )


@pytest.mark.parametrize(
    "cards",
    [
        [],
        [
            {
                "idempotency_key": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "fields": {"term": "x", "meaning": "y"},
            }
        ]
        * 21,
        [{"idempotency_key": "bad", "fields": {"term": "x", "meaning": "y"}}],
        [
            {
                "idempotency_key": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "fields": {"term": "x", "meaning": "y", "deck_id": DECK_ID},
            }
        ],
        [
            {
                "idempotency_key": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "fields": {"term": "x", "meaning": "y"},
            }
        ]
        * 2,
    ],
)
def test_bulk_invalid_envelope_never_accesses_database(client, cards):
    http, session = client
    response = http.post(f"/v1/decks/{DECK_ID}/cards/bulk", json={"cards": cards})
    assert response.status_code == 422
    assert session.lookups == 0


def test_bulk_oversized_body_never_accesses_database(client):
    import json

    http, session = client
    payload = {
        "cards": [
            {
                "idempotency_key": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "fields": {"term": "x", "meaning": "y"},
            }
        ]
    }
    response = http.post(
        f"/v1/decks/{DECK_ID}/cards/bulk",
        content=" " * 100_000 + json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert session.lookups == 0
