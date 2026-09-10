"""Transactional confirmed import of an approved legacy CSV snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.imports import CanonicalImportRow, ValidatedCsvSnapshot


class ConfirmedImportError(RuntimeError):
    """Bounded confirmed-import failure without private source content."""

    def __init__(self, code: str, *, row_number: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.row_number = row_number


@dataclass(frozen=True, repr=False)
class ApprovedImportItem:
    """Approved audit item paired with its re-read private canonical candidate."""

    import_item_id: int
    row: CanonicalImportRow


@dataclass(frozen=True, repr=False)
class ApprovedImportSnapshot:
    """Locked and fully reproduced dry run ready for confirmed application."""

    dry_run_id: UUID
    owner_id: int
    deck_id: UUID
    source_namespace: str
    snapshot_captured_at: datetime
    items: list[ApprovedImportItem]


def verify_approved_snapshot(
    session: Session,
    *,
    snapshot: ValidatedCsvSnapshot,
    approved_dry_run_id: UUID,
    owner_id: int,
    deck_id: UUID,
    source_namespace: str,
    target_language: str,
    snapshot_captured_at: datetime,
    validator_version: str,
) -> ApprovedImportSnapshot:
    """Lock and reproduce an eligible dry run before any product mutation."""

    dry_run = session.execute(
        text(
            """
            SELECT id, owner_id, deck_id, source_namespace, source_snapshot_hash,
                   validator_version, target_language, snapshot_captured_at,
                   status, total_rows, accepted_rows, repaired_rows, rejected_rows
            FROM import_runs
            WHERE id = :dry_run_id
              AND owner_id = :owner_id
              AND deck_id = :deck_id
            FOR UPDATE
            """
        ),
        {
            "dry_run_id": approved_dry_run_id,
            "owner_id": owner_id,
            "deck_id": deck_id,
        },
    ).one_or_none()
    if dry_run is None:
        raise ConfirmedImportError("approved_dry_run_not_found")

    deck = session.execute(
        text(
            """
            SELECT target_language, archived_at
            FROM learning_decks
            WHERE id = :deck_id AND owner_id = :owner_id
            FOR UPDATE
            """
        ),
        {"deck_id": deck_id, "owner_id": owner_id},
    ).one_or_none()
    if deck is None:
        raise ConfirmedImportError("target_deck_not_found")
    if deck.archived_at is not None:
        raise ConfirmedImportError("target_deck_archived")
    if deck.target_language != target_language:
        raise ConfirmedImportError("target_language_conflict")

    report = snapshot.report
    if dry_run.status != "completed":
        raise ConfirmedImportError("approved_dry_run_not_completed")
    if dry_run.rejected_rows != 0:
        raise ConfirmedImportError("approved_dry_run_has_rejections")
    if report.rejected_rows != 0:
        raise ConfirmedImportError("current_snapshot_has_rejections")

    expected_metadata = (
        source_namespace,
        target_language,
        snapshot_captured_at,
        validator_version,
    )
    dry_run_metadata = (
        dry_run.source_namespace,
        dry_run.target_language,
        dry_run.snapshot_captured_at,
        dry_run.validator_version,
    )
    report_metadata = (
        report.source_namespace,
        report.target_language,
        datetime.fromisoformat(report.snapshot_captured_at),
        report.validator_version,
    )
    if dry_run_metadata != expected_metadata or report_metadata != expected_metadata:
        raise ConfirmedImportError("approved_dry_run_metadata_mismatch")
    if dry_run.source_snapshot_hash != report.source_snapshot_hash:
        raise ConfirmedImportError("source_snapshot_hash_mismatch")

    approved_items = session.execute(
        text(
            """
            SELECT id, row_number, source_identity_hash, content_hash, outcome
            FROM import_items
            WHERE run_id = :dry_run_id
            ORDER BY row_number
            """
        ),
        {"dry_run_id": approved_dry_run_id},
    ).all()
    if (
        dry_run.total_rows != len(approved_items)
        or dry_run.total_rows != len(snapshot.rows)
        or dry_run.total_rows != dry_run.accepted_rows + dry_run.repaired_rows
    ):
        raise ConfirmedImportError("approved_item_count_mismatch")

    verified_items: list[ApprovedImportItem] = []
    for approved_item, current_row in zip(approved_items, snapshot.rows, strict=True):
        row_report = current_row.report
        if approved_item.row_number != row_report.row_number:
            raise ConfirmedImportError(
                "approved_row_number_mismatch", row_number=row_report.row_number
            )
        if approved_item.source_identity_hash != row_report.source_identity_hash:
            raise ConfirmedImportError(
                "source_identity_hash_mismatch", row_number=row_report.row_number
            )
        if approved_item.content_hash != row_report.content_hash:
            raise ConfirmedImportError(
                "canonical_content_hash_mismatch", row_number=row_report.row_number
            )
        if approved_item.outcome != row_report.outcome:
            raise ConfirmedImportError(
                "approved_row_outcome_mismatch", row_number=row_report.row_number
            )
        verified_items.append(
            ApprovedImportItem(import_item_id=approved_item.id, row=current_row)
        )

    return ApprovedImportSnapshot(
        dry_run_id=approved_dry_run_id,
        owner_id=owner_id,
        deck_id=deck_id,
        source_namespace=source_namespace,
        snapshot_captured_at=snapshot_captured_at,
        items=verified_items,
    )
