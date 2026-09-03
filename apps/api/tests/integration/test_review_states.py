"""PostgreSQL constraint tests for current review scheduling state."""

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
    """Reflect cards and review states from the migrated database."""

    metadata = MetaData()
    metadata.reflect(
        bind=migrated_database_engine,
        only=["learning_cards", "review_states"],
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


def valid_state_values(
    *,
    card_id: UUID,
    owner_id: int,
    **overrides: Any,
) -> dict[str, Any]:
    """Return a valid initial review-state mapping with optional overrides."""

    values = {
        "card_id": card_id,
        "owner_id": owner_id,
        "review_stage": 1,
        "ease_factor": Decimal("2.50"),
        "interval_days": 0,
        "last_reviewed_at": None,
        "next_review_at": datetime(2026, 9, 3, tzinfo=UTC),
        "version": 1,
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


def test_initial_review_state_requires_explicit_schedule_and_uses_audit_default(
    migrated_database_engine: Engine,
    domain_tables: Mapping[str, Table],
) -> None:
    states = domain_tables["review_states"]
    owner_id = insert_user(migrated_database_engine)
    card_id = insert_owned_card(migrated_database_engine, owner_id=owner_id)
    values = valid_state_values(card_id=card_id, owner_id=owner_id)

    with migrated_database_engine.begin() as connection:
        row = connection.execute(
            states.insert().values(**values).returning(states)
        ).one()

    assert row.card_id == card_id
    assert row.owner_id == owner_id
    assert row.review_stage == 1
    assert row.ease_factor == Decimal("2.50")
    assert row.interval_days == 0
    assert row.last_reviewed_at is None
    assert row.next_review_at == values["next_review_at"]
    assert row.version == 1
    assert row.updated_at is not None


@pytest.mark.parametrize(
    "missing_column",
    [
        "review_stage",
        "ease_factor",
        "interval_days",
        "next_review_at",
        "version",
    ],
)
def test_review_state_rejects_missing_scheduling_values(
    migrated_database_engine: Engine,
    domain_tables: Mapping[str, Table],
    missing_column: str,
) -> None:
    states = domain_tables["review_states"]
    owner_id = insert_user(migrated_database_engine)
    card_id = insert_owned_card(migrated_database_engine, owner_id=owner_id)
    values = valid_state_values(card_id=card_id, owner_id=owner_id)
    values.pop(missing_column)

    assert_integrity_error(
        migrated_database_engine,
        states.insert().values(**values),
        sqlstate="23502",
        column_name=missing_column,
    )


def test_review_state_has_at_most_one_row_per_card(
    migrated_database_engine: Engine,
    domain_tables: Mapping[str, Table],
) -> None:
    states = domain_tables["review_states"]
    owner_id = insert_user(migrated_database_engine)
    card_id = insert_owned_card(migrated_database_engine, owner_id=owner_id)
    values = valid_state_values(card_id=card_id, owner_id=owner_id)
    with migrated_database_engine.begin() as connection:
        connection.execute(states.insert().values(**values))

    assert_integrity_error(
        migrated_database_engine,
        states.insert().values(**values),
        sqlstate="23505",
        constraint_name="pk_review_states",
    )


def test_review_state_requires_the_cards_owner(
    migrated_database_engine: Engine,
    domain_tables: Mapping[str, Table],
) -> None:
    states = domain_tables["review_states"]
    card_owner_id = insert_user(migrated_database_engine)
    other_owner_id = insert_user(migrated_database_engine)
    card_id = insert_owned_card(migrated_database_engine, owner_id=card_owner_id)

    assert_integrity_error(
        migrated_database_engine,
        states.insert().values(
            **valid_state_values(card_id=card_id, owner_id=other_owner_id)
        ),
        sqlstate="23503",
        constraint_name="fk_review_states_card_id_owner_id_learning_cards",
    )


@pytest.mark.parametrize(
    ("overrides", "constraint_name"),
    [
        ({"review_stage": 0}, "ck_review_states_review_stage_range"),
        ({"review_stage": 6}, "ck_review_states_review_stage_range"),
        ({"ease_factor": Decimal("1.29")}, "ck_review_states_ease_factor_range"),
        ({"ease_factor": Decimal("2.51")}, "ck_review_states_ease_factor_range"),
        ({"interval_days": -1}, "ck_review_states_interval_days_nonnegative"),
        ({"version": 0}, "ck_review_states_version_positive"),
    ],
)
def test_invalid_review_scheduling_ranges_are_rejected(
    migrated_database_engine: Engine,
    domain_tables: Mapping[str, Table],
    overrides: Mapping[str, Any],
    constraint_name: str,
) -> None:
    states = domain_tables["review_states"]
    owner_id = insert_user(migrated_database_engine)
    card_id = insert_owned_card(migrated_database_engine, owner_id=owner_id)

    assert_integrity_error(
        migrated_database_engine,
        states.insert().values(
            **valid_state_values(
                card_id=card_id,
                owner_id=owner_id,
                **overrides,
            )
        ),
        sqlstate="23514",
        constraint_name=constraint_name,
    )


def test_next_review_cannot_precede_last_review(
    migrated_database_engine: Engine,
    domain_tables: Mapping[str, Table],
) -> None:
    states = domain_tables["review_states"]
    owner_id = insert_user(migrated_database_engine)
    card_id = insert_owned_card(migrated_database_engine, owner_id=owner_id)
    last_reviewed_at = datetime(2026, 9, 3, 12, tzinfo=UTC)

    assert_integrity_error(
        migrated_database_engine,
        states.insert().values(
            **valid_state_values(
                card_id=card_id,
                owner_id=owner_id,
                last_reviewed_at=last_reviewed_at,
                next_review_at=last_reviewed_at - timedelta(seconds=1),
            )
        ),
        sqlstate="23514",
        constraint_name="ck_review_states_next_review_not_before_last_review",
    )


def test_physical_card_deletion_is_restricted_while_review_state_exists(
    migrated_database_engine: Engine,
    domain_tables: Mapping[str, Table],
) -> None:
    cards = domain_tables["learning_cards"]
    states = domain_tables["review_states"]
    owner_id = insert_user(migrated_database_engine)
    card_id = insert_owned_card(migrated_database_engine, owner_id=owner_id)
    with migrated_database_engine.begin() as connection:
        connection.execute(
            states.insert().values(
                **valid_state_values(card_id=card_id, owner_id=owner_id)
            )
        )

    assert_integrity_error(
        migrated_database_engine,
        cards.delete().where(cards.c.id == card_id),
        sqlstate="23503",
        constraint_name="fk_review_states_card_id_owner_id_learning_cards",
    )


def test_due_review_index_matches_owner_due_order_pattern(
    migrated_database_engine: Engine,
    domain_tables: Mapping[str, Table],
) -> None:
    del domain_tables
    with migrated_database_engine.connect() as connection:
        index_definition = connection.execute(
            select(text("indexdef"))
            .select_from(text("pg_indexes"))
            .where(text("indexname = 'ix_review_states_owner_next_review_card'"))
        ).scalar_one()

    assert "(owner_id, next_review_at, card_id)" in index_definition
