"""Unit tests for deterministic, content-safe legacy CSV validation."""

import csv
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.imports import (
    EXPECTED_FIELDS,
    LEGACY_FIELD_MAPPING,
    ImportBoundaryError,
    read_validated_csv_snapshot,
    validate_csv_snapshot,
)

FIXTURES = Path(__file__).parents[1] / "fixtures"
SANITIZED_REPORT = (
    Path(__file__).parents[4]
    / "doc"
    / "training"
    / "issues"
    / "issue-22"
    / "sanitized-dry-run-report.json"
)
SNAPSHOT_AT = datetime(2026, 9, 9, 4, 0, tzinfo=UTC)


def _validate(path: Path, language: str = "en"):
    return validate_csv_snapshot(
        path,
        source_namespace="legacy-google-sheet-cutover-v1",
        target_language=language,
        snapshot_captured_at=SNAPSHOT_AT,
    )


def _write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.writer(destination)
        writer.writerow(headers)
        writer.writerows(rows)


def _blank_row(**values: str) -> list[str]:
    defaults = {
        "id": "synthetic-id",
        "content": "synthetic term",
        "type": "phrase",
        "chineseExplain": "synthetic meaning",
        "status": "active",
        "reviewStage": "1",
        "easeFactor": "2.5",
        "createdDate": "2026-09-01T00:00:00Z",
    }
    defaults.update(values)
    return [defaults.get(field, "") for field in EXPECTED_FIELDS]


def test_all_legacy_fields_have_an_explicit_mapping() -> None:
    assert set(LEGACY_FIELD_MAPPING) == set(EXPECTED_FIELDS)
    assert len(LEGACY_FIELD_MAPPING) == 21


@pytest.mark.parametrize(
    ("fixture", "language"),
    [("import-valid-en.csv", "en"), ("import-valid-ja.csv", "ja")],
)
def test_valid_multilingual_reports_are_deterministic(
    fixture: str, language: str
) -> None:
    first = _validate(FIXTURES / fixture, language)
    second = _validate(FIXTURES / fixture, language)

    assert asdict(first) == asdict(second)
    assert first.status == "completed"
    assert first.total_rows == 1
    assert first.accepted_rows == 1
    assert first.repaired_rows == 0
    assert first.rejected_rows == 0
    assert first.items[0].diagnostics[0].code == "legacy_schedule_reset"


def test_headers_are_validated_without_echoing_unknown_names(tmp_path: Path) -> None:
    secret_header = "private-secret-header"
    headers = [field for field in EXPECTED_FIELDS if field != "content"]
    headers.append(secret_header)
    path = tmp_path / "invalid-headers.csv"
    _write_csv(path, headers, [["" for _ in headers]])

    report = _validate(path)
    serialized = json.dumps(asdict(report))

    assert report.status == "rejected"
    assert report.rejected_rows == 1
    assert {(item.code, item.field) for item in report.diagnostics} == {
        ("missing_header", "content"),
        ("unknown_headers", "$headers"),
    }
    assert secret_header not in serialized


def test_duplicate_ids_and_malformed_values_are_row_level(tmp_path: Path) -> None:
    path = tmp_path / "invalid-rows.csv"
    rows = [
        _blank_row(
            id="duplicate",
            lessonDate="not-a-date",
            chineseExplain="",
            status="mystery",
            reviewStage="99",
            easeFactor="nan",
        ),
        _blank_row(id="duplicate", intervalDays="-1", nextReview="bad-date"),
    ]
    _write_csv(path, list(EXPECTED_FIELDS), rows)

    report = _validate(path)
    first_codes = {(item.code, item.field) for item in report.items[0].diagnostics}
    second_codes = {(item.code, item.field) for item in report.items[1].diagnostics}

    assert report.rejected_rows == 2
    assert ("duplicate_source_id", "id") in first_codes
    assert ("required", "chineseExplain") in first_codes
    assert ("malformed_date", "lessonDate") in first_codes
    assert ("unsupported_value", "status") in first_codes
    assert ("legacy_schedule_out_of_range", "reviewStage") in first_codes
    assert ("legacy_schedule_out_of_range", "easeFactor") in first_codes
    assert ("legacy_schedule_out_of_range", "intervalDays") in second_codes
    assert ("legacy_schedule_invalid", "nextReview") in second_codes


def test_unicode_and_collection_repairs_are_diagnostic_only(tmp_path: Path) -> None:
    path = tmp_path / "repairs.csv"
    _write_csv(
        path,
        list(EXPECTED_FIELDS),
        [
            _blank_row(
                content=" cafe\u0301 ",
                type="vocabulary (n)",
                synonyms="same, same, ",
                tags="Fixture, fixture",
                status="",
                createdDate="",
            )
        ],
    )

    report = _validate(path)
    codes = {item.code for item in report.items[0].diagnostics}

    assert report.repaired_rows == 1
    assert "unicode_or_whitespace_normalized" in codes
    assert "part_of_speech_preserved_as_other" in codes
    assert "empty_items_removed" in codes
    assert "duplicate_items_removed" in codes
    assert "blank_status_defaulted_active" in codes
    assert "created_at_defaulted" in codes


def test_sheet_slash_dates_are_interpreted_in_taipei_without_repair(
    tmp_path: Path,
) -> None:
    path = tmp_path / "slash-dates.csv"
    _write_csv(
        path,
        list(EXPECTED_FIELDS),
        [
            _blank_row(
                lessonDate="2026/9/1",
                createdDate="2026/9/1",
                lastReview="2026/9/1",
                nextReview="2026/9/2",
            )
        ],
    )

    report = _validate(path)

    assert report.accepted_rows == 1
    assert report.repaired_rows == 0


def test_report_never_contains_raw_private_learning_content(tmp_path: Path) -> None:
    path = tmp_path / "private.csv"
    private_values = {
        "content": "DO-NOT-EXPOSE-TERM",
        "chineseExplain": "DO-NOT-EXPOSE-MEANING",
        "note": "DO-NOT-EXPOSE-NOTE",
    }
    _write_csv(path, list(EXPECTED_FIELDS), [_blank_row(**private_values)])

    serialized = json.dumps(asdict(_validate(path)), ensure_ascii=False)

    assert all(value not in serialized for value in private_values.values())


def test_confirmed_import_can_reuse_private_canonical_candidates_in_memory(
    tmp_path: Path,
) -> None:
    path = tmp_path / "private.csv"
    _write_csv(
        path,
        list(EXPECTED_FIELDS),
        [
            _blank_row(
                content=" private term ",
                chineseExplain=" private meaning ",
                tags=" Fixture, fixture, Second ",
            )
        ],
    )

    snapshot = read_validated_csv_snapshot(
        path,
        source_namespace="legacy-google-sheet-cutover-v1",
        target_language="en",
        snapshot_captured_at=SNAPSHOT_AT,
    )

    assert snapshot.rows[0].card_candidate["term"] == "private term"
    assert snapshot.rows[0].card_candidate["meaning"] == "private meaning"
    assert snapshot.rows[0].card_candidate["tags"] == ["Fixture", "Second"]
    assert snapshot.rows[0].report is snapshot.report.items[0]
    assert "private term" not in json.dumps(asdict(snapshot.report))


def test_content_hash_tracks_mapped_content_not_ignored_legacy_schedule(
    tmp_path: Path,
) -> None:
    first_path = tmp_path / "first.csv"
    second_path = tmp_path / "second.csv"
    _write_csv(first_path, list(EXPECTED_FIELDS), [_blank_row(reviewStage="1")])
    _write_csv(second_path, list(EXPECTED_FIELDS), [_blank_row(reviewStage="5")])

    first = _validate(first_path)
    second = _validate(second_path)

    assert first.source_snapshot_hash != second.source_snapshot_hash
    assert first.items[0].source_identity_hash == second.items[0].source_identity_hash
    assert first.items[0].content_hash == second.items[0].content_hash


def test_checked_in_sanitized_report_matches_current_validator() -> None:
    checked_in = json.loads(SANITIZED_REPORT.read_text(encoding="utf-8"))

    for language in ("en", "ja"):
        generated = validate_csv_snapshot(
            FIXTURES / f"import-valid-{language}.csv",
            source_namespace=checked_in["source_namespace"],
            target_language=language,
            snapshot_captured_at=datetime.fromisoformat(
                checked_in["snapshot_captured_at"]
            ),
        )
        expected = checked_in["reports"][language]
        assert generated.source_snapshot_hash == expected["source_snapshot_hash"]
        assert (
            generated.items[0].source_identity_hash
            == expected["items"][0]["source_identity_hash"]
        )
        assert generated.items[0].content_hash == expected["items"][0]["content_hash"]
        assert generated.accepted_rows == expected["accepted_rows"]
        assert generated.repaired_rows == expected["repaired_rows"]
        assert generated.rejected_rows == expected["rejected_rows"]


@pytest.mark.parametrize("language", ["zh", "EN", ""])
def test_unsupported_languages_fail_safely(language: str) -> None:
    with pytest.raises(ImportBoundaryError, match="target_language_unsupported"):
        _validate(FIXTURES / "import-valid-en.csv", language)
