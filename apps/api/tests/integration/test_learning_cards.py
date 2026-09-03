"""PostgreSQL constraint tests for confirmed multilingual learning cards."""

import os
from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, MetaData, Table, text
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
def learning_cards_table(migrated_database_engine: Engine) -> Table:
    """Reflect the migrated card table with PostgreSQL-aware column types."""

    return Table("learning_cards", MetaData(), autoload_with=migrated_database_engine)


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


def insert_deck(
    engine: Engine,
    *,
    owner_id: int,
    target_language: str = "en",
) -> UUID:
    """Insert a valid owned deck."""

    with engine.begin() as connection:
        return connection.execute(
            text(
                """
                INSERT INTO learning_decks (
                    owner_id, title, target_language, explanation_language
                )
                VALUES (:owner_id, :title, :target_language, 'zh-TW')
                RETURNING id
                """
            ),
            {
                "owner_id": owner_id,
                "title": f"{target_language} deck {uuid4()}",
                "target_language": target_language,
            },
        ).scalar_one()


def valid_card_values(
    *,
    deck_id: UUID,
    owner_id: int,
    term: str = "example",
    meaning: str = "例子",
    **overrides: Any,
) -> dict[str, Any]:
    """Return a minimal valid card value mapping with optional overrides."""

    values = {
        "deck_id": deck_id,
        "owner_id": owner_id,
        "term": term,
        "meaning": meaning,
    }
    values.update(overrides)
    return values


def insert_card(
    engine: Engine,
    table: Table,
    values: Mapping[str, Any],
) -> UUID:
    """Insert a card and return its generated UUID."""

    with engine.begin() as connection:
        return connection.execute(
            table.insert().values(**values).returning(table.c.id)
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


def test_english_and_japanese_cards_share_one_confirmed_card_table(
    migrated_database_engine: Engine,
    learning_cards_table: Table,
) -> None:
    owner_id = insert_user(migrated_database_engine)
    english_deck_id = insert_deck(migrated_database_engine, owner_id=owner_id)
    japanese_deck_id = insert_deck(
        migrated_database_engine,
        owner_id=owner_id,
        target_language="ja",
    )

    english_card_id = insert_card(
        migrated_database_engine,
        learning_cards_table,
        valid_card_values(
            deck_id=english_deck_id,
            owner_id=owner_id,
            term="serendipity",
            meaning="意外發現美好事物的能力",
            pronunciation="/ˌser.ənˈdɪp.ə.ti/",
            example_sentence="We met by pure serendipity.",
            example_translation="我們的相遇純屬美好的偶然。",
            synonyms=["chance", "fortune"],
            part_of_speech="noun",
        ),
    )
    japanese_card_id = insert_card(
        migrated_database_engine,
        learning_cards_table,
        valid_card_values(
            deck_id=japanese_deck_id,
            owner_id=owner_id,
            term="勉強",
            meaning="學習",
            reading="べんきょう",
            romanization="benkyou",
            example_sentence="毎日日本語を勉強します。",
            example_translation="我每天學日文。",
            part_of_speech="noun",
        ),
    )

    with migrated_database_engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT c.id, d.target_language, c.term, c.reading
                FROM learning_cards AS c
                JOIN learning_decks AS d ON d.id = c.deck_id
                WHERE c.owner_id = :owner_id
                ORDER BY d.target_language
                """
            ),
            {"owner_id": owner_id},
        ).all()

    assert rows == [
        (english_card_id, "en", "serendipity", None),
        (japanese_card_id, "ja", "勉強", "べんきょう"),
    ]


def test_card_requires_an_existing_owned_deck_pair(
    migrated_database_engine: Engine,
    learning_cards_table: Table,
) -> None:
    first_owner_id = insert_user(migrated_database_engine)
    second_owner_id = insert_user(migrated_database_engine)
    first_deck_id = insert_deck(
        migrated_database_engine,
        owner_id=first_owner_id,
    )

    assert_integrity_error(
        migrated_database_engine,
        learning_cards_table.insert().values(
            deck_id=None,
            owner_id=first_owner_id,
            term="term",
            meaning="meaning",
        ),
        sqlstate="23502",
        column_name="deck_id",
    )
    assert_integrity_error(
        migrated_database_engine,
        learning_cards_table.insert().values(
            deck_id=uuid4(),
            owner_id=first_owner_id,
            term="term",
            meaning="meaning",
        ),
        sqlstate="23503",
        constraint_name="fk_learning_cards_deck_id_owner_id_learning_decks",
    )
    assert_integrity_error(
        migrated_database_engine,
        learning_cards_table.insert().values(
            deck_id=first_deck_id,
            owner_id=second_owner_id,
            term="term",
            meaning="meaning",
        ),
        sqlstate="23503",
        constraint_name="fk_learning_cards_deck_id_owner_id_learning_decks",
    )


@pytest.mark.parametrize(
    ("values", "sqlstate", "constraint_name", "column_name"),
    [
        ({"term": None}, "23502", None, "term"),
        ({"meaning": None}, "23502", None, "meaning"),
        (
            {"term": "   "},
            "23514",
            "ck_learning_cards_term_length",
            None,
        ),
        (
            {"meaning": "   "},
            "23514",
            "ck_learning_cards_meaning_length",
            None,
        ),
    ],
)
def test_confirmed_card_requires_term_and_meaning(
    migrated_database_engine: Engine,
    learning_cards_table: Table,
    values: Mapping[str, Any],
    sqlstate: str,
    constraint_name: str | None,
    column_name: str | None,
) -> None:
    owner_id = insert_user(migrated_database_engine)
    deck_id = insert_deck(migrated_database_engine, owner_id=owner_id)

    assert_integrity_error(
        migrated_database_engine,
        learning_cards_table.insert().values(
            **valid_card_values(
                deck_id=deck_id,
                owner_id=owner_id,
                **values,
            )
        ),
        sqlstate=sqlstate,
        constraint_name=constraint_name,
        column_name=column_name,
    )


@pytest.mark.parametrize(
    ("values", "constraint_name"),
    [
        (
            {"reading": "   "},
            "ck_learning_cards_reading_length",
        ),
        (
            {"example_sentence": "   "},
            "ck_learning_cards_example_sentence_length",
        ),
        (
            {"example_translation": "translation without sentence"},
            "ck_learning_cards_example_dependents_require_sentence",
        ),
        (
            {"part_of_speech": "unsupported"},
            "ck_learning_cards_part_of_speech_supported",
        ),
        (
            {"part_of_speech": "other"},
            "ck_learning_cards_other_part_of_speech_requires_detail",
        ),
        (
            {"synonyms": [str(index) for index in range(21)]},
            "ck_learning_cards_synonyms_count",
        ),
        (
            {"antonyms": ["opposite", None]},
            "ck_learning_cards_antonyms_no_nulls",
        ),
    ],
)
def test_card_optional_content_constraints_are_database_enforced(
    migrated_database_engine: Engine,
    learning_cards_table: Table,
    values: Mapping[str, Any],
    constraint_name: str,
) -> None:
    owner_id = insert_user(migrated_database_engine)
    deck_id = insert_deck(migrated_database_engine, owner_id=owner_id)

    assert_integrity_error(
        migrated_database_engine,
        learning_cards_table.insert().values(
            **valid_card_values(
                deck_id=deck_id,
                owner_id=owner_id,
                **values,
            )
        ),
        sqlstate="23514",
        constraint_name=constraint_name,
    )


def test_card_replay_version_and_timestamp_constraints_are_database_enforced(
    migrated_database_engine: Engine,
    learning_cards_table: Table,
) -> None:
    owner_id = insert_user(migrated_database_engine)
    deck_id = insert_deck(migrated_database_engine, owner_id=owner_id)
    replay_key = uuid4()
    insert_card(
        migrated_database_engine,
        learning_cards_table,
        valid_card_values(
            deck_id=deck_id,
            owner_id=owner_id,
            creation_idempotency_key=replay_key,
            creation_request_hash="request-v1",
        ),
    )
    cases = [
        (
            {"creation_idempotency_key": uuid4()},
            "23514",
            "ck_learning_cards_creation_replay_fields_paired",
        ),
        (
            {
                "creation_idempotency_key": uuid4(),
                "creation_request_hash": "   ",
            },
            "23514",
            "ck_learning_cards_creation_request_hash_nonblank",
        ),
        (
            {
                "creation_idempotency_key": replay_key,
                "creation_request_hash": "request-v1",
            },
            "23505",
            "uq_learning_cards_owner_creation_idempotency_key",
        ),
        (
            {"version": 0},
            "23514",
            "ck_learning_cards_version_positive",
        ),
    ]

    for values, sqlstate, constraint_name in cases:
        assert_integrity_error(
            migrated_database_engine,
            learning_cards_table.insert().values(
                **valid_card_values(
                    deck_id=deck_id,
                    owner_id=owner_id,
                    term=f"term-{uuid4()}",
                    **values,
                )
            ),
            sqlstate=sqlstate,
            constraint_name=constraint_name,
        )

    assert_integrity_error(
        migrated_database_engine,
        learning_cards_table.insert().values(
            **valid_card_values(
                deck_id=deck_id,
                owner_id=owner_id,
                created_at=text("CURRENT_TIMESTAMP"),
                updated_at=text("CURRENT_TIMESTAMP - INTERVAL '1 second'"),
            )
        ),
        sqlstate="23514",
        constraint_name="ck_learning_cards_timestamps_ordered",
    )
    assert_integrity_error(
        migrated_database_engine,
        learning_cards_table.insert().values(
            **valid_card_values(
                deck_id=deck_id,
                owner_id=owner_id,
                created_at=text("CURRENT_TIMESTAMP"),
                archived_at=text("CURRENT_TIMESTAMP - INTERVAL '1 second'"),
            )
        ),
        sqlstate="23514",
        constraint_name="ck_learning_cards_archive_not_before_creation",
    )


def test_physical_deck_deletion_is_restricted_while_a_card_exists(
    migrated_database_engine: Engine,
    learning_cards_table: Table,
) -> None:
    owner_id = insert_user(migrated_database_engine)
    deck_id = insert_deck(migrated_database_engine, owner_id=owner_id)
    insert_card(
        migrated_database_engine,
        learning_cards_table,
        valid_card_values(deck_id=deck_id, owner_id=owner_id),
    )

    assert_integrity_error(
        migrated_database_engine,
        text("DELETE FROM learning_decks WHERE id = :deck_id").bindparams(
            deck_id=deck_id
        ),
        sqlstate="23503",
        constraint_name="fk_learning_cards_deck_id_owner_id_learning_decks",
    )


def test_active_card_listing_index_matches_the_named_access_pattern(
    migrated_database_engine: Engine,
) -> None:
    with migrated_database_engine.connect() as connection:
        index_definition = connection.execute(
            text(
                """
                SELECT indexdef
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename = 'learning_cards'
                  AND indexname = 'ix_learning_cards_active_deck_created_id'
                """
            )
        ).scalar_one()

    assert "(deck_id, created_at DESC, id DESC)" in index_definition
    assert "WHERE (archived_at IS NULL)" in index_definition
