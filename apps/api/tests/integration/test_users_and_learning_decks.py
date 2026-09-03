"""PostgreSQL constraint tests for users and learning decks."""

import os
from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid4

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


def insert_user(
    engine: Engine,
    *,
    google_subject: str | None = None,
    normalized_email: str | None = None,
) -> int:
    """Insert one valid user and return its generated identity."""

    subject = google_subject or f"google-{uuid4()}"
    email = normalized_email or f"{uuid4()}@example.test"
    with engine.begin() as connection:
        return connection.execute(
            text(
                """
                INSERT INTO users (google_subject, normalized_email)
                VALUES (:google_subject, :normalized_email)
                RETURNING id
                """
            ),
            {
                "google_subject": subject,
                "normalized_email": email,
            },
        ).scalar_one()


def insert_deck(
    engine: Engine,
    *,
    owner_id: int,
    title: str = "Core vocabulary",
    target_language: str = "en",
    explanation_language: str = "zh-TW",
    creation_idempotency_key: UUID | None = None,
    creation_request_hash: str | None = None,
) -> UUID:
    """Insert one valid deck and return its generated UUID."""

    with engine.begin() as connection:
        return connection.execute(
            text(
                """
                INSERT INTO learning_decks (
                    owner_id,
                    title,
                    target_language,
                    explanation_language,
                    creation_idempotency_key,
                    creation_request_hash
                )
                VALUES (
                    :owner_id,
                    :title,
                    :target_language,
                    :explanation_language,
                    :creation_idempotency_key,
                    :creation_request_hash
                )
                RETURNING id
                """
            ),
            {
                "owner_id": owner_id,
                "title": title,
                "target_language": target_language,
                "explanation_language": explanation_language,
                "creation_idempotency_key": creation_idempotency_key,
                "creation_request_hash": creation_request_hash,
            },
        ).scalar_one()


def assert_integrity_error(
    engine: Engine,
    statement: str,
    parameters: Mapping[str, Any],
    *,
    sqlstate: str,
    constraint_name: str | None = None,
    column_name: str | None = None,
) -> None:
    """Assert PostgreSQL rejects a statement for the expected invariant."""

    with pytest.raises(IntegrityError) as caught, engine.begin() as connection:
        connection.execute(text(statement), parameters)

    assert caught.value.orig.sqlstate == sqlstate
    if constraint_name is not None:
        assert caught.value.orig.diag.constraint_name == constraint_name
    if column_name is not None:
        assert caught.value.orig.diag.column_name == column_name


def test_english_and_japanese_decks_share_one_owned_table(
    migrated_database_engine: Engine,
) -> None:
    owner_id = insert_user(migrated_database_engine)

    english_deck_id = insert_deck(
        migrated_database_engine,
        owner_id=owner_id,
        title="English",
        target_language="en",
    )
    japanese_deck_id = insert_deck(
        migrated_database_engine,
        owner_id=owner_id,
        title="Japanese",
        target_language="ja",
    )

    with migrated_database_engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT id, target_language
                FROM learning_decks
                WHERE owner_id = :owner_id
                ORDER BY target_language
                """
            ),
            {"owner_id": owner_id},
        ).all()

    assert rows == [(english_deck_id, "en"), (japanese_deck_id, "ja")]


def test_deck_requires_an_existing_owner(
    migrated_database_engine: Engine,
) -> None:
    insert_statement = """
        INSERT INTO learning_decks (
            owner_id, title, target_language, explanation_language
        )
        VALUES (:owner_id, 'Deck', 'en', 'zh-TW')
    """
    assert_integrity_error(
        migrated_database_engine,
        insert_statement,
        {"owner_id": None},
        sqlstate="23502",
        column_name="owner_id",
    )
    assert_integrity_error(
        migrated_database_engine,
        insert_statement,
        {"owner_id": 9_999_999},
        sqlstate="23503",
        constraint_name="fk_learning_decks_owner_id_users",
    )


def test_user_identity_and_timestamps_are_database_enforced(
    migrated_database_engine: Engine,
) -> None:
    cases = [
        (
            "'   ', 'user@example.test', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP",
            "ck_users_google_subject_nonblank",
        ),
        (
            "'google-subject', '   ', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP",
            "ck_users_normalized_email_nonblank",
        ),
        (
            (
                "'google-subject', 'user@example.test', CURRENT_TIMESTAMP, "
                "CURRENT_TIMESTAMP - INTERVAL '1 second'"
            ),
            "ck_users_timestamps_ordered",
        ),
    ]

    for values_sql, constraint_name in cases:
        assert_integrity_error(
            migrated_database_engine,
            f"""
            INSERT INTO users (
                google_subject, normalized_email, created_at, updated_at
            )
            VALUES ({values_sql})
            """,
            {},
            sqlstate="23514",
            constraint_name=constraint_name,
        )


@pytest.mark.parametrize(
    ("column", "value", "constraint_name"),
    [
        (
            "target_language",
            "fr",
            "ck_learning_decks_target_language_supported",
        ),
        (
            "explanation_language",
            "fr",
            "ck_learning_decks_explanation_language_supported",
        ),
    ],
)
def test_deck_rejects_unsupported_languages(
    migrated_database_engine: Engine,
    column: str,
    value: str,
    constraint_name: str,
) -> None:
    owner_id = insert_user(migrated_database_engine)
    values = {
        "owner_id": owner_id,
        "title": "Deck",
        "target_language": "en",
        "explanation_language": "zh-TW",
    }
    values[column] = value

    assert_integrity_error(
        migrated_database_engine,
        """
        INSERT INTO learning_decks (
            owner_id, title, target_language, explanation_language
        )
        VALUES (
            :owner_id, :title, :target_language, :explanation_language
        )
        """,
        values,
        sqlstate="23514",
        constraint_name=constraint_name,
    )


def test_user_identity_and_deck_replay_constraints_are_database_enforced(
    migrated_database_engine: Engine,
) -> None:
    subject = f"google-{uuid4()}"
    owner_id = insert_user(
        migrated_database_engine,
        google_subject=subject,
    )
    replay_key = uuid4()
    insert_deck(
        migrated_database_engine,
        owner_id=owner_id,
        creation_idempotency_key=replay_key,
        creation_request_hash="request-v1",
    )

    assert_integrity_error(
        migrated_database_engine,
        """
        INSERT INTO users (google_subject, normalized_email)
        VALUES (:google_subject, 'second@example.test')
        """,
        {"google_subject": subject},
        sqlstate="23505",
        constraint_name="uq_users_google_subject",
    )
    assert_integrity_error(
        migrated_database_engine,
        """
        INSERT INTO learning_decks (
            owner_id,
            title,
            target_language,
            explanation_language,
            creation_idempotency_key
        )
        VALUES (:owner_id, 'Unpaired', 'en', 'zh-TW', :replay_key)
        """,
        {"owner_id": owner_id, "replay_key": uuid4()},
        sqlstate="23514",
        constraint_name="ck_learning_decks_creation_replay_fields_paired",
    )
    assert_integrity_error(
        migrated_database_engine,
        """
        INSERT INTO learning_decks (
            owner_id,
            title,
            target_language,
            explanation_language,
            creation_idempotency_key,
            creation_request_hash
        )
        VALUES (:owner_id, 'Blank hash', 'en', 'zh-TW', :replay_key, '   ')
        """,
        {"owner_id": owner_id, "replay_key": uuid4()},
        sqlstate="23514",
        constraint_name="ck_learning_decks_creation_request_hash_nonblank",
    )
    assert_integrity_error(
        migrated_database_engine,
        """
        INSERT INTO learning_decks (
            owner_id,
            title,
            target_language,
            explanation_language,
            creation_idempotency_key,
            creation_request_hash
        )
        VALUES (
            :owner_id, 'Replay', 'en', 'zh-TW', :replay_key, 'request-v1'
        )
        """,
        {"owner_id": owner_id, "replay_key": replay_key},
        sqlstate="23505",
        constraint_name="uq_learning_decks_owner_creation_idempotency_key",
    )


def test_deck_content_timestamps_and_version_are_database_enforced(
    migrated_database_engine: Engine,
) -> None:
    owner_id = insert_user(migrated_database_engine)
    cases = [
        (
            "'   ', 'en', 'zh-TW', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP",
            "ck_learning_decks_title_length",
        ),
        (
            "'Deck', 'en', 'zh-TW', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP",
            "ck_learning_decks_version_positive",
        ),
        (
            (
                "'Deck', 'en', 'zh-TW', 1, CURRENT_TIMESTAMP, "
                "CURRENT_TIMESTAMP - INTERVAL '1 second'"
            ),
            "ck_learning_decks_timestamps_ordered",
        ),
    ]

    for values_sql, constraint_name in cases:
        assert_integrity_error(
            migrated_database_engine,
            f"""
            INSERT INTO learning_decks (
                owner_id,
                title,
                target_language,
                explanation_language,
                version,
                created_at,
                updated_at
            )
            VALUES (:owner_id, {values_sql})
            """,
            {"owner_id": owner_id},
            sqlstate="23514",
            constraint_name=constraint_name,
        )

    assert_integrity_error(
        migrated_database_engine,
        """
        INSERT INTO learning_decks (
            owner_id,
            title,
            target_language,
            explanation_language,
            created_at,
            archived_at
        )
        VALUES (
            :owner_id,
            'Deck',
            'en',
            'zh-TW',
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP - INTERVAL '1 second'
        )
        """,
        {"owner_id": owner_id},
        sqlstate="23514",
        constraint_name="ck_learning_decks_archive_not_before_creation",
    )


def test_owner_deletion_is_restricted_while_a_deck_exists(
    migrated_database_engine: Engine,
) -> None:
    owner_id = insert_user(migrated_database_engine)
    insert_deck(migrated_database_engine, owner_id=owner_id)

    assert_integrity_error(
        migrated_database_engine,
        "DELETE FROM users WHERE id = :owner_id",
        {"owner_id": owner_id},
        sqlstate="23503",
        constraint_name="fk_learning_decks_owner_id_users",
    )
