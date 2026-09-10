"""Post-commit reconciliation tests for confirmed CSV imports."""

import json
import os
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.confirmed_imports import (
    apply_confirmed_import,
    execute_confirmed_import,
    main,
    reconcile_confirmed_import,
)
from app.database import create_database_session_factory
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


def _insert_user_and_deck(engine: Engine) -> tuple[int, UUID]:
    with engine.begin() as connection:
        owner_id = connection.execute(
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
        deck_id = connection.execute(
            text(
                """
                INSERT INTO learning_decks (
                    owner_id, title, target_language, explanation_language
                ) VALUES (:owner_id, 'Reconciliation target', 'en', 'zh-TW')
                RETURNING id
                """
            ),
            {"owner_id": owner_id},
        ).scalar_one()
    return owner_id, deck_id


def _arrange_approved_import(engine: Engine):
    owner_id, deck_id = _insert_user_and_deck(engine)
    snapshot = read_validated_csv_snapshot(
        FIXTURES / "import-valid-en.csv",
        source_namespace=SOURCE_NAMESPACE,
        target_language="en",
        snapshot_captured_at=SNAPSHOT_AT,
    )
    with Session(engine) as session, session.begin():
        dry_run_id, _ = persist_dry_run(
            session,
            report=snapshot.report,
            owner_id=owner_id,
            deck_id=deck_id,
        )
    session_factory = create_database_session_factory(engine)
    return owner_id, deck_id, snapshot, dry_run_id, session_factory


def _arrange_applied_import(engine: Engine):
    owner_id, deck_id, snapshot, dry_run_id, session_factory = _arrange_approved_import(
        engine
    )
    apply_result = apply_confirmed_import(
        session_factory,
        snapshot=snapshot,
        approved_dry_run_id=dry_run_id,
        owner_id=owner_id,
        deck_id=deck_id,
        source_namespace=SOURCE_NAMESPACE,
        target_language="en",
        snapshot_captured_at=SNAPSHOT_AT,
        validator_version=VALIDATOR_VERSION,
    )
    return owner_id, deck_id, snapshot, dry_run_id, session_factory, apply_result


def test_reconciliation_passes_and_replays_persisted_safe_result(
    migrated_database_engine: Engine,
) -> None:
    (
        _,
        _,
        snapshot,
        _,
        session_factory,
        apply_result,
    ) = _arrange_applied_import(migrated_database_engine)

    first = reconcile_confirmed_import(
        session_factory,
        apply_result=apply_result,
        snapshot=snapshot,
    )
    with migrated_database_engine.connect() as connection:
        persisted_before = connection.execute(
            text(
                """
                SELECT reconciliation_status, reconciliation_result, reconciled_at
                FROM confirmed_import_runs WHERE id = :run_id
                """
            ),
            {"run_id": apply_result.run_id},
        ).one()

    replay = reconcile_confirmed_import(
        session_factory,
        apply_result=apply_result,
        snapshot=snapshot,
    )
    with migrated_database_engine.connect() as connection:
        persisted_after = connection.execute(
            text(
                """
                SELECT reconciliation_status, reconciliation_result, reconciled_at
                FROM confirmed_import_runs WHERE id = :run_id
                """
            ),
            {"run_id": apply_result.run_id},
        ).one()

    assert first.status == "passed"
    assert all(first.checks.values())
    assert first.diagnostic_codes == []
    assert first.actual_counts == first.expected_counts
    assert first.samples[0].row_number == 2
    assert all(first.samples[0].fields.values())
    assert replay == first
    assert persisted_before == persisted_after
    assert persisted_after.reconciliation_status == "passed"
    serialized = json.dumps(asdict(first))
    assert snapshot.rows[0].card_candidate["term"] not in serialized
    assert snapshot.rows[0].card_candidate["meaning"] not in serialized


def test_retry_after_apply_commit_recovers_without_duplicate_mutations(
    migrated_database_engine: Engine,
) -> None:
    (
        owner_id,
        deck_id,
        snapshot,
        dry_run_id,
        session_factory,
        first_apply,
    ) = _arrange_applied_import(migrated_database_engine)

    replay = apply_confirmed_import(
        session_factory,
        snapshot=snapshot,
        approved_dry_run_id=dry_run_id,
        owner_id=owner_id,
        deck_id=deck_id,
        source_namespace=SOURCE_NAMESPACE,
        target_language="en",
        snapshot_captured_at=SNAPSHOT_AT,
        validator_version=VALIDATOR_VERSION,
    )
    reconciliation = reconcile_confirmed_import(
        session_factory,
        apply_result=replay,
        snapshot=snapshot,
    )

    assert first_apply.replayed is False
    assert replay.replayed is True
    assert replay.run_id == first_apply.run_id
    assert reconciliation.status == "passed"
    with migrated_database_engine.connect() as connection:
        counts = connection.execute(
            text(
                """
                SELECT
                    (SELECT count(*) FROM learning_cards) AS cards,
                    (SELECT count(*) FROM review_states) AS states,
                    (SELECT count(*) FROM confirmed_import_runs) AS runs,
                    (SELECT count(*) FROM confirmed_import_mappings) AS mappings
                """
            )
        ).one()
    assert tuple(counts) == (1, 1, 1, 1)


def test_failure_after_commit_is_recovered_by_unchanged_execution_retry(
    migrated_database_engine: Engine,
) -> None:
    owner_id, deck_id, snapshot, dry_run_id, session_factory = _arrange_approved_import(
        migrated_database_engine
    )

    def fail_after_commit(point: str, row_number: int | None = None) -> None:
        del row_number
        if point == "after_commit":
            raise RuntimeError("synthetic_post_commit_failure")

    with pytest.raises(RuntimeError, match="synthetic_post_commit_failure"):
        execute_confirmed_import(
            session_factory,
            snapshot=snapshot,
            approved_dry_run_id=dry_run_id,
            owner_id=owner_id,
            deck_id=deck_id,
            source_namespace=SOURCE_NAMESPACE,
            target_language="en",
            snapshot_captured_at=SNAPSHOT_AT,
            validator_version=VALIDATOR_VERSION,
            failure_injector=fail_after_commit,
        )

    apply_result, reconciliation = execute_confirmed_import(
        session_factory,
        snapshot=snapshot,
        approved_dry_run_id=dry_run_id,
        owner_id=owner_id,
        deck_id=deck_id,
        source_namespace=SOURCE_NAMESPACE,
        target_language="en",
        snapshot_captured_at=SNAPSHOT_AT,
        validator_version=VALIDATOR_VERSION,
    )

    assert apply_result.replayed is True
    assert reconciliation.status == "passed"
    with migrated_database_engine.connect() as connection:
        counts = connection.execute(
            text(
                """
                SELECT
                    (SELECT count(*) FROM learning_cards),
                    (SELECT count(*) FROM confirmed_import_runs),
                    (SELECT count(*) FROM confirmed_import_mappings)
                """
            )
        ).one()
    assert tuple(counts) == (1, 1, 1)


def test_confirmed_import_cli_writes_safe_reports_and_exact_replay(
    migrated_database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    owner_id, deck_id, snapshot, dry_run_id, _ = _arrange_approved_import(
        migrated_database_engine
    )
    report_path = tmp_path / "confirmed-import.json"
    reconciliation_path = tmp_path / "reconciliation.json"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv(
        "DATABASE_URL",
        migrated_database_engine.url.render_as_string(hide_password=False),
    )
    args = [
        "confirmed_imports",
        "--csv",
        str(FIXTURES / "import-valid-en.csv"),
        "--approved-dry-run-id",
        str(dry_run_id),
        "--owner-id",
        str(owner_id),
        "--deck-id",
        str(deck_id),
        "--source-namespace",
        SOURCE_NAMESPACE,
        "--target-language",
        "en",
        "--snapshot-captured-at",
        SNAPSHOT_AT.isoformat(),
        "--validator-version",
        VALIDATOR_VERSION,
        "--report",
        str(report_path),
        "--reconciliation-report",
        str(reconciliation_path),
    ]

    monkeypatch.setattr(sys, "argv", args)
    assert main() == 0
    first_report = json.loads(report_path.read_text(encoding="utf-8"))
    reconciliation_report = json.loads(reconciliation_path.read_text(encoding="utf-8"))

    assert first_report["replayed"] is False
    assert first_report["reconciliation_status"] == "passed"
    assert reconciliation_report["status"] == "passed"
    serialized = json.dumps([first_report, reconciliation_report])
    assert snapshot.rows[0].card_candidate["term"] not in serialized
    assert snapshot.rows[0].card_candidate["meaning"] not in serialized

    assert main() == 0
    replay_report = json.loads(report_path.read_text(encoding="utf-8"))
    assert replay_report["replayed"] is True
    assert (
        replay_report["confirmed_import_run_id"]
        == first_report["confirmed_import_run_id"]
    )


@pytest.mark.parametrize(
    ("mutation", "failed_check"),
    [
        (
            "UPDATE learning_cards SET meaning = 'tampered'",
            "canonical_content_hashes_match",
        ),
        (
            "DELETE FROM review_states",
            "fresh_review_states_match",
        ),
        (
            "DELETE FROM learning_card_tags",
            "tag_association_count_matches",
        ),
        (
            "DELETE FROM confirmed_import_mappings",
            "eligible_rows_match_mappings",
        ),
    ],
)
def test_reconciliation_marks_safe_failure_for_post_commit_mismatch(
    migrated_database_engine: Engine,
    mutation: str,
    failed_check: str,
) -> None:
    (
        _,
        _,
        snapshot,
        _,
        session_factory,
        apply_result,
    ) = _arrange_applied_import(migrated_database_engine)
    with migrated_database_engine.begin() as connection:
        connection.execute(text(mutation))

    result = reconcile_confirmed_import(
        session_factory,
        apply_result=apply_result,
        snapshot=snapshot,
    )

    assert result.status == "failed"
    assert result.checks[failed_check] is False
    assert f"reconciliation_{failed_check}_failed" in result.diagnostic_codes
    serialized = json.dumps(asdict(result))
    assert snapshot.rows[0].card_candidate["term"] not in serialized
    assert snapshot.rows[0].card_candidate["meaning"] not in serialized
    with migrated_database_engine.connect() as connection:
        status = connection.execute(
            text(
                "SELECT reconciliation_status FROM confirmed_import_runs "
                "WHERE id = :run_id"
            ),
            {"run_id": apply_result.run_id},
        ).scalar_one()
    assert status == "failed"
