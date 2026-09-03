"""Representative PostgreSQL query-plan checks for Issue #8 access patterns."""

import os
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.engine import Connection

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1",
        reason="set RUN_POSTGRES_INTEGRATION_TESTS=1 to run PostgreSQL integration tests",
    ),
]

OWNER_COUNT = 100
DECKS_PER_OWNER = 20
CARDS_PER_DECK = 20


def iter_plan_nodes(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield every node in PostgreSQL's nested JSON plan."""

    yield node
    for child in node.get("Plans", []):
        yield from iter_plan_nodes(child)


def explain(
    connection: Connection,
    query: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """Run the real query and return the root of its JSON execution plan."""

    result = connection.execute(
        text(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}"),
        parameters,
    ).scalar_one()
    return result[0]["Plan"]


def used_indexes(plan: dict[str, Any]) -> set[str]:
    """Collect index names used anywhere in a PostgreSQL plan tree."""

    return {
        node["Index Name"] for node in iter_plan_nodes(plan) if "Index Name" in node
    }


def seed_representative_dataset(engine: Engine) -> dict[str, Any]:
    """Create a deterministic, selective dataset for planner inspection."""

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO users (google_subject, normalized_email)
                SELECT
                    'plan-user-' || user_number,
                    'plan-user-' || user_number || '@example.test'
                FROM generate_series(1, :owner_count) AS user_number
                """
            ),
            {"owner_count": OWNER_COUNT},
        )
        connection.execute(
            text(
                """
                INSERT INTO learning_decks (
                    id,
                    owner_id,
                    title,
                    target_language,
                    explanation_language,
                    archived_at,
                    created_at,
                    updated_at
                )
                SELECT
                    md5('plan-deck-' || deck_number)::uuid,
                    ((deck_number - 1) / CAST(:decks_per_owner AS BIGINT)) + 1,
                    'Plan deck ' || deck_number,
                    CASE WHEN deck_number % 2 = 0 THEN 'en' ELSE 'ja' END,
                    'zh-TW',
                    CASE
                        WHEN deck_number % 10 = 0
                        THEN TIMESTAMPTZ '2026-01-02 00:00:00+00'
                    END,
                    TIMESTAMPTZ '2026-01-01 00:00:00+00',
                    TIMESTAMPTZ '2026-01-01 00:00:00+00'
                FROM generate_series(
                    1,
                    CAST(:owner_count AS BIGINT)
                        * CAST(:decks_per_owner AS BIGINT)
                ) AS deck_number
                """
            ),
            {
                "owner_count": OWNER_COUNT,
                "decks_per_owner": DECKS_PER_OWNER,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO learning_cards (
                    id,
                    deck_id,
                    owner_id,
                    term,
                    meaning,
                    archived_at,
                    created_at,
                    updated_at
                )
                SELECT
                    md5('plan-card-' || card_number)::uuid,
                    md5(
                        'plan-deck-'
                        || (
                            ((card_number - 1) / CAST(:cards_per_deck AS BIGINT))
                            + 1
                        )
                    )::uuid,
                    (
                        (
                            (
                                (card_number - 1)
                                / CAST(:cards_per_deck AS BIGINT)
                            ) + 1 - 1
                        ) / CAST(:decks_per_owner AS BIGINT)
                    ) + 1,
                    'Plan term ' || card_number,
                    'Plan meaning ' || card_number,
                    CASE
                        WHEN card_number % 25 = 0
                        THEN TIMESTAMPTZ '2026-02-01 00:00:00+00'
                    END,
                    TIMESTAMPTZ '2026-01-01 00:00:00+00'
                        + card_number * INTERVAL '1 second',
                    TIMESTAMPTZ '2026-01-01 00:00:00+00'
                        + card_number * INTERVAL '1 second'
                FROM generate_series(
                    1,
                    CAST(:owner_count AS BIGINT)
                        * CAST(:decks_per_owner AS BIGINT)
                        * CAST(:cards_per_deck AS BIGINT)
                ) AS card_number
                """
            ),
            {
                "owner_count": OWNER_COUNT,
                "decks_per_owner": DECKS_PER_OWNER,
                "cards_per_deck": CARDS_PER_DECK,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO tags (
                    id,
                    owner_id,
                    display_name,
                    normalized_name
                )
                SELECT
                    md5('plan-tag-' || owner_id)::uuid,
                    owner_id,
                    'Plan tag ' || owner_id,
                    'plan-tag-' || owner_id
                FROM generate_series(1, :owner_count) AS owner_id
                """
            ),
            {"owner_count": OWNER_COUNT},
        )
        connection.execute(
            text(
                """
                INSERT INTO learning_card_tags (owner_id, card_id, tag_id)
                SELECT
                    owner_id,
                    id,
                    md5('plan-tag-' || owner_id)::uuid
                FROM learning_cards
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO review_states (
                    card_id,
                    owner_id,
                    review_stage,
                    ease_factor,
                    interval_days,
                    last_reviewed_at,
                    next_review_at,
                    version
                )
                SELECT
                    id,
                    owner_id,
                    2,
                    2.50,
                    1,
                    TIMESTAMPTZ '2026-03-01 00:00:00+00',
                    TIMESTAMPTZ '2026-03-01 00:00:00+00'
                        + (row_number() OVER (ORDER BY id) % 30) * INTERVAL '1 day',
                    2
                FROM learning_cards
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO review_batches (
                    id,
                    owner_id,
                    idempotency_key,
                    request_hash,
                    reviewed_at,
                    algorithm_version,
                    item_count
                )
                SELECT
                    md5('plan-batch-' || batch_number)::uuid,
                    (
                        (
                            ((batch_number - 1) / 2)
                            / CAST(:decks_per_owner AS BIGINT)
                        )
                    ) + 1,
                    md5('plan-idempotency-' || batch_number)::uuid,
                    'sha256:plan-batch-' || batch_number,
                    TIMESTAMPTZ '2026-04-01 00:00:00+00'
                        + batch_number * INTERVAL '1 minute',
                    'srs-v1',
                    10
                FROM generate_series(
                    1,
                    CAST(:owner_count AS BIGINT)
                        * CAST(:decks_per_owner AS BIGINT) * 2
                ) AS batch_number
                """
            ),
            {
                "owner_count": OWNER_COUNT,
                "decks_per_owner": DECKS_PER_OWNER,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO review_events (
                    batch_id,
                    owner_id,
                    card_id,
                    decision,
                    quality,
                    previous_review_stage,
                    resulting_review_stage,
                    previous_ease_factor,
                    resulting_ease_factor,
                    previous_interval_days,
                    resulting_interval_days,
                    previous_last_reviewed_at,
                    resulting_last_reviewed_at,
                    previous_next_review_at,
                    resulting_next_review_at,
                    previous_version,
                    resulting_version,
                    algorithm_version,
                    reviewed_at
                )
                SELECT
                    md5('plan-batch-' || batch_number)::uuid,
                    owner_number,
                    md5('plan-card-' || card_number)::uuid,
                    'yes',
                    5,
                    1,
                    2,
                    2.40,
                    2.50,
                    0,
                    1,
                    NULL,
                    reviewed_at,
                    reviewed_at,
                    reviewed_at + INTERVAL '1 day',
                    round_number + 1,
                    round_number + 2,
                    'srs-v1',
                    reviewed_at
                FROM (
                    SELECT
                        owner_number,
                        round_number,
                        (owner_number - 1) * 400 + card_ordinal AS card_number,
                        (owner_number - 1) * 40
                            + round_number * 4
                            + group_number
                            + 1 AS batch_number,
                        TIMESTAMPTZ '2026-04-01 00:00:00+00'
                            + (
                                (owner_number - 1) * 40
                                + round_number * 4
                                + group_number
                                + 1
                            ) * INTERVAL '1 minute' AS reviewed_at
                    FROM (
                        SELECT
                            owner_number,
                            (event_number - 1) / 40 AS round_number,
                            ((event_number - 1) % 40) + 1 AS card_ordinal,
                            ((event_number - 1) % 40) / 10 AS group_number
                        FROM generate_series(
                            1,
                            CAST(:owner_count AS BIGINT)
                        ) AS owner_number
                        CROSS JOIN generate_series(1, 400) AS event_number
                    ) AS event_distribution
                ) AS numbered_events
                """
            ),
            {"owner_count": OWNER_COUNT},
        )

    with engine.begin() as connection:
        connection.exec_driver_sql(
            "ANALYZE users, learning_decks, learning_cards, tags, "
            "learning_card_tags, review_states, review_batches, review_events"
        )

    return {
        "owner_id": 1,
        "deck_id": "35724a5c-f8ef-1135-3567-2db28c9c780e",
        "tag_id": "0d863d5d-126a-a758-7d40-2cb78fce4aae",
        "card_id": "eefa3327-cc9e-cc6c-047e-fe000790e496",
        "batch_id": "0a82c1f6-bf53-6708-dd91-7d6d66052e60",
    }


def test_named_access_patterns_use_their_deliberate_indexes(
    migrated_database_engine: Engine,
) -> None:
    identifiers = seed_representative_dataset(migrated_database_engine)

    access_patterns = {
        "active cards in a deck": (
            """
            SELECT id, term, meaning, created_at
            FROM learning_cards
            WHERE deck_id = :deck_id AND archived_at IS NULL
            ORDER BY created_at DESC, id DESC
            LIMIT 20
            """,
            {"deck_id": identifiers["deck_id"]},
            "ix_learning_cards_active_deck_created_id",
        ),
        "decks by owner and language": (
            """
            SELECT id, title
            FROM learning_decks
            WHERE owner_id = :owner_id
              AND target_language = 'en'
              AND archived_at IS NULL
            ORDER BY id
            """,
            {"owner_id": identifiers["owner_id"]},
            "ix_learning_decks_owner_language_archive",
        ),
        "cards by tag": (
            """
            SELECT card_id
            FROM learning_card_tags
            WHERE tag_id = :tag_id
            ORDER BY card_id
            LIMIT 20
            """,
            {"tag_id": identifiers["tag_id"]},
            "ix_learning_card_tags_tag_id_card_id",
        ),
        "due cards for an owner": (
            """
            SELECT s.card_id, s.next_review_at
            FROM review_states AS s
            JOIN learning_cards AS c
              ON (c.id, c.owner_id) = (s.card_id, s.owner_id)
            JOIN learning_decks AS d
              ON (d.id, d.owner_id) = (c.deck_id, c.owner_id)
            WHERE s.owner_id = :owner_id
              AND s.next_review_at <= TIMESTAMPTZ '2026-03-15 00:00:00+00'
              AND c.archived_at IS NULL
              AND d.archived_at IS NULL
            ORDER BY s.next_review_at, s.card_id
            LIMIT 20
            """,
            {"owner_id": identifiers["owner_id"]},
            "ix_review_states_owner_next_review_card",
        ),
        "owner review history": (
            """
            SELECT id, card_id, decision, reviewed_at
            FROM review_events
            WHERE owner_id = :owner_id
            ORDER BY reviewed_at DESC, id DESC
            LIMIT 20
            """,
            {"owner_id": identifiers["owner_id"]},
            "ix_review_events_owner_reviewed_id",
        ),
        "card review history": (
            """
            SELECT id, decision, reviewed_at
            FROM review_events
            WHERE card_id = :card_id
            ORDER BY reviewed_at DESC, id DESC
            LIMIT 20
            """,
            {"card_id": identifiers["card_id"]},
            "ix_review_events_card_reviewed_id",
        ),
        "batch response reconstruction": (
            """
            SELECT id, card_id, decision
            FROM review_events
            WHERE batch_id = :batch_id
            ORDER BY id
            """,
            {"batch_id": identifiers["batch_id"]},
            "ix_review_events_batch_id_id",
        ),
    }

    with migrated_database_engine.connect() as connection:
        cardinalities = connection.execute(
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
                    (SELECT count(*) FROM review_events),
                    (
                        SELECT count(*)
                        FROM review_events
                        WHERE owner_id = :owner_id
                    ),
                    (
                        SELECT count(*)
                        FROM review_events
                        WHERE card_id = :card_id
                    ),
                    (
                        SELECT count(*)
                        FROM review_events
                        WHERE batch_id = :batch_id
                    )
                """
            ),
            identifiers,
        ).one()
        observed = {
            name: used_indexes(explain(connection, query, parameters))
            for name, (query, parameters, _) in access_patterns.items()
        }

    assert tuple(cardinalities) == (
        100,
        2_000,
        40_000,
        100,
        40_000,
        40_000,
        4_000,
        40_000,
        400,
        10,
        10,
    )
    for name, (_, _, expected_index) in access_patterns.items():
        assert expected_index in observed[name], (
            f"{name!r} did not use {expected_index!r}; "
            f"observed indexes: {sorted(observed[name])}"
        )
