"""PostgreSQL verification for the complete synthetic multilingual fixture."""

import os
from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1",
        reason="set RUN_POSTGRES_INTEGRATION_TESTS=1 to run PostgreSQL integration tests",
    ),
]

FIXTURE_PATH = (
    Path(__file__).parents[1] / "fixtures" / "multilingual_learning_domain.sql"
)


def load_multilingual_fixture(engine: Engine) -> None:
    """Load the complete synthetic fixture in one transaction."""

    fixture_sql = FIXTURE_PATH.read_text(encoding="utf-8")
    with engine.begin() as connection:
        connection.exec_driver_sql(fixture_sql)


def test_fixture_uses_one_schema_for_complete_english_and_japanese_records(
    migrated_database_engine: Engine,
) -> None:
    load_multilingual_fixture(migrated_database_engine)

    with migrated_database_engine.connect() as connection:
        counts = connection.execute(
            text(
                """
                SELECT
                    (SELECT count(*) FROM users),
                    (SELECT count(*) FROM learning_decks),
                    (SELECT count(*) FROM learning_cards),
                    (SELECT count(*) FROM tags),
                    (SELECT count(*) FROM learning_card_tags),
                    (SELECT count(*) FROM review_states),
                    (SELECT count(*) FROM review_batches),
                    (SELECT count(*) FROM review_events)
                """
            )
        ).one()
        cards = connection.execute(
            text(
                """
                SELECT
                    d.target_language,
                    c.term,
                    c.reading,
                    c.pronunciation,
                    c.romanization,
                    c.example_sentence
                FROM learning_cards AS c
                JOIN learning_decks AS d
                  ON (d.id, d.owner_id) = (c.deck_id, c.owner_id)
                ORDER BY d.target_language
                """
            )
        ).all()
        tag_links = connection.execute(
            text(
                """
                SELECT d.target_language, t.normalized_name
                FROM learning_card_tags AS ct
                JOIN learning_cards AS c
                  ON (c.id, c.owner_id) = (ct.card_id, ct.owner_id)
                JOIN learning_decks AS d ON d.id = c.deck_id
                JOIN tags AS t
                  ON (t.id, t.owner_id) = (ct.tag_id, ct.owner_id)
                ORDER BY d.target_language, t.normalized_name
                """
            )
        ).all()
        transitions = connection.execute(
            text(
                """
                SELECT
                    d.target_language,
                    b.item_count,
                    e.decision,
                    e.resulting_review_stage,
                    s.review_stage,
                    e.resulting_ease_factor,
                    s.ease_factor,
                    e.resulting_interval_days,
                    s.interval_days,
                    e.resulting_last_reviewed_at,
                    s.last_reviewed_at,
                    e.resulting_next_review_at,
                    s.next_review_at,
                    e.resulting_version,
                    s.version
                FROM review_events AS e
                JOIN review_batches AS b
                  ON (b.id, b.owner_id) = (e.batch_id, e.owner_id)
                JOIN learning_cards AS c
                  ON (c.id, c.owner_id) = (e.card_id, e.owner_id)
                JOIN learning_decks AS d ON d.id = c.deck_id
                JOIN review_states AS s
                  ON (s.card_id, s.owner_id) = (e.card_id, e.owner_id)
                ORDER BY d.target_language
                """
            )
        ).all()

    assert tuple(counts) == (1, 2, 2, 2, 3, 2, 1, 2)
    assert cards == [
        (
            "en",
            "serendipity",
            None,
            "/ˌser.ənˈdɪp.ə.ti/",
            None,
            "We met by pure serendipity.",
        ),
        (
            "ja",
            "勉強",
            "べんきょう",
            None,
            "benkyou",
            "毎日日本語を勉強します。",
        ),
    ]
    assert tag_links == [
        ("en", "core"),
        ("en", "noun"),
        ("ja", "core"),
    ]
    assert len(transitions) == 2
    assert all(row.item_count == len(transitions) for row in transitions)
    for row in transitions:
        assert row.resulting_review_stage == row.review_stage
        assert row.resulting_ease_factor == row.ease_factor
        assert row.resulting_interval_days == row.interval_days
        assert row.resulting_last_reviewed_at == row.last_reviewed_at
        assert row.resulting_next_review_at == row.next_review_at
        assert row.resulting_version == row.version


def test_fixture_rejects_accidental_duplicate_loading(
    migrated_database_engine: Engine,
) -> None:
    load_multilingual_fixture(migrated_database_engine)

    with pytest.raises(IntegrityError) as caught:
        load_multilingual_fixture(migrated_database_engine)

    assert caught.value.orig.sqlstate == "23505"
    assert caught.value.orig.diag.constraint_name == "uq_users_google_subject"
