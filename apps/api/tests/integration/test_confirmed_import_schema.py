"""PostgreSQL constraints for confirmed CSV import audit records."""

import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.imports import persist_dry_run, validate_csv_snapshot

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1",
        reason="set RUN_POSTGRES_INTEGRATION_TESTS=1 to run PostgreSQL integration tests",
    ),
]

FIXTURES = Path(__file__).parents[1] / "fixtures"
SOURCE_NAMESPACE = "legacy-google-sheet-cutover-v1"


def _insert_user(engine: Engine) -> int:
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


def _insert_deck(engine: Engine, owner_id: int) -> UUID:
    with engine.begin() as connection:
        return connection.execute(
            text(
                """
                INSERT INTO learning_decks (
                    owner_id, title, target_language, explanation_language
                ) VALUES (:owner_id, 'Confirmed import target', 'en', 'zh-TW')
                RETURNING id
                """
            ),
            {"owner_id": owner_id},
        ).scalar_one()


def _insert_card(engine: Engine, owner_id: int, deck_id: UUID) -> UUID:
    with engine.begin() as connection:
        return connection.execute(
            text(
                """
                INSERT INTO learning_cards (deck_id, owner_id, term, meaning)
                VALUES (:deck_id, :owner_id, 'synthetic term', 'synthetic meaning')
                RETURNING id
                """
            ),
            {"deck_id": deck_id, "owner_id": owner_id},
        ).scalar_one()


def _persist_dry_run(
    engine: Engine,
    *,
    owner_id: int,
    deck_id: UUID,
    snapshot_captured_at: datetime,
) -> UUID:
    report = validate_csv_snapshot(
        FIXTURES / "import-valid-en.csv",
        source_namespace=SOURCE_NAMESPACE,
        target_language="en",
        snapshot_captured_at=snapshot_captured_at,
    )
    with Session(engine) as session, session.begin():
        run_id, _ = persist_dry_run(
            session,
            report=report,
            owner_id=owner_id,
            deck_id=deck_id,
        )
    return run_id


def _insert_confirmed_run(
    connection,
    *,
    dry_run_id: UUID,
    owner_id: int,
    deck_id: UUID,
) -> UUID:
    return connection.execute(
        text(
            """
            INSERT INTO confirmed_import_runs (
                approved_dry_run_id, owner_id, deck_id, source_namespace,
                status, eligible_row_count, imported_card_count,
                source_mapping_count, tag_count, card_tag_association_count,
                review_state_count, archived_card_count, reconciliation_status,
                completed_at
            ) VALUES (
                :dry_run_id, :owner_id, :deck_id, :source_namespace,
                'completed', 1, 1, 1, 0, 0, 1, 0, 'pending',
                CURRENT_TIMESTAMP
            )
            RETURNING id
            """
        ),
        {
            "dry_run_id": dry_run_id,
            "owner_id": owner_id,
            "deck_id": deck_id,
            "source_namespace": SOURCE_NAMESPACE,
        },
    ).scalar_one()


def _approved_item(connection, dry_run_id: UUID):
    return connection.execute(
        text(
            """
            SELECT id, row_number, source_identity_hash, content_hash
            FROM import_items
            WHERE run_id = :dry_run_id
            """
        ),
        {"dry_run_id": dry_run_id},
    ).one()


def test_confirmed_mapping_is_bound_to_approved_hashes_and_owned_card(
    migrated_database_engine: Engine,
) -> None:
    owner_id = _insert_user(migrated_database_engine)
    deck_id = _insert_deck(migrated_database_engine, owner_id)
    card_id = _insert_card(migrated_database_engine, owner_id, deck_id)
    dry_run_id = _persist_dry_run(
        migrated_database_engine,
        owner_id=owner_id,
        deck_id=deck_id,
        snapshot_captured_at=datetime(2026, 9, 9, 4, 0, tzinfo=UTC),
    )

    with migrated_database_engine.begin() as connection:
        confirmed_run_id = _insert_confirmed_run(
            connection,
            dry_run_id=dry_run_id,
            owner_id=owner_id,
            deck_id=deck_id,
        )
        item = _approved_item(connection, dry_run_id)
        connection.execute(
            text(
                """
                INSERT INTO confirmed_import_mappings (
                    confirmed_import_run_id, approved_dry_run_id,
                    approved_import_item_id, owner_id, source_namespace,
                    row_number, source_identity_hash, canonical_content_hash,
                    learning_card_id, outcome
                ) VALUES (
                    :confirmed_run_id, :dry_run_id, :item_id, :owner_id,
                    :source_namespace, :row_number, :source_identity_hash,
                    :content_hash, :card_id, 'created'
                )
                """
            ),
            {
                "confirmed_run_id": confirmed_run_id,
                "dry_run_id": dry_run_id,
                "item_id": item.id,
                "owner_id": owner_id,
                "source_namespace": SOURCE_NAMESPACE,
                "row_number": item.row_number,
                "source_identity_hash": item.source_identity_hash,
                "content_hash": item.content_hash,
                "card_id": card_id,
            },
        )

    with migrated_database_engine.connect() as connection:
        mapping = connection.execute(
            text(
                """
                SELECT owner_id, source_namespace, source_identity_hash,
                       canonical_content_hash, learning_card_id
                FROM confirmed_import_mappings
                """
            )
        ).one()

    assert mapping.owner_id == owner_id
    assert mapping.source_namespace == SOURCE_NAMESPACE
    assert mapping.learning_card_id == card_id
    assert len(mapping.source_identity_hash) == 64
    assert len(mapping.canonical_content_hash) == 64


def test_confirmed_mapping_rejects_hash_not_in_approved_item(
    migrated_database_engine: Engine,
) -> None:
    owner_id = _insert_user(migrated_database_engine)
    deck_id = _insert_deck(migrated_database_engine, owner_id)
    card_id = _insert_card(migrated_database_engine, owner_id, deck_id)
    dry_run_id = _persist_dry_run(
        migrated_database_engine,
        owner_id=owner_id,
        deck_id=deck_id,
        snapshot_captured_at=datetime(2026, 9, 9, 4, 0, tzinfo=UTC),
    )

    with pytest.raises(IntegrityError), migrated_database_engine.begin() as connection:
        confirmed_run_id = _insert_confirmed_run(
            connection,
            dry_run_id=dry_run_id,
            owner_id=owner_id,
            deck_id=deck_id,
        )
        item = _approved_item(connection, dry_run_id)
        connection.execute(
            text(
                """
                INSERT INTO confirmed_import_mappings (
                    confirmed_import_run_id, approved_dry_run_id,
                    approved_import_item_id, owner_id, source_namespace,
                    row_number, source_identity_hash, canonical_content_hash,
                    learning_card_id, outcome
                ) VALUES (
                    :confirmed_run_id, :dry_run_id, :item_id, :owner_id,
                    :source_namespace, :row_number, :source_identity_hash,
                    :content_hash, :card_id, 'created'
                )
                """
            ),
            {
                "confirmed_run_id": confirmed_run_id,
                "dry_run_id": dry_run_id,
                "item_id": item.id,
                "owner_id": owner_id,
                "source_namespace": SOURCE_NAMESPACE,
                "row_number": item.row_number,
                "source_identity_hash": item.source_identity_hash,
                "content_hash": "0" * 64,
                "card_id": card_id,
            },
        )


def test_owner_namespace_can_have_only_one_successful_confirmed_import(
    migrated_database_engine: Engine,
) -> None:
    owner_id = _insert_user(migrated_database_engine)
    deck_id = _insert_deck(migrated_database_engine, owner_id)
    first_dry_run_id = _persist_dry_run(
        migrated_database_engine,
        owner_id=owner_id,
        deck_id=deck_id,
        snapshot_captured_at=datetime(2026, 9, 9, 4, 0, tzinfo=UTC),
    )
    second_dry_run_id = _persist_dry_run(
        migrated_database_engine,
        owner_id=owner_id,
        deck_id=deck_id,
        snapshot_captured_at=datetime(2026, 9, 10, 4, 0, tzinfo=UTC),
    )

    with migrated_database_engine.begin() as connection:
        _insert_confirmed_run(
            connection,
            dry_run_id=first_dry_run_id,
            owner_id=owner_id,
            deck_id=deck_id,
        )

    with pytest.raises(IntegrityError), migrated_database_engine.begin() as connection:
        _insert_confirmed_run(
            connection,
            dry_run_id=second_dry_run_id,
            owner_id=owner_id,
            deck_id=deck_id,
        )
