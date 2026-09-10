"""One-time, read-only CSV migration validation and audit persistence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import ConfigurationError, load_settings
from app.database import (
    create_database_engine,
    create_database_session_factory,
    database_transaction,
    dispose_database_engine,
)

VALIDATOR_VERSION = "csv-dry-run-v1"
EXPECTED_FIELDS = (
    "id",
    "lessonDate",
    "content",
    "type",
    "phonics",
    "chineseExplain",
    "engExplain",
    "synonyms",
    "antonyms",
    "tags",
    "note",
    "supplementary",
    "example",
    "status",
    "reviewStage",
    "easeFactor",
    "intervalDays",
    "lastReview",
    "nextReview",
    "createdDate",
    "overdueDays",
)
SUPPORTED_LANGUAGES = {"en", "ja"}
LEGACY_FIELD_MAPPING = {
    "id": "hashed source identity; never a card primary key",
    "lessonDate": "learning_cards.learned_on in Asia/Taipei",
    "content": "learning_cards.term",
    "type": "learning_cards.part_of_speech and part_of_speech_detail",
    "phonics": "learning_cards.pronunciation",
    "chineseExplain": "learning_cards.meaning",
    "engExplain": "learning_cards.target_language_definition",
    "synonyms": "learning_cards.synonyms",
    "antonyms": "learning_cards.antonyms",
    "tags": "owned tags and learning_card_tags",
    "note": "learning_cards.note",
    "supplementary": "learning_cards.supplementary_note",
    "example": "learning_cards.example_sentence",
    "status": "learning_cards.archived_at",
    "reviewStage": "validated then reset by fresh scheduling policy",
    "easeFactor": "validated then reset by fresh scheduling policy",
    "intervalDays": "validated then reset by fresh scheduling policy",
    "lastReview": "validated then reset by fresh scheduling policy",
    "nextReview": "validated then reset by fresh scheduling policy",
    "createdDate": "learning_cards.created_at or snapshot timestamp fallback",
    "overdueDays": "validated diagnostic only; derived at query time",
}
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ROWS = 10_000
MAX_CELL_CHARACTERS = 20_000
MAX_DIAGNOSTICS_PER_ROW = 12
MAX_RUN_DIAGNOSTICS = 12
TAIPEI = ZoneInfo("Asia/Taipei")

Outcome = Literal["accepted", "repaired", "rejected"]
Severity = Literal["info", "repair", "error"]


class ImportBoundaryError(RuntimeError):
    """Safe import failure that never contains source row content."""


@dataclass(frozen=True)
class Diagnostic:
    """Safe machine-readable diagnostic without a rejected value."""

    code: str
    field: str
    severity: Severity


@dataclass
class RowReport:
    """Deterministic result for one CSV data row."""

    row_number: int
    source_identity_hash: str
    content_hash: str
    outcome: Outcome
    diagnostics: list[Diagnostic]
    diagnostic_count: int = 0
    diagnostics_truncated: bool = False


@dataclass(frozen=True)
class DryRunReport:
    """Bounded sanitized dry-run report."""

    validator_version: str
    source_namespace: str
    source_snapshot_hash: str
    target_language: str
    snapshot_captured_at: str
    status: Literal["completed", "rejected"]
    total_rows: int
    accepted_rows: int
    repaired_rows: int
    rejected_rows: int
    diagnostic_count: int
    diagnostics: list[Diagnostic]
    diagnostics_truncated: bool
    items: list[RowReport]


@dataclass(frozen=True, repr=False)
class CanonicalImportRow:
    """Private in-memory canonical content paired with its safe row report."""

    report: RowReport
    card_candidate: dict[str, object]


@dataclass(frozen=True, repr=False)
class ValidatedCsvSnapshot:
    """Validated report plus private candidates that must never be persisted as audit."""

    report: DryRunReport
    rows: list[CanonicalImportRow]


def _sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip())


def _identity_key(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def normalize_collection_identity(value: str) -> str:
    """Return the shared normalized identity used by tags and list values."""

    return _identity_key(value)


def _append_diagnostic(row: RowReport, diagnostic: Diagnostic) -> None:
    row.diagnostic_count += 1
    if diagnostic.severity == "error":
        row.outcome = "rejected"
    elif diagnostic.severity == "repair" and row.outcome == "accepted":
        row.outcome = "repaired"
    if len(row.diagnostics) < MAX_DIAGNOSTICS_PER_ROW:
        row.diagnostics.append(diagnostic)
    else:
        row.diagnostics_truncated = True


def _append_run_diagnostic(
    diagnostics: list[Diagnostic], diagnostic: Diagnostic
) -> tuple[int, bool]:
    if len(diagnostics) < MAX_RUN_DIAGNOSTICS:
        diagnostics.append(diagnostic)
        return 1, False
    return 1, True


def _parse_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = datetime.strptime(value, "%Y/%m/%d").replace(tzinfo=TAIPEI)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TAIPEI)
    return parsed.astimezone(UTC)


def _parse_calendar_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return _parse_datetime(value).astimezone(TAIPEI).date()


def _validate_length(
    row: RowReport,
    field: str,
    value: str,
    maximum: int,
    *,
    required: bool = False,
) -> None:
    if required and not value:
        _append_diagnostic(row, Diagnostic("required", field, "error"))
    elif len(value) > maximum:
        _append_diagnostic(row, Diagnostic("too_long", field, "error"))


def _validate_array(
    row: RowReport, field: str, value: str, item_limit: int
) -> list[str]:
    if not value:
        return []
    raw_parts = value.split(",")
    parts = [_normalize(part) for part in raw_parts]
    nonempty = [part for part in parts if part]
    if len(nonempty) != len(parts):
        _append_diagnostic(row, Diagnostic("empty_items_removed", field, "repair"))

    seen: set[str] = set()
    unique: list[str] = []
    for part in nonempty:
        key = _identity_key(part)
        if key in seen:
            continue
        seen.add(key)
        unique.append(part)
    if len(unique) != len(nonempty):
        _append_diagnostic(row, Diagnostic("duplicate_items_removed", field, "repair"))
    if len(unique) > 20:
        _append_diagnostic(row, Diagnostic("too_many_items", field, "error"))
    if any(len(part) > item_limit for part in unique):
        _append_diagnostic(row, Diagnostic("item_too_long", field, "error"))
    return unique


def _part_of_speech(value: str) -> tuple[str | None, str | None]:
    normalized = value.casefold()
    if not normalized:
        return None, None
    if normalized == "adv":
        return "adverb", None
    if normalized in {
        "noun",
        "verb",
        "adjective",
        "adverb",
        "pronoun",
        "determiner",
        "preposition",
        "conjunction",
        "interjection",
        "particle",
        "auxiliary",
        "numeral",
        "phrase",
        "other",
    }:
        return normalized, value if normalized == "other" else None
    return "other", value


def _validate_integer_range(
    row: RowReport, field: str, value: str, minimum: int, maximum: int | None
) -> None:
    if not value:
        _append_diagnostic(row, Diagnostic("legacy_schedule_missing", field, "repair"))
        return
    try:
        parsed = int(value)
    except ValueError:
        _append_diagnostic(row, Diagnostic("legacy_schedule_invalid", field, "repair"))
        return
    if parsed < minimum or (maximum is not None and parsed > maximum):
        _append_diagnostic(
            row, Diagnostic("legacy_schedule_out_of_range", field, "repair")
        )


def _validate_decimal_range(
    row: RowReport, field: str, value: str, minimum: Decimal, maximum: Decimal
) -> None:
    if not value:
        _append_diagnostic(row, Diagnostic("legacy_schedule_missing", field, "repair"))
        return
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        _append_diagnostic(row, Diagnostic("legacy_schedule_invalid", field, "repair"))
        return
    if not parsed.is_finite() or parsed < minimum or parsed > maximum:
        _append_diagnostic(
            row, Diagnostic("legacy_schedule_out_of_range", field, "repair")
        )


def _validate_schedule(row: RowReport, values: dict[str, str]) -> None:
    _validate_integer_range(row, "reviewStage", values["reviewStage"], 1, 5)
    _validate_decimal_range(
        row, "easeFactor", values["easeFactor"], Decimal("1.3"), Decimal("2.5")
    )
    if values["intervalDays"]:
        _validate_integer_range(row, "intervalDays", values["intervalDays"], 0, None)

    parsed_dates: dict[str, datetime] = {}
    for field in ("lastReview", "nextReview"):
        if not values[field]:
            continue
        try:
            parsed_dates[field] = _parse_datetime(values[field])
        except ValueError:
            _append_diagnostic(
                row, Diagnostic("legacy_schedule_invalid", field, "repair")
            )
    if set(parsed_dates) == {"lastReview", "nextReview"} and (
        parsed_dates["nextReview"] < parsed_dates["lastReview"]
    ):
        _append_diagnostic(
            row, Diagnostic("legacy_schedule_conflict", "$schedule", "repair")
        )
    if bool(values["lastReview"]) != bool(values["nextReview"]):
        _append_diagnostic(
            row, Diagnostic("legacy_schedule_incomplete", "$schedule", "repair")
        )
    if values["overdueDays"]:
        try:
            int(values["overdueDays"])
        except ValueError:
            _append_diagnostic(
                row, Diagnostic("derived_value_invalid", "overdueDays", "repair")
            )
    _append_diagnostic(row, Diagnostic("legacy_schedule_reset", "$schedule", "info"))


def _validate_row(
    row_number: int,
    header: list[str],
    cells: list[str],
    source_namespace: str,
    target_language: str,
    snapshot_captured_at: datetime,
    header_is_valid: bool,
) -> CanonicalImportRow:
    normalized_cells = [_normalize(value) for value in cells]
    first_values: dict[str, str] = {}
    first_raw_values: dict[str, str] = {}
    for field, raw_value, value in zip(header, cells, normalized_cells, strict=False):
        first_values.setdefault(field, value)
        first_raw_values.setdefault(field, raw_value)
    values = {field: first_values.get(field, "") for field in EXPECTED_FIELDS}
    legacy_id = values["id"]
    identity_material = legacy_id if legacy_id else f"missing-row-{row_number}"
    result = RowReport(
        row_number=row_number,
        source_identity_hash=_sha256(
            [source_namespace, unicodedata.normalize("NFC", identity_material)]
        ),
        content_hash="0" * 64,
        outcome="accepted",
        diagnostics=[],
    )

    if not header_is_valid:
        _append_diagnostic(result, Diagnostic("invalid_headers", "$headers", "error"))
    if len(cells) != len(header):
        _append_diagnostic(result, Diagnostic("column_count_mismatch", "$row", "error"))

    for field, raw in first_raw_values.items():
        if field in EXPECTED_FIELDS and raw != _normalize(raw):
            _append_diagnostic(
                result, Diagnostic("unicode_or_whitespace_normalized", field, "repair")
            )

    _validate_length(result, "id", values["id"], 255, required=True)
    _validate_length(result, "content", values["content"], 255, required=True)
    _validate_length(
        result, "chineseExplain", values["chineseExplain"], 2000, required=True
    )
    for field, limit in (
        ("phonics", 255),
        ("engExplain", 2000),
        ("note", 4000),
        ("supplementary", 4000),
        ("example", 1000),
    ):
        _validate_length(result, field, values[field], limit)

    if values["lessonDate"]:
        try:
            _parse_calendar_date(values["lessonDate"])
        except ValueError:
            _append_diagnostic(
                result, Diagnostic("malformed_date", "lessonDate", "error")
            )
    if values["createdDate"]:
        try:
            _parse_datetime(values["createdDate"])
        except ValueError:
            _append_diagnostic(
                result, Diagnostic("created_at_replaced", "createdDate", "repair")
            )
    else:
        _append_diagnostic(
            result, Diagnostic("created_at_defaulted", "createdDate", "repair")
        )

    status = values["status"].casefold()
    if not status:
        _append_diagnostic(
            result, Diagnostic("blank_status_defaulted_active", "status", "repair")
        )
    elif status not in {"active", "inactive", "deleted"}:
        _append_diagnostic(result, Diagnostic("unsupported_value", "status", "error"))

    part_of_speech = values["type"].casefold()
    if part_of_speech == "adv":
        _append_diagnostic(
            result, Diagnostic("part_of_speech_alias_mapped", "type", "repair")
        )
    elif part_of_speech and part_of_speech not in {
        "noun",
        "verb",
        "adjective",
        "adverb",
        "pronoun",
        "determiner",
        "preposition",
        "conjunction",
        "interjection",
        "particle",
        "auxiliary",
        "numeral",
        "phrase",
        "other",
    }:
        if len(values["type"]) > 100:
            _append_diagnostic(result, Diagnostic("too_long", "type", "error"))
        else:
            _append_diagnostic(
                result,
                Diagnostic("part_of_speech_preserved_as_other", "type", "repair"),
            )

    synonyms = _validate_array(result, "synonyms", values["synonyms"], 255)
    antonyms = _validate_array(result, "antonyms", values["antonyms"], 255)
    tags = _validate_array(result, "tags", values["tags"], 50)
    _validate_schedule(result, values)

    try:
        learned_on = (
            _parse_calendar_date(values["lessonDate"]).isoformat()
            if values["lessonDate"]
            else None
        )
    except ValueError:
        learned_on = None
    try:
        created_at = (
            _parse_datetime(values["createdDate"]).isoformat()
            if values["createdDate"]
            else snapshot_captured_at.astimezone(UTC).isoformat()
        )
    except ValueError:
        created_at = snapshot_captured_at.astimezone(UTC).isoformat()
    canonical_part_of_speech, part_of_speech_detail = _part_of_speech(values["type"])
    canonical_candidate = {
        "target_language": target_language,
        "term": values["content"],
        "meaning": values["chineseExplain"],
        "reading": None,
        "pronunciation": values["phonics"] or None,
        "romanization": None,
        "target_language_definition": values["engExplain"] or None,
        "synonyms": synonyms,
        "antonyms": antonyms,
        "tags": tags,
        "note": values["note"] or None,
        "supplementary_note": values["supplementary"] or None,
        "example_sentence": values["example"] or None,
        "example_translation": None,
        "example_source": None,
        "part_of_speech": canonical_part_of_speech,
        "part_of_speech_detail": part_of_speech_detail,
        "learned_on": learned_on,
        "archived": values["status"].casefold() in {"inactive", "deleted"},
        "created_at": created_at,
        "fresh_review_state": {
            "review_stage": 1,
            "ease_factor": "2.50",
            "interval_days": 0,
            "last_reviewed_at": None,
            "next_review_at": snapshot_captured_at.astimezone(UTC).isoformat(),
            "version": 1,
        },
    }
    result.content_hash = _sha256(canonical_candidate)

    return CanonicalImportRow(report=result, card_candidate=canonical_candidate)


def read_validated_csv_snapshot(
    path: Path,
    *,
    source_namespace: str,
    target_language: str,
    snapshot_captured_at: datetime,
) -> ValidatedCsvSnapshot:
    """Validate a bounded CSV and retain private candidates only in process memory."""

    namespace = _normalize(source_namespace)
    if not namespace or len(namespace) > 100:
        raise ImportBoundaryError("source_namespace_invalid")
    if target_language not in SUPPORTED_LANGUAGES:
        raise ImportBoundaryError("target_language_unsupported")
    if snapshot_captured_at.tzinfo is None:
        raise ImportBoundaryError("snapshot_captured_at_timezone_required")
    try:
        if not path.is_file():
            raise ImportBoundaryError("csv_not_found")
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ImportBoundaryError("csv_too_large")
    except OSError:
        raise ImportBoundaryError("csv_unreadable") from None

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.reader(source)
            header = next(reader, None)
            if header is None:
                raise ImportBoundaryError("csv_empty")
            rows = list(reader)
    except UnicodeDecodeError:
        raise ImportBoundaryError("csv_not_utf8") from None
    except csv.Error:
        raise ImportBoundaryError("csv_malformed") from None
    except OSError:
        raise ImportBoundaryError("csv_unreadable") from None

    if len(rows) > MAX_ROWS:
        raise ImportBoundaryError("csv_too_many_rows")
    if any(len(cell) > MAX_CELL_CHARACTERS for row in rows for cell in row):
        raise ImportBoundaryError("csv_cell_too_large")

    normalized_header = [_normalize(field) for field in header]
    counts = Counter(normalized_header)
    missing = [field for field in EXPECTED_FIELDS if field not in counts]
    unknown_count = sum(field not in EXPECTED_FIELDS for field in normalized_header)
    duplicate_count = sum(count - 1 for count in counts.values() if count > 1)
    run_diagnostics: list[Diagnostic] = []
    run_diagnostic_count = 0
    run_truncated = False
    for field in missing:
        added, truncated = _append_run_diagnostic(
            run_diagnostics, Diagnostic("missing_header", field, "error")
        )
        run_diagnostic_count += added
        run_truncated = run_truncated or truncated
    if unknown_count:
        added, truncated = _append_run_diagnostic(
            run_diagnostics, Diagnostic("unknown_headers", "$headers", "error")
        )
        run_diagnostic_count += added
        run_truncated = run_truncated or truncated
    if duplicate_count:
        added, truncated = _append_run_diagnostic(
            run_diagnostics, Diagnostic("duplicate_headers", "$headers", "error")
        )
        run_diagnostic_count += added
        run_truncated = run_truncated or truncated
    header_is_valid = not (missing or unknown_count or duplicate_count)

    canonical_snapshot = {
        "target_language": target_language,
        "snapshot_captured_at": snapshot_captured_at.astimezone(UTC).isoformat(),
        "header": normalized_header,
        "rows": [[_normalize(cell) for cell in row] for row in rows],
    }
    snapshot_hash = _sha256(canonical_snapshot)
    validated_rows = [
        _validate_row(
            index,
            normalized_header,
            row,
            namespace,
            target_language,
            snapshot_captured_at,
            header_is_valid,
        )
        for index, row in enumerate(rows, start=2)
    ]
    items = [row.report for row in validated_rows]

    identities = Counter(item.source_identity_hash for item in items)
    for item in items:
        if identities[item.source_identity_hash] > 1:
            _append_diagnostic(item, Diagnostic("duplicate_source_id", "id", "error"))

    outcome_counts = Counter(item.outcome for item in items)
    diagnostic_count = run_diagnostic_count + sum(
        item.diagnostic_count for item in items
    )
    return ValidatedCsvSnapshot(
        report=DryRunReport(
            validator_version=VALIDATOR_VERSION,
            source_namespace=namespace,
            source_snapshot_hash=snapshot_hash,
            target_language=target_language,
            snapshot_captured_at=snapshot_captured_at.astimezone(UTC).isoformat(),
            status="completed" if header_is_valid else "rejected",
            total_rows=len(items),
            accepted_rows=outcome_counts["accepted"],
            repaired_rows=outcome_counts["repaired"],
            rejected_rows=outcome_counts["rejected"],
            diagnostic_count=diagnostic_count,
            diagnostics=run_diagnostics,
            diagnostics_truncated=run_truncated,
            items=items,
        ),
        rows=validated_rows,
    )


def validate_csv_snapshot(
    path: Path,
    *,
    source_namespace: str,
    target_language: str,
    snapshot_captured_at: datetime,
) -> DryRunReport:
    """Validate a bounded CSV and return only its content-safe report."""

    return read_validated_csv_snapshot(
        path,
        source_namespace=source_namespace,
        target_language=target_language,
        snapshot_captured_at=snapshot_captured_at,
    ).report


def persist_dry_run(
    session: Session,
    *,
    report: DryRunReport,
    owner_id: int,
    deck_id: UUID,
) -> tuple[UUID, bool]:
    """Persist only the dry-run audit and return its ID plus replay status."""

    deck_language = session.execute(
        text(
            "SELECT target_language FROM learning_decks "
            "WHERE id = :deck_id AND owner_id = :owner_id"
        ),
        {"deck_id": deck_id, "owner_id": owner_id},
    ).scalar_one_or_none()
    if deck_language is None:
        raise ImportBoundaryError("target_deck_not_found")
    if deck_language != report.target_language:
        raise ImportBoundaryError("target_language_conflict")

    existing_id = session.execute(
        text(
            "SELECT id FROM import_runs "
            "WHERE owner_id = :owner_id "
            "AND source_namespace = :source_namespace "
            "AND source_snapshot_hash = :source_snapshot_hash "
            "AND validator_version = :validator_version"
        ),
        {
            "owner_id": owner_id,
            "source_namespace": report.source_namespace,
            "source_snapshot_hash": report.source_snapshot_hash,
            "validator_version": report.validator_version,
        },
    ).scalar_one_or_none()
    if existing_id is not None:
        existing_deck_id = session.execute(
            text("SELECT deck_id FROM import_runs WHERE id = :run_id"),
            {"run_id": existing_id},
        ).scalar_one()
        if existing_deck_id != deck_id:
            raise ImportBoundaryError("source_snapshot_target_conflict")
        return existing_id, True

    run_id = session.execute(
        text(
            """
            INSERT INTO import_runs (
                owner_id, deck_id, source_namespace, source_snapshot_hash,
                validator_version, target_language, snapshot_captured_at, status,
                total_rows, accepted_rows, repaired_rows, rejected_rows,
                diagnostic_count, diagnostics, diagnostics_truncated, completed_at
            ) VALUES (
                :owner_id, :deck_id, :source_namespace, :source_snapshot_hash,
                :validator_version, :target_language, :snapshot_captured_at, :status,
                :total_rows, :accepted_rows, :repaired_rows, :rejected_rows,
                :diagnostic_count, CAST(:diagnostics AS jsonb),
                :diagnostics_truncated, CURRENT_TIMESTAMP
            ) RETURNING id
            """
        ),
        {
            "owner_id": owner_id,
            "deck_id": deck_id,
            "source_namespace": report.source_namespace,
            "source_snapshot_hash": report.source_snapshot_hash,
            "validator_version": report.validator_version,
            "target_language": report.target_language,
            "snapshot_captured_at": datetime.fromisoformat(report.snapshot_captured_at),
            "status": report.status,
            "total_rows": report.total_rows,
            "accepted_rows": report.accepted_rows,
            "repaired_rows": report.repaired_rows,
            "rejected_rows": report.rejected_rows,
            "diagnostic_count": report.diagnostic_count,
            "diagnostics": json.dumps([asdict(item) for item in report.diagnostics]),
            "diagnostics_truncated": report.diagnostics_truncated,
        },
    ).scalar_one()
    for item in report.items:
        session.execute(
            text(
                """
                INSERT INTO import_items (
                    run_id, row_number, source_identity_hash, content_hash, outcome,
                    diagnostic_count, diagnostics, diagnostics_truncated
                ) VALUES (
                    :run_id, :row_number, :source_identity_hash, :content_hash,
                    :outcome, :diagnostic_count, CAST(:diagnostics AS jsonb),
                    :diagnostics_truncated
                )
                """
            ),
            {
                "run_id": run_id,
                "row_number": item.row_number,
                "source_identity_hash": item.source_identity_hash,
                "content_hash": item.content_hash,
                "outcome": item.outcome,
                "diagnostic_count": item.diagnostic_count,
                "diagnostics": json.dumps(
                    [asdict(diagnostic) for diagnostic in item.diagnostics]
                ),
                "diagnostics_truncated": item.diagnostics_truncated,
            },
        )
    return run_id, False


def report_as_dict(
    report: DryRunReport, run_id: UUID, replayed: bool
) -> dict[str, object]:
    """Return a JSON-serializable report containing no raw learning content."""

    payload = asdict(report)
    payload["run_id"] = str(run_id)
    payload["replayed"] = replayed
    return payload


def _parse_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a legacy Sheet CSV snapshot")
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--source-namespace", required=True)
    parser.add_argument("--owner-id", required=True, type=int)
    parser.add_argument("--deck-id", required=True, type=UUID)
    parser.add_argument(
        "--target-language", required=True, choices=sorted(SUPPORTED_LANGUAGES)
    )
    parser.add_argument(
        "--snapshot-captured-at", required=True, type=datetime.fromisoformat
    )
    parser.add_argument("--report", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    """Run the local dry-run CLI with a short-lived database transaction."""

    args = _parse_cli_args()
    try:
        report = validate_csv_snapshot(
            args.csv,
            source_namespace=args.source_namespace,
            target_language=args.target_language,
            snapshot_captured_at=args.snapshot_captured_at,
        )
        settings = load_settings()
        engine = create_database_engine(settings)
        session_factory = create_database_session_factory(engine)
        try:
            with database_transaction(session_factory) as session:
                run_id, replayed = persist_dry_run(
                    session,
                    report=report,
                    owner_id=args.owner_id,
                    deck_id=args.deck_id,
                )
        finally:
            dispose_database_engine(engine)
        args.report.write_text(
            json.dumps(
                report_as_dict(report, run_id, replayed),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    except ImportBoundaryError as error:
        print(str(error), file=sys.stderr)
        return 2
    except SQLAlchemyError:
        print("database_unavailable", file=sys.stderr)
        return 2
    except ConfigurationError as error:
        print(str(error), file=sys.stderr)
        return 2
    except OSError:
        print("report_write_failed", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
