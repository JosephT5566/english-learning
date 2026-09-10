"""PostgreSQL tests for the one-time CSV dry-run audit boundary."""

import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.imports import ImportBoundaryError, persist_dry_run, validate_csv_snapshot

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1",
        reason="set RUN_POSTGRES_INTEGRATION_TESTS=1 to run PostgreSQL integration tests",
    ),
]

FIXTURES = Path(__file__).parents[1] / "fixtures"


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
                ) VALUES (:owner_id, 'Import target', :language, 'zh-TW')
                RETURNING id
                """
            ),
            {"owner_id": owner_id, "language": language},
        ).scalar_one()


def _report(language: str = "en"):
    return validate_csv_snapshot(
        FIXTURES / f"import-valid-{language}.csv",
        source_namespace="legacy-google-sheet-cutover-v1",
        target_language=language,
        snapshot_captured_at=datetime(2026, 9, 9, 4, 0, tzinfo=UTC),
    )


def _table_counts(engine: Engine) -> dict[str, int]:
    tables = (
        "learning_cards",
        "review_states",
        "review_batches",
        "review_events",
        "tags",
        "learning_card_tags",
    )
    with engine.connect() as connection:
        return {
            table: connection.execute(
                text(f"SELECT count(*) FROM {table}")
            ).scalar_one()
            for table in tables
        }


def test_unchanged_dry_run_replays_one_audit_without_learning_mutations(
    migrated_database_engine: Engine,
) -> None:
    owner_id = _insert_user(migrated_database_engine)
    deck_id = _insert_deck(migrated_database_engine, owner_id)
    before = _table_counts(migrated_database_engine)
    report = _report()

    with Session(migrated_database_engine) as session, session.begin():
        first_id, first_replayed = persist_dry_run(
            session, report=report, owner_id=owner_id, deck_id=deck_id
        )
    with Session(migrated_database_engine) as session, session.begin():
        second_id, second_replayed = persist_dry_run(
            session, report=_report(), owner_id=owner_id, deck_id=deck_id
        )

    assert first_id == second_id
    assert first_replayed is False
    assert second_replayed is True
    assert _table_counts(migrated_database_engine) == before
    with migrated_database_engine.connect() as connection:
        assert (
            connection.execute(text("SELECT count(*) FROM import_runs")).scalar_one()
            == 1
        )
        assert (
            connection.execute(text("SELECT count(*) FROM import_items")).scalar_one()
            == 1
        )


def test_dry_run_rejects_cross_owner_and_language_conflicts(
    migrated_database_engine: Engine,
) -> None:
    owner_id = _insert_user(migrated_database_engine)
    other_owner_id = _insert_user(migrated_database_engine)
    english_deck_id = _insert_deck(migrated_database_engine, owner_id)

    with (
        pytest.raises(ImportBoundaryError, match="target_deck_not_found"),
        Session(migrated_database_engine) as session,
        session.begin(),
    ):
        persist_dry_run(
            session,
            report=_report(),
            owner_id=other_owner_id,
            deck_id=english_deck_id,
        )

    with (
        pytest.raises(ImportBoundaryError, match="target_language_conflict"),
        Session(migrated_database_engine) as session,
        session.begin(),
    ):
        persist_dry_run(
            session,
            report=_report("ja"),
            owner_id=owner_id,
            deck_id=english_deck_id,
        )


def test_changed_snapshot_creates_a_separate_audit_run(
    migrated_database_engine: Engine,
    tmp_path: Path,
) -> None:
    owner_id = _insert_user(migrated_database_engine)
    deck_id = _insert_deck(migrated_database_engine, owner_id)
    first_report = _report()
    changed_path = tmp_path / "changed.csv"
    changed_path.write_text(
        (FIXTURES / "import-valid-en.csv")
        .read_text(encoding="utf-8")
        .replace("synthetic phrase", "changed synthetic phrase"),
        encoding="utf-8",
    )
    second_report = validate_csv_snapshot(
        changed_path,
        source_namespace="legacy-google-sheet-cutover-v1",
        target_language="en",
        snapshot_captured_at=datetime(2026, 9, 9, 4, 0, tzinfo=UTC),
    )

    with Session(migrated_database_engine) as session, session.begin():
        first_id, _ = persist_dry_run(
            session, report=first_report, owner_id=owner_id, deck_id=deck_id
        )
    with Session(migrated_database_engine) as session, session.begin():
        second_id, replayed = persist_dry_run(
            session, report=second_report, owner_id=owner_id, deck_id=deck_id
        )

    assert first_report.source_snapshot_hash != second_report.source_snapshot_hash
    assert (
        first_report.items[0].source_identity_hash
        == second_report.items[0].source_identity_hash
    )
    assert first_report.items[0].content_hash != second_report.items[0].content_hash
    assert first_id != second_id
    assert replayed is False
