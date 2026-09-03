"""PostgreSQL constraint tests for owned tags and card associations."""

import os
from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, MetaData, Table, func, select, text
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
def domain_tables(
    migrated_database_engine: Engine,
) -> Mapping[str, Table]:
    """Reflect the migrated tables used by tag constraint tests."""

    metadata = MetaData()
    metadata.reflect(
        bind=migrated_database_engine,
        only=["learning_cards", "learning_card_tags", "tags"],
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
    """Insert a deck and one confirmed card for an owner."""

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


def insert_tag(
    engine: Engine,
    tags: Table,
    *,
    owner_id: int,
    display_name: str = "Travel",
    normalized_name: str = "travel",
) -> UUID:
    """Insert an owned tag and return its generated UUID."""

    with engine.begin() as connection:
        return connection.execute(
            tags.insert()
            .values(
                owner_id=owner_id,
                display_name=display_name,
                normalized_name=normalized_name,
            )
            .returning(tags.c.id)
        ).scalar_one()


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


def test_tag_name_identity_is_unique_per_owner_but_not_global(
    migrated_database_engine: Engine,
    domain_tables: Mapping[str, Table],
) -> None:
    tags = domain_tables["tags"]
    first_owner_id = insert_user(migrated_database_engine)
    second_owner_id = insert_user(migrated_database_engine)
    insert_tag(migrated_database_engine, tags, owner_id=first_owner_id)
    insert_tag(migrated_database_engine, tags, owner_id=second_owner_id)

    assert_integrity_error(
        migrated_database_engine,
        tags.insert().values(
            owner_id=first_owner_id,
            display_name="TRAVEL",
            normalized_name="travel",
        ),
        sqlstate="23505",
        constraint_name="uq_tags_owner_id_normalized_name",
    )


@pytest.mark.parametrize(
    ("values", "sqlstate", "constraint_name", "column_name"),
    [
        ({"owner_id": None}, "23502", None, "owner_id"),
        (
            {"owner_id": 9_999_999},
            "23503",
            "fk_tags_owner_id_users",
            None,
        ),
        (
            {"display_name": "   "},
            "23514",
            "ck_tags_display_name_length",
            None,
        ),
        (
            {"normalized_name": "   "},
            "23514",
            "ck_tags_normalized_name_length",
            None,
        ),
        (
            {"version": 0},
            "23514",
            "ck_tags_version_positive",
            None,
        ),
        (
            {
                "created_at": text("CURRENT_TIMESTAMP"),
                "updated_at": text("CURRENT_TIMESTAMP - INTERVAL '1 second'"),
            },
            "23514",
            "ck_tags_timestamps_ordered",
            None,
        ),
    ],
)
def test_tag_content_and_owner_constraints_are_database_enforced(
    migrated_database_engine: Engine,
    domain_tables: Mapping[str, Table],
    values: Mapping[str, Any],
    sqlstate: str,
    constraint_name: str | None,
    column_name: str | None,
) -> None:
    tags = domain_tables["tags"]
    owner_id = insert_user(migrated_database_engine)
    tag_values = {
        "owner_id": owner_id,
        "display_name": "Travel",
        "normalized_name": f"travel-{uuid4()}",
    }
    tag_values.update(values)

    assert_integrity_error(
        migrated_database_engine,
        tags.insert().values(**tag_values),
        sqlstate=sqlstate,
        constraint_name=constraint_name,
        column_name=column_name,
    )


def test_owner_deletion_is_restricted_while_a_tag_exists(
    migrated_database_engine: Engine,
    domain_tables: Mapping[str, Table],
) -> None:
    tags = domain_tables["tags"]
    owner_id = insert_user(migrated_database_engine)
    insert_tag(migrated_database_engine, tags, owner_id=owner_id)

    assert_integrity_error(
        migrated_database_engine,
        text("DELETE FROM users WHERE id = :owner_id").bindparams(owner_id=owner_id),
        sqlstate="23503",
        constraint_name="fk_tags_owner_id_users",
    )


def test_card_tag_association_requires_one_shared_owner(
    migrated_database_engine: Engine,
    domain_tables: Mapping[str, Table],
) -> None:
    tags = domain_tables["tags"]
    associations = domain_tables["learning_card_tags"]
    first_owner_id = insert_user(migrated_database_engine)
    second_owner_id = insert_user(migrated_database_engine)
    first_card_id = insert_owned_card(
        migrated_database_engine,
        owner_id=first_owner_id,
    )
    first_tag_id = insert_tag(
        migrated_database_engine,
        tags,
        owner_id=first_owner_id,
    )
    second_tag_id = insert_tag(
        migrated_database_engine,
        tags,
        owner_id=second_owner_id,
    )
    with migrated_database_engine.begin() as connection:
        connection.execute(
            associations.insert().values(
                owner_id=first_owner_id,
                card_id=first_card_id,
                tag_id=first_tag_id,
            )
        )

    assert_integrity_error(
        migrated_database_engine,
        associations.insert().values(
            owner_id=first_owner_id,
            card_id=first_card_id,
            tag_id=second_tag_id,
        ),
        sqlstate="23503",
        constraint_name="fk_learning_card_tags_tag_id_owner_id_tags",
    )
    assert_integrity_error(
        migrated_database_engine,
        associations.insert().values(
            owner_id=second_owner_id,
            card_id=first_card_id,
            tag_id=second_tag_id,
        ),
        sqlstate="23503",
        constraint_name="fk_learning_card_tags_card_id_owner_id_learning_cards",
    )


def test_duplicate_card_tag_attachment_is_rejected(
    migrated_database_engine: Engine,
    domain_tables: Mapping[str, Table],
) -> None:
    tags = domain_tables["tags"]
    associations = domain_tables["learning_card_tags"]
    owner_id = insert_user(migrated_database_engine)
    card_id = insert_owned_card(migrated_database_engine, owner_id=owner_id)
    tag_id = insert_tag(migrated_database_engine, tags, owner_id=owner_id)
    values = {"owner_id": owner_id, "card_id": card_id, "tag_id": tag_id}
    with migrated_database_engine.begin() as connection:
        connection.execute(associations.insert().values(**values))

    assert_integrity_error(
        migrated_database_engine,
        associations.insert().values(**values),
        sqlstate="23505",
        constraint_name="pk_learning_card_tags",
    )


def test_tag_deletion_cascades_only_to_associations(
    migrated_database_engine: Engine,
    domain_tables: Mapping[str, Table],
) -> None:
    tags = domain_tables["tags"]
    associations = domain_tables["learning_card_tags"]
    cards = domain_tables["learning_cards"]
    owner_id = insert_user(migrated_database_engine)
    card_id = insert_owned_card(migrated_database_engine, owner_id=owner_id)
    tag_id = insert_tag(migrated_database_engine, tags, owner_id=owner_id)
    with migrated_database_engine.begin() as connection:
        connection.execute(
            associations.insert().values(
                owner_id=owner_id,
                card_id=card_id,
                tag_id=tag_id,
            )
        )
        connection.execute(tags.delete().where(tags.c.id == tag_id))

    with migrated_database_engine.connect() as connection:
        association_count = connection.execute(
            text("SELECT count(*) FROM learning_card_tags")
        ).scalar_one()
        card_count = connection.execute(
            select(func.count()).select_from(cards)
        ).scalar_one()

    assert association_count == 0
    assert card_count == 1


def test_physical_card_deletion_is_restricted_while_tagged(
    migrated_database_engine: Engine,
    domain_tables: Mapping[str, Table],
) -> None:
    tags = domain_tables["tags"]
    associations = domain_tables["learning_card_tags"]
    cards = domain_tables["learning_cards"]
    owner_id = insert_user(migrated_database_engine)
    card_id = insert_owned_card(migrated_database_engine, owner_id=owner_id)
    tag_id = insert_tag(migrated_database_engine, tags, owner_id=owner_id)
    with migrated_database_engine.begin() as connection:
        connection.execute(
            associations.insert().values(
                owner_id=owner_id,
                card_id=card_id,
                tag_id=tag_id,
            )
        )

    assert_integrity_error(
        migrated_database_engine,
        cards.delete().where(cards.c.id == card_id),
        sqlstate="23503",
        constraint_name="fk_learning_card_tags_card_id_owner_id_learning_cards",
    )


def test_tag_filtering_index_uses_tag_then_card(
    migrated_database_engine: Engine,
) -> None:
    with migrated_database_engine.connect() as connection:
        index_definition = connection.execute(
            text(
                """
                SELECT indexdef
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename = 'learning_card_tags'
                  AND indexname = 'ix_learning_card_tags_tag_id_card_id'
                """
            )
        ).scalar_one()

    assert "(tag_id, card_id)" in index_definition
