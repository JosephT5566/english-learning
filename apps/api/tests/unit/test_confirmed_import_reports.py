"""Contract tests for checked-in sanitized Issue #23 evidence reports."""

import json
from datetime import UTC, datetime
from pathlib import Path

from app.imports import read_validated_csv_snapshot

ROOT = Path(__file__).parents[4]
FIXTURE = Path(__file__).parents[1] / "fixtures" / "import-valid-en.csv"
ARTIFACTS = ROOT / "doc" / "training" / "issues" / "issue-23"
SNAPSHOT_AT = datetime(2026, 9, 9, 4, 0, tzinfo=UTC)


def _read_json(name: str):
    return json.loads((ARTIFACTS / name).read_text(encoding="utf-8"))


def test_sanitized_reports_match_the_current_canonical_fixture() -> None:
    snapshot = read_validated_csv_snapshot(
        FIXTURE,
        source_namespace="sanitized-cutover-fixture-v1",
        target_language="en",
        snapshot_captured_at=SNAPSHOT_AT,
    )
    confirmed = _read_json("sanitized-confirmed-import-report.json")
    reconciliation = _read_json("sanitized-reconciliation-report.json")

    assert confirmed["source_snapshot_hash"] == snapshot.report.source_snapshot_hash
    assert confirmed["counts"] == {
        "archived_cards": 0,
        "card_tag_associations": 1,
        "eligible_rows": 1,
        "imported_cards": 1,
        "review_states": 1,
        "source_mappings": 1,
        "tags": 1,
    }
    assert reconciliation["expected_counts"] == reconciliation["actual_counts"]
    assert all(reconciliation["checks"].values())
    assert reconciliation["samples"][0]["source_identity_hash"] == (
        snapshot.rows[0].report.source_identity_hash
    )
    assert reconciliation["samples"][0]["canonical_content_hash"] == (
        snapshot.rows[0].report.content_hash
    )

    serialized = json.dumps([confirmed, reconciliation])
    assert snapshot.rows[0].card_candidate["term"] not in serialized
    assert snapshot.rows[0].card_candidate["meaning"] not in serialized
    assert snapshot.rows[0].card_candidate["example_sentence"] not in serialized


def test_replay_and_failure_evidence_records_required_recovery_properties() -> None:
    replay = _read_json("unchanged-replay-proof.json")
    failure = _read_json("failure-recovery-evidence.json")

    assert replay["first_apply_replayed"] is False
    assert replay["replay_replayed"] is True
    assert replay["same_confirmed_import_run_id"] is True
    assert replay["product_rows_unchanged"] is True
    assert replay["timestamps_unchanged"] is True
    assert replay["versions_unchanged"] is True
    assert len(failure["pre_commit_failure_points"]) == 7
    assert failure["pre_commit_result"]["all_product_mutations_rolled_back"] is True
    assert (
        failure["post_commit_interruption"]["retry_created_new_product_rows"] is False
    )
    assert failure["post_commit_interruption"]["retry_reconciliation_status"] == (
        "passed"
    )
    assert failure["reports_contained_raw_learning_content"] is False
