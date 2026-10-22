"""Disposable PostgreSQL evidence for anonymous publication and isolation."""

import json
import os
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, Uuid, bindparam, create_engine, event, text

from app.auth import VerifiedGoogleIdentity
from app.config import Settings
from app.database import create_database_session_factory
from app.main import create_app
from app.public_admission import PublicAdmission
from app.public_reviews import PUBLIC_CARDS_QUERY, PUBLIC_REVIEW_PATH
from tests.integration.test_multilingual_domain_fixture import load_multilingual_fixture

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1",
        reason="requires disposable PostgreSQL",
    ),
]
EN = "10000000-0000-0000-0000-000000000001"
JA = "10000000-0000-0000-0000-000000000002"
OTHER = "10000000-0000-0000-0000-000000000003"
PATH = PUBLIC_REVIEW_PATH


def configure(client: TestClient, ids: tuple[str, ...] = (EN, JA)) -> None:
    client.app.state.settings = Settings(
        public_review_deck_ids=tuple(UUID(value) for value in ids),
        public_review_burst=100,
        public_review_global_burst=100,
    )
    client.app.state.public_admission = PublicAdmission(client.app.state.settings)


def snapshot(engine: Engine) -> dict[str, list[dict]]:
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


def test_public_exact_fields_archive_policy_dynamic_membership_and_no_writes(
    migrated_database_engine: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    engine = migrated_database_engine
    load_multilingual_fixture(engine)
    private_note = "private-note-must-never-be-published"
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE learning_cards SET note = :note"), {"note": private_note}
        )
        connection.execute(
            text(
                "INSERT INTO users (google_subject, normalized_email) VALUES ('other', 'other@example.test')"
            )
        )
        connection.execute(
            text("""INSERT INTO learning_decks (id, owner_id, title, target_language, explanation_language)
            SELECT :id, id, 'Other public owner', 'en', 'en' FROM users WHERE google_subject = 'other'"""),
            {"id": UUID(OTHER)},
        )
        connection.execute(
            text("""INSERT INTO learning_cards (id, deck_id, owner_id, term, meaning)
            SELECT :id, d.id, d.owner_id, 'other owner', 'public' FROM learning_decks d WHERE d.id = :deck"""),
            {"id": uuid4(), "deck": UUID(OTHER)},
        )
    before = snapshot(engine)
    with TestClient(create_app()) as client:
        verifier = Mock()
        client.app.state.token_verifier = verifier
        configure(client, (EN, JA, OTHER))
        response = client.get(PATH)
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 3
        assert {item["target_language"] for item in items} == {"en", "ja"}
        for item in items:
            assert set(item) == {
                "id",
                "target_language",
                "term",
                "meaning",
                "pronunciation",
                "reading",
                "romanization",
                "part_of_speech",
                "part_of_speech_detail",
                "target_language_definition",
                "example_sentence",
                "example_translation",
                "synonyms",
                "antonyms",
            }
        assert private_note not in response.text
        assert snapshot(engine) == before
        verifier.verify.assert_not_called()
        assert "review_submission_completed" not in capsys.readouterr().out

        configure(client, ())
        assert client.get(PATH).json() == {"items": []}
        configure(client, (str(uuid4()),))
        assert client.get(PATH).json() == {"items": []}
        configure(client, (EN,))
        assert len(client.get(PATH).json()["items"]) == 1
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE learning_cards SET meaning = 'new public edit' WHERE deck_id = :id"
                ),
                {"id": UUID(EN)},
            )
        assert client.get(PATH).json()["items"][0]["meaning"] == "new public edit"
        with engine.begin() as connection:
            connection.execute(
                text("""INSERT INTO learning_cards (id, deck_id, owner_id, term, meaning)
                    SELECT :id, d.id, d.owner_id, 'later addition', 'public later'
                    FROM learning_decks d WHERE d.id = :deck"""),
                {"id": uuid4(), "deck": UUID(EN)},
            )
        assert {item["term"] for item in client.get(PATH).json()["items"]} == {
            "serendipity",
            "later addition",
        }
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE learning_cards SET archived_at = now() WHERE deck_id = :id"
                ),
                {"id": UUID(EN)},
            )
        assert client.get(PATH).json() == {"items": []}
        configure(client, (JA,))
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE learning_decks SET archived_at = now() WHERE id = :id"),
                {"id": UUID(JA)},
            )
        assert client.get(PATH).json() == {"items": []}


def test_random_batch_uses_all_eligible_candidates_but_at_most_ten_distinct(
    migrated_database_engine: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    engine = migrated_database_engine
    load_multilingual_fixture(engine)
    with engine.begin() as connection:
        connection.execute(
            text("""INSERT INTO learning_cards (id, deck_id, owner_id, term, meaning)
            SELECT gen_random_uuid(), d.id, d.owner_id, 'candidate ' || n, 'meaning'
            FROM learning_decks d CROSS JOIN generate_series(1, 30) n WHERE d.id = :id"""),
            {"id": UUID(EN)},
        )
    with TestClient(create_app()) as client:
        configure(client)
        for _ in range(3):
            response = client.get(PATH)
            assert response.status_code == 200
            items = response.json()["items"]
            assert len(items) == len({item["id"] for item in items}) == 10
        # Explain the exact production statement, not a substitute sampling algorithm.
        with engine.connect() as connection:
            plan = connection.execute(
                text(
                    "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + PUBLIC_CARDS_QUERY.text
                ).bindparams(bindparam("deck_ids", expanding=True, type_=Uuid)),
                {"deck_ids": (UUID(EN), UUID(JA))},
            ).scalar_one()
            candidates = connection.execute(
                text(
                    "SELECT count(*) FROM learning_cards c JOIN learning_decks d ON d.id = c.deck_id AND d.owner_id = c.owner_id WHERE d.id IN (:en, :ja) AND d.archived_at IS NULL AND c.archived_at IS NULL"
                ),
                {"en": UUID(EN), "ja": UUID(JA)},
            ).scalar_one()
        assert candidates == 32
        assert plan[0]["Plan"]["Actual Rows"] == 10
        print(
            "PUBLIC_QUERY_EXPLAIN "
            + json.dumps({"candidate_count": candidates, "plan": plan})
        )
        sort = plan[0]["Plan"]["Plans"][0]
        assert sort["Node Type"] == "Sort"
        assert sort["Plans"][0]["Actual Rows"] == candidates


def test_readonly_timeout_cleanup_and_private_write_same_pool(
    migrated_database_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import public_reviews

    engine = migrated_database_engine
    load_multilingual_fixture(engine)
    pooled = create_engine(engine.url, pool_size=1, max_overflow=0)
    statements: list[str] = []
    event.listen(
        pooled,
        "before_cursor_execute",
        lambda _conn, _cur, statement, _params, _ctx, _many: statements.append(
            statement
        ),
    )
    try:
        with TestClient(create_app()) as client:
            configure(client)
            client.app.state.database_session_factory = create_database_session_factory(
                pooled
            )
            client.app.state.token_verifier = Mock()
            response = client.get(PATH)
            assert response.status_code == 200
            assert statements[0] == "SET TRANSACTION READ ONLY"
            assert client.app.state.public_admission._in_flight == 0
            before = snapshot(engine)
            monkeypatch.setattr(
                public_reviews,
                "PUBLIC_CARDS_QUERY",
                text("UPDATE learning_cards SET meaning = 'forbidden' RETURNING id"),
            )
            denied = client.get(PATH)
            assert denied.status_code == 503
            assert snapshot(engine) == before
            assert client.app.state.public_admission._in_flight == 0
            client.app.state.settings = client.app.state.settings.model_copy(
                update={"public_review_query_timeout_ms": 10}
            )
            monkeypatch.setattr(
                public_reviews, "PUBLIC_CARDS_QUERY", text("SELECT pg_sleep(0.2)")
            )
            timeout = client.get(PATH)
            assert timeout.status_code == 503
            assert timeout.json()["error"]["code"] == "database_unavailable"
            assert client.app.state.public_admission._in_flight == 0
            monkeypatch.setattr(
                public_reviews, "PUBLIC_CARDS_QUERY", PUBLIC_CARDS_QUERY
            )
            assert client.get(PATH).status_code == 200
            client.app.state.token_verifier.verify.return_value = (
                VerifiedGoogleIdentity(
                    subject="fixture-google-subject", email="fixture@example.test"
                )
            )
            sources_before = {
                key: bucket.tokens
                for key, bucket in client.app.state.public_admission._sources.items()
            }
            private = client.post(
                "/v1/decks",
                json={
                    "title": "Private write",
                    "target_language": "en",
                    "explanation_language": "en",
                },
                headers={
                    "Authorization": "Bearer fixture",
                    "Idempotency-Key": str(uuid4()),
                },
            )
            assert private.status_code == 201
            assert sources_before == {
                key: bucket.tokens
                for key, bucket in client.app.state.public_admission._sources.items()
            }
            for path in ["/v1/decks", "/v1/cards", "/v1/reviews/due"]:
                assert client.get(path).status_code == 401
            assert client.post("/v1/decks", json={}).status_code == 401
            assert client.post("/v1/reviews", json={}).status_code == 401
    finally:
        pooled.dispose()
