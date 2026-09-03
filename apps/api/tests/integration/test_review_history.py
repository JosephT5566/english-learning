"""PostgreSQL constraint tests for review batches and retained history rows."""

import os
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, MetaData, Table, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.base import Executable

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1",
        reason="set RUN_POSTGRES_INTEGRATION_TESTS=1 to run PostgreSQL integration tests",
    ),
]


@pytest.fixture
def domain_tables(migrated_database_engine: Engine) -> Mapping[str, Table]:
    """Reflect the review-history tables and their card parent."""

    metadata = MetaData()
    metadata.reflect(
        bind=migrated_database_engine,
        only=["learning_cards", "review_batches", "review_events"],
    )
    return metadata.tables


def insert_user(engine: Engine) -> int:
    """Insert a unique valid user."""

    with engine.begin() as connection:
        return connection.execute(
            text(
                """
                INSERT INTO users (google_subject, normalized_email)
                VALUES (:subject, :email)
                RETURNING id
                """
            ),
            {
                "subject": f"google-{uuid4()}",
                "email": f"{uuid4()}@example.test",
            },
        ).scalar_one()


def insert_owned_card(engine: Engine, *, owner_id: int) -> UUID:
    """Insert a deck and confirmed card owned by one user."""

    with engine.begin() as connection:
        deck_id = connection.execute(
            text(
                """
                INSERT INTO learning_decks (
                    owner_id, title, target_language, explanation_language
                )
                VALUES (:owner_id, :title, 'en', 'zh-TW')
                RETURNING id
                """
            ),
            {"owner_id": owner_id, "title": f"Deck {uuid4()}"},
        ).scalar_one()
        return connection.execute(
            text(
                """
                INSERT INTO learning_cards (deck_id, owner_id, term, meaning)
                VALUES (:deck_id, :owner_id, :term, 'meaning')
                RETURNING id
                """
            ),
            {
                "deck_id": deck_id,
                "owner_id": owner_id,
                "term": f"term-{uuid4()}",
            },
        ).scalar_one()


def valid_batch_values(*, owner_id: int, **overrides: Any) -> dict[str, Any]:
    """Return a valid review-batch value mapping with optional overrides."""

    values = {
        "owner_id": owner_id,
        "idempotency_key": uuid4(),
        "request_hash": f"sha256:{uuid4().hex}",
        "reviewed_at": datetime(2026, 9, 3, 12, tzinfo=UTC),
        "algorithm_version": "srs-v1",
        "item_count": 1,
    }
    values.update(overrides)
    return values


def insert_batch(
    engine: Engine,
    batches: Table,
    values: Mapping[str, Any],
) -> UUID:
    """Insert a review batch and return its generated UUID."""

    with engine.begin() as connection:
        return connection.execute(
            batches.insert().values(**values).returning(batches.c.id)
        ).scalar_one()


def valid_event_values(
    *,
    batch_id: UUID,
    card_id: UUID,
    owner_id: int,
    **overrides: Any,
) -> dict[str, Any]:
    """Return a valid before-and-after review-event mapping."""

    reviewed_at = datetime(2026, 9, 3, 12, tzinfo=UTC)
    values = {
        "batch_id": batch_id,
        "owner_id": owner_id,
        "card_id": card_id,
        "decision": "yes",
        "quality": 5,
        "previous_review_stage": 1,
        "resulting_review_stage": 2,
        "previous_ease_factor": Decimal("2.50"),
        "resulting_ease_factor": Decimal("2.50"),
        "previous_interval_days": 0,
        "resulting_interval_days": 1,
        "previous_last_reviewed_at": None,
        "resulting_last_reviewed_at": reviewed_at,
        "previous_next_review_at": datetime(2026, 9, 3, tzinfo=UTC),
        "resulting_next_review_at": datetime(2026, 9, 4, tzinfo=UTC),
        "previous_version": 1,
        "resulting_version": 2,
        "algorithm_version": "srs-v1",
        "reviewed_at": reviewed_at,
    }
    values.update(overrides)
    return values


def assert_integrity_error(
    engine: Engine,
    statement: Executable,
    *,
    sqlstate: str,
    constraint_name: str | None = None,
    column_name: str | None = None,
) -> None:
    """Assert PostgreSQL rejects a statement for the expected invariant."""

    with pytest.raises(IntegrityError) as caught, engine.begin() as connection:
        connection.execute(statement)

    assert caught.value.orig.sqlstate == sqlstate
    if constraint_name is not None:
        assert caught.value.orig.diag.constraint_name == constraint_name
    if column_name is not None:
        assert caught.value.orig.diag.column_name == column_name


def test_review_batch_and_event_preserve_a_valid_transition(
    migrated_database_engine: Engine,
    domain_tables: Mapping[str, Table],
) -> None:
    batches = domain_tables["review_batches"]
    events = domain_tables["review_events"]
    owner_id = insert_user(migrated_database_engine)
    card_id = insert_owned_card(migrated_database_engine, owner_id=owner_id)
    batch_id = insert_batch(
        migrated_database_engine,
        batches,
        valid_batch_values(owner_id=owner_id),
    )

    with migrated_database_engine.begin() as connection:
        event = connection.execute(
            events.insert()
            .values(
                **valid_event_values(
                    batch_id=batch_id,
                    card_id=card_id,
                    owner_id=owner_id,
                )
            )
            .returning(events)
        ).one()

    assert event.id > 0
    assert event.batch_id == batch_id
    assert event.card_id == card_id
    assert event.previous_review_stage == 1
    assert event.resulting_review_stage == 2
    assert event.previous_version == 1
    assert event.resulting_version == 2
    assert event.resulting_last_reviewed_at == event.reviewed_at
    assert event.created_at is not None


def test_review_batch_requires_explicit_command_metadata(
    migrated_database_engine: Engine,
    domain_tables: Mapping[str, Table],
) -> None:
    batches = domain_tables["review_batches"]
    owner_id = insert_user(migrated_database_engine)

    for column_name in (
        "owner_id",
        "idempotency_key",
        "request_hash",
        "reviewed_at",
        "algorithm_version",
        "item_count",
    ):
        values = valid_batch_values(owner_id=owner_id)
        values.pop(column_name)
        assert_integrity_error(
            migrated_database_engine,
            batches.insert().values(**values),
            sqlstate="23502",
            column_name=column_name,
        )


def test_review_batch_requires_an_existing_owner(
    migrated_database_engine: Engine,
    domain_tables: Mapping[str, Table],
) -> None:
    batches = domain_tables["review_batches"]
    owner_id = insert_user(migrated_database_engine)

    assert_integrity_error(
        migrated_database_engine,
        batches.insert().values(**valid_batch_values(owner_id=owner_id + 1_000_000)),
        sqlstate="23503",
        constraint_name="fk_review_batches_owner_id_users",
    )


def test_idempotency_key_is_unique_per_owner(
    migrated_database_engine: Engine,
    domain_tables: Mapping[str, Table],
) -> None:
    batches = domain_tables["review_batches"]
    first_owner_id = insert_user(migrated_database_engine)
    second_owner_id = insert_user(migrated_database_engine)
    idempotency_key = uuid4()
    first_values = valid_batch_values(
        owner_id=first_owner_id,
        idempotency_key=idempotency_key,
    )
    insert_batch(migrated_database_engine, batches, first_values)

    assert_integrity_error(
        migrated_database_engine,
        batches.insert().values(**first_values),
        sqlstate="23505",
        constraint_name="uq_review_batches_owner_id_idempotency_key",
    )

    insert_batch(
        migrated_database_engine,
        batches,
        valid_batch_values(
            owner_id=second_owner_id,
            idempotency_key=idempotency_key,
        ),
    )


@pytest.mark.parametrize(
    ("overrides", "constraint_name"),
    [
        ({"request_hash": "   "}, "ck_review_batches_request_hash_nonblank"),
        (
            {"algorithm_version": "   "},
            "ck_review_batches_algorithm_version_nonblank",
        ),
        ({"item_count": 0}, "ck_review_batches_item_count_range"),
        ({"item_count": 11}, "ck_review_batches_item_count_range"),
    ],
)
def test_invalid_review_batch_metadata_is_rejected(
    migrated_database_engine: Engine,
    domain_tables: Mapping[str, Table],
    overrides: Mapping[str, Any],
    constraint_name: str,
) -> None:
    batches = domain_tables["review_batches"]
    owner_id = insert_user(migrated_database_engine)

    assert_integrity_error(
        migrated_database_engine,
        batches.insert().values(**valid_batch_values(owner_id=owner_id, **overrides)),
        sqlstate="23514",
        constraint_name=constraint_name,
    )


def test_review_event_rejects_cross_owner_batch_and_card_pairs(
    migrated_database_engine: Engine,
    domain_tables: Mapping[str, Table],
) -> None:
    batches = domain_tables["review_batches"]
    events = domain_tables["review_events"]
    first_owner_id = insert_user(migrated_database_engine)
    second_owner_id = insert_user(migrated_database_engine)
    first_card_id = insert_owned_card(
        migrated_database_engine,
        owner_id=first_owner_id,
    )
    second_batch_id = insert_batch(
        migrated_database_engine,
        batches,
        valid_batch_values(owner_id=second_owner_id),
    )

    assert_integrity_error(
        migrated_database_engine,
        events.insert().values(
            **valid_event_values(
                batch_id=second_batch_id,
                card_id=first_card_id,
                owner_id=first_owner_id,
            )
        ),
        sqlstate="23503",
        constraint_name="fk_review_events_batch_id_owner_id_review_batches",
    )
    assert_integrity_error(
        migrated_database_engine,
        events.insert().values(
            **valid_event_values(
                batch_id=second_batch_id,
                card_id=first_card_id,
                owner_id=second_owner_id,
            )
        ),
        sqlstate="23503",
        constraint_name="fk_review_events_card_id_owner_id_learning_cards",
    )


def test_review_event_requires_a_complete_transition_snapshot(
    migrated_database_engine: Engine,
    domain_tables: Mapping[str, Table],
) -> None:
    batches = domain_tables["review_batches"]
    events = domain_tables["review_events"]
    owner_id = insert_user(migrated_database_engine)
    card_id = insert_owned_card(migrated_database_engine, owner_id=owner_id)
    batch_id = insert_batch(
        migrated_database_engine,
        batches,
        valid_batch_values(owner_id=owner_id),
    )

    for column_name in (
        "batch_id",
        "owner_id",
        "card_id",
        "decision",
        "quality",
        "previous_review_stage",
        "resulting_review_stage",
        "previous_ease_factor",
        "resulting_ease_factor",
        "previous_interval_days",
        "resulting_interval_days",
        "resulting_last_reviewed_at",
        "previous_next_review_at",
        "resulting_next_review_at",
        "previous_version",
        "resulting_version",
        "algorithm_version",
        "reviewed_at",
    ):
        values = valid_event_values(
            batch_id=batch_id,
            card_id=card_id,
            owner_id=owner_id,
        )
        values.pop(column_name)
        assert_integrity_error(
            migrated_database_engine,
            events.insert().values(**values),
            sqlstate="23502",
            column_name=column_name,
        )


def test_one_batch_cannot_review_the_same_card_twice(
    migrated_database_engine: Engine,
    domain_tables: Mapping[str, Table],
) -> None:
    batches = domain_tables["review_batches"]
    events = domain_tables["review_events"]
    owner_id = insert_user(migrated_database_engine)
    card_id = insert_owned_card(migrated_database_engine, owner_id=owner_id)
    batch_id = insert_batch(
        migrated_database_engine,
        batches,
        valid_batch_values(owner_id=owner_id),
    )
    values = valid_event_values(
        batch_id=batch_id,
        card_id=card_id,
        owner_id=owner_id,
    )
    with migrated_database_engine.begin() as connection:
        connection.execute(events.insert().values(**values))

    assert_integrity_error(
        migrated_database_engine,
        events.insert().values(**values),
        sqlstate="23505",
        constraint_name="uq_review_events_batch_id_card_id",
    )


def test_invalid_review_event_transitions_are_rejected(
    migrated_database_engine: Engine,
    domain_tables: Mapping[str, Table],
) -> None:
    batches = domain_tables["review_batches"]
    events = domain_tables["review_events"]
    owner_id = insert_user(migrated_database_engine)
    card_id = insert_owned_card(migrated_database_engine, owner_id=owner_id)
    batch_id = insert_batch(
        migrated_database_engine,
        batches,
        valid_batch_values(owner_id=owner_id),
    )
    reviewed_at = datetime(2026, 9, 3, 12, tzinfo=UTC)
    invalid_cases: list[tuple[Mapping[str, Any], str | None]] = [
        ({"decision": "maybe"}, None),
        ({"quality": 1}, None),
        ({"decision": "yes", "quality": 0}, "ck_review_events_decision_quality_match"),
        ({"previous_review_stage": 0}, "ck_review_events_review_stage_ranges"),
        ({"resulting_review_stage": 6}, "ck_review_events_review_stage_ranges"),
        (
            {"previous_ease_factor": Decimal("1.29")},
            "ck_review_events_ease_factor_ranges",
        ),
        (
            {"resulting_ease_factor": Decimal("2.51")},
            "ck_review_events_ease_factor_ranges",
        ),
        ({"previous_interval_days": -1}, "ck_review_events_interval_days_nonnegative"),
        ({"resulting_interval_days": -1}, "ck_review_events_interval_days_nonnegative"),
        (
            {"previous_version": 0, "resulting_version": 1},
            "ck_review_events_version_transition",
        ),
        ({"resulting_version": 1}, "ck_review_events_version_transition"),
        ({"algorithm_version": "   "}, "ck_review_events_algorithm_version_nonblank"),
        (
            {
                "previous_last_reviewed_at": reviewed_at,
                "previous_next_review_at": reviewed_at - timedelta(seconds=1),
            },
            "ck_review_events_previous_schedule_ordered",
        ),
        (
            {
                "previous_last_reviewed_at": reviewed_at + timedelta(hours=1),
                "previous_next_review_at": reviewed_at + timedelta(hours=2),
            },
            "ck_review_events_review_time_monotonic",
        ),
        (
            {"resulting_last_reviewed_at": reviewed_at + timedelta(seconds=1)},
            "ck_review_events_resulting_last_review_matches_review",
        ),
        (
            {"resulting_next_review_at": reviewed_at - timedelta(seconds=1)},
            "ck_review_events_resulting_schedule_ordered",
        ),
    ]

    for overrides, constraint_name in invalid_cases:
        assert_integrity_error(
            migrated_database_engine,
            events.insert().values(
                **valid_event_values(
                    batch_id=batch_id,
                    card_id=card_id,
                    owner_id=owner_id,
                    **overrides,
                )
            ),
            sqlstate="23514",
            constraint_name=constraint_name,
        )


def test_review_history_restricts_physical_batch_and_card_deletion(
    migrated_database_engine: Engine,
    domain_tables: Mapping[str, Table],
) -> None:
    batches = domain_tables["review_batches"]
    cards = domain_tables["learning_cards"]
    events = domain_tables["review_events"]
    owner_id = insert_user(migrated_database_engine)
    card_id = insert_owned_card(migrated_database_engine, owner_id=owner_id)
    batch_id = insert_batch(
        migrated_database_engine,
        batches,
        valid_batch_values(owner_id=owner_id),
    )
    with migrated_database_engine.begin() as connection:
        connection.execute(
            events.insert().values(
                **valid_event_values(
                    batch_id=batch_id,
                    card_id=card_id,
                    owner_id=owner_id,
                )
            )
        )

    assert_integrity_error(
        migrated_database_engine,
        batches.delete().where(batches.c.id == batch_id),
        sqlstate="23503",
        constraint_name="fk_review_events_batch_id_owner_id_review_batches",
    )
    assert_integrity_error(
        migrated_database_engine,
        cards.delete().where(cards.c.id == card_id),
        sqlstate="23503",
        constraint_name="fk_review_events_card_id_owner_id_learning_cards",
    )


def test_review_event_indexes_match_history_and_replay_patterns(
    migrated_database_engine: Engine,
    domain_tables: Mapping[str, Table],
) -> None:
    del domain_tables
    with migrated_database_engine.connect() as connection:
        rows = connection.execute(
            select(text("indexname, indexdef"))
            .select_from(text("pg_indexes"))
            .where(text("tablename = 'review_events'"))
        ).all()
    index_definitions = {row.indexname: row.indexdef for row in rows}

    assert (
        "(owner_id, reviewed_at DESC, id DESC)"
        in index_definitions["ix_review_events_owner_reviewed_id"]
    )
    assert (
        "(card_id, reviewed_at DESC, id DESC)"
        in index_definitions["ix_review_events_card_reviewed_id"]
    )
    assert "(batch_id, id)" in index_definitions["ix_review_events_batch_id_id"]
