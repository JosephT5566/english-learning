"""PostgreSQL verification boundary for approved confirmed imports."""

import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.confirmed_imports import ConfirmedImportError, verify_approved_snapshot
from app.imports import (
    VALIDATOR_VERSION,
    persist_dry_run,
    read_validated_csv_snapshot,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1",
        reason="set RUN_POSTGRES_INTEGRATION_TESTS=1 to run PostgreSQL integration tests",
    ),
]

FIXTURES = Path(__file__).parents[1] / "fixtures"
SOURCE_NAMESPACE = "legacy-google-sheet-cutover-v1"
SNAPSHOT_AT = datetime(2026, 9, 9, 4, 0, tzinfo=UTC)


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


def _insert_deck(engine: Engine, owner_id: int, language: str = "en") -> UUID:
    with engine.begin() as connection:
        return connection.execute(
            text(
                """
                INSERT INTO learning_decks (
                    owner_id, title, target_language, explanation_language
                ) VALUES (:owner_id, 'Confirmed import target', :language, 'zh-TW')
                RETURNING id
                """
            ),
            {"owner_id": owner_id, "language": language},
        ).scalar_one()


def _snapshot(path: Path = FIXTURES / "import-valid-en.csv"):
    return read_validated_csv_snapshot(
        path,
        source_namespace=SOURCE_NAMESPACE,
        target_language="en",
        snapshot_captured_at=SNAPSHOT_AT,
    )


def _persist_approved_dry_run(engine: Engine, *, owner_id: int, deck_id: UUID) -> UUID:
    with Session(engine) as session, session.begin():
        dry_run_id, _ = persist_dry_run(
            session,
            report=_snapshot().report,
            owner_id=owner_id,
            deck_id=deck_id,
        )
    return dry_run_id


def _verify(
    session: Session,
    *,
    snapshot,
    dry_run_id: UUID,
    owner_id: int,
    deck_id: UUID,
):
    return verify_approved_snapshot(
        session,
        snapshot=snapshot,
        approved_dry_run_id=dry_run_id,
        owner_id=owner_id,
        deck_id=deck_id,
        source_namespace=SOURCE_NAMESPACE,
        target_language="en",
        snapshot_captured_at=SNAPSHOT_AT,
        validator_version=VALIDATOR_VERSION,
    )


def _product_counts(engine: Engine) -> tuple[int, ...]:
    with engine.connect() as connection:
        return tuple(
            connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            for table in (
                "learning_cards",
                "tags",
                "learning_card_tags",
                "review_states",
                "review_batches",
                "review_events",
                "confirmed_import_runs",
                "confirmed_import_mappings",
            )
        )


def test_matching_snapshot_is_verified_without_product_writes(
    migrated_database_engine: Engine,
) -> None:
    owner_id = _insert_user(migrated_database_engine)
    deck_id = _insert_deck(migrated_database_engine, owner_id)
    dry_run_id = _persist_approved_dry_run(
        migrated_database_engine, owner_id=owner_id, deck_id=deck_id
    )
    before = _product_counts(migrated_database_engine)

    with Session(migrated_database_engine) as session, session.begin():
        approved = _verify(
            session,
            snapshot=_snapshot(),
            dry_run_id=dry_run_id,
            owner_id=owner_id,
            deck_id=deck_id,
        )

    assert approved.dry_run_id == dry_run_id
    assert approved.owner_id == owner_id
    assert approved.deck_id == deck_id
    assert len(approved.items) == 1
    assert _product_counts(migrated_database_engine) == before


def test_changed_csv_is_rejected_before_product_writes(
    migrated_database_engine: Engine,
    tmp_path: Path,
) -> None:
    owner_id = _insert_user(migrated_database_engine)
    deck_id = _insert_deck(migrated_database_engine, owner_id)
    dry_run_id = _persist_approved_dry_run(
        migrated_database_engine, owner_id=owner_id, deck_id=deck_id
    )
    changed_path = tmp_path / "changed.csv"
    changed_path.write_text(
        (FIXTURES / "import-valid-en.csv")
        .read_text(encoding="utf-8")
        .replace("synthetic phrase", "changed synthetic phrase"),
        encoding="utf-8",
    )
    before = _product_counts(migrated_database_engine)

    with (
        pytest.raises(ConfirmedImportError, match="source_snapshot_hash_mismatch"),
        Session(migrated_database_engine) as session,
        session.begin(),
    ):
        _verify(
            session,
            snapshot=_snapshot(changed_path),
            dry_run_id=dry_run_id,
            owner_id=owner_id,
            deck_id=deck_id,
        )

    assert _product_counts(migrated_database_engine) == before


def test_foreign_owner_and_archived_deck_are_rejected(
    migrated_database_engine: Engine,
) -> None:
    owner_id = _insert_user(migrated_database_engine)
    other_owner_id = _insert_user(migrated_database_engine)
    deck_id = _insert_deck(migrated_database_engine, owner_id)
    dry_run_id = _persist_approved_dry_run(
        migrated_database_engine, owner_id=owner_id, deck_id=deck_id
    )

    with (
        pytest.raises(ConfirmedImportError, match="approved_dry_run_not_found"),
        Session(migrated_database_engine) as session,
        session.begin(),
    ):
        _verify(
            session,
            snapshot=_snapshot(),
            dry_run_id=dry_run_id,
            owner_id=other_owner_id,
            deck_id=deck_id,
        )

    with migrated_database_engine.begin() as connection:
        connection.execute(
            text(
                """
                UPDATE learning_decks
                SET archived_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = :deck_id
                """
            ),
            {"deck_id": deck_id},
        )

    with (
        pytest.raises(ConfirmedImportError, match="target_deck_archived"),
        Session(migrated_database_engine) as session,
        session.begin(),
    ):
        _verify(
            session,
            snapshot=_snapshot(),
            dry_run_id=dry_run_id,
            owner_id=owner_id,
            deck_id=deck_id,
        )


def test_dry_run_with_rejected_rows_is_ineligible(
    migrated_database_engine: Engine,
    tmp_path: Path,
) -> None:
    owner_id = _insert_user(migrated_database_engine)
    deck_id = _insert_deck(migrated_database_engine, owner_id)
    rejected_path = tmp_path / "rejected.csv"
    rejected_path.write_text(
        (FIXTURES / "import-valid-en.csv")
        .read_text(encoding="utf-8")
        .replace("synthetic meaning", ""),
        encoding="utf-8",
    )
    rejected_snapshot = _snapshot(rejected_path)
    with Session(migrated_database_engine) as session, session.begin():
        dry_run_id, _ = persist_dry_run(
            session,
            report=rejected_snapshot.report,
            owner_id=owner_id,
            deck_id=deck_id,
        )

    with (
        pytest.raises(ConfirmedImportError, match="approved_dry_run_has_rejections"),
        Session(migrated_database_engine) as session,
        session.begin(),
    ):
        _verify(
            session,
            snapshot=rejected_snapshot,
            dry_run_id=dry_run_id,
            owner_id=owner_id,
            deck_id=deck_id,
        )
