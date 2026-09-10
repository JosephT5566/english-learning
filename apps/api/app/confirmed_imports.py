"""Transactional confirmed import of an approved legacy CSV snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.session import sessionmaker

from app.database import database_transaction
from app.imports import (
    CanonicalImportRow,
    ValidatedCsvSnapshot,
    normalize_collection_identity,
)


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


@dataclass(frozen=True)
class ConfirmedImportResult:
    """Content-safe persisted result for a first apply or exact replay."""

    run_id: UUID
    approved_dry_run_id: UUID
    owner_id: int
    deck_id: UUID
    source_namespace: str
    source_snapshot_hash: str
    status: str
    eligible_row_count: int
    imported_card_count: int
    source_mapping_count: int
    tag_count: int
    card_tag_association_count: int
    review_state_count: int
    archived_card_count: int
    reconciliation_status: str
    completed_at: datetime
    replayed: bool


class FailureInjector(Protocol):
    """Test seam for deterministic transaction failure injection."""

    def __call__(self, point: str, row_number: int | None = None) -> None: ...


def _do_not_fail(point: str, row_number: int | None = None) -> None:
    del point, row_number


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


def _result_from_row(
    row,
    *,
    source_snapshot_hash: str,
    replayed: bool,
) -> ConfirmedImportResult:
    return ConfirmedImportResult(
        run_id=row.id,
        approved_dry_run_id=row.approved_dry_run_id,
        owner_id=row.owner_id,
        deck_id=row.deck_id,
        source_namespace=row.source_namespace,
        source_snapshot_hash=source_snapshot_hash,
        status=row.status,
        eligible_row_count=row.eligible_row_count,
        imported_card_count=row.imported_card_count,
        source_mapping_count=row.source_mapping_count,
        tag_count=row.tag_count,
        card_tag_association_count=row.card_tag_association_count,
        review_state_count=row.review_state_count,
        archived_card_count=row.archived_card_count,
        reconciliation_status=row.reconciliation_status,
        completed_at=row.completed_at,
        replayed=replayed,
    )


def _existing_apply(
    session: Session,
    *,
    approved: ApprovedImportSnapshot,
    source_snapshot_hash: str,
) -> ConfirmedImportResult | None:
    existing = session.execute(
        text(
            """
            SELECT id, approved_dry_run_id, owner_id, deck_id, source_namespace,
                   status, eligible_row_count, imported_card_count,
                   source_mapping_count, tag_count, card_tag_association_count,
                   review_state_count, archived_card_count,
                   reconciliation_status, completed_at
            FROM confirmed_import_runs
            WHERE owner_id = :owner_id AND source_namespace = :source_namespace
            """
        ),
        {
            "owner_id": approved.owner_id,
            "source_namespace": approved.source_namespace,
        },
    ).one_or_none()
    if existing is None:
        return None
    if (
        existing.approved_dry_run_id != approved.dry_run_id
        or existing.deck_id != approved.deck_id
    ):
        raise ConfirmedImportError("source_namespace_already_applied")
    return _result_from_row(
        existing,
        source_snapshot_hash=source_snapshot_hash,
        replayed=True,
    )


def _create_card(
    session: Session,
    *,
    approved: ApprovedImportSnapshot,
    row: CanonicalImportRow,
) -> UUID:
    candidate = row.card_candidate
    created_at = datetime.fromisoformat(str(candidate["created_at"]))
    archived_at = (
        max(created_at, approved.snapshot_captured_at)
        if candidate["archived"]
        else None
    )
    updated_at = archived_at or created_at
    return session.execute(
        text(
            """
            INSERT INTO learning_cards (
                deck_id, owner_id, term, meaning, reading, pronunciation,
                romanization, target_language_definition, example_sentence,
                example_translation, example_source, synonyms, antonyms,
                part_of_speech, part_of_speech_detail, note,
                supplementary_note, learned_on, archived_at, version,
                created_at, updated_at
            ) VALUES (
                :deck_id, :owner_id, :term, :meaning, :reading, :pronunciation,
                :romanization, :target_language_definition, :example_sentence,
                :example_translation, :example_source, :synonyms, :antonyms,
                :part_of_speech, :part_of_speech_detail, :note,
                :supplementary_note, :learned_on, :archived_at, 1,
                :created_at, :updated_at
            )
            RETURNING id
            """
        ),
        {
            "deck_id": approved.deck_id,
            "owner_id": approved.owner_id,
            "term": candidate["term"],
            "meaning": candidate["meaning"],
            "reading": candidate["reading"],
            "pronunciation": candidate["pronunciation"],
            "romanization": candidate["romanization"],
            "target_language_definition": candidate["target_language_definition"],
            "example_sentence": candidate["example_sentence"],
            "example_translation": candidate["example_translation"],
            "example_source": candidate["example_source"],
            "synonyms": candidate["synonyms"],
            "antonyms": candidate["antonyms"],
            "part_of_speech": candidate["part_of_speech"],
            "part_of_speech_detail": candidate["part_of_speech_detail"],
            "note": candidate["note"],
            "supplementary_note": candidate["supplementary_note"],
            "learned_on": candidate["learned_on"],
            "archived_at": archived_at,
            "created_at": created_at,
            "updated_at": updated_at,
        },
    ).scalar_one()


def _tag_id(
    session: Session,
    *,
    owner_id: int,
    display_name: str,
    imported_at: datetime,
) -> UUID:
    normalized_name = normalize_collection_identity(display_name)
    tag_id = session.execute(
        text(
            """
            INSERT INTO tags (
                owner_id, display_name, normalized_name, version,
                created_at, updated_at
            ) VALUES (
                :owner_id, :display_name, :normalized_name, 1,
                :imported_at, :imported_at
            )
            ON CONFLICT (owner_id, normalized_name) DO NOTHING
            RETURNING id
            """
        ),
        {
            "owner_id": owner_id,
            "display_name": display_name,
            "normalized_name": normalized_name,
            "imported_at": imported_at,
        },
    ).scalar_one_or_none()
    if tag_id is not None:
        return tag_id
    return session.execute(
        text(
            """
            SELECT id FROM tags
            WHERE owner_id = :owner_id AND normalized_name = :normalized_name
            """
        ),
        {"owner_id": owner_id, "normalized_name": normalized_name},
    ).scalar_one()


def _create_fresh_review_state(
    session: Session,
    *,
    card_id: UUID,
    owner_id: int,
    snapshot_captured_at: datetime,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO review_states (
                card_id, owner_id, review_stage, ease_factor, interval_days,
                last_reviewed_at, next_review_at, version, updated_at
            ) VALUES (
                :card_id, :owner_id, 1, 2.50, 0, NULL,
                :snapshot_captured_at, 1, :snapshot_captured_at
            )
            """
        ),
        {
            "card_id": card_id,
            "owner_id": owner_id,
            "snapshot_captured_at": snapshot_captured_at,
        },
    )


def _apply_verified_snapshot(
    session: Session,
    *,
    approved: ApprovedImportSnapshot,
    source_snapshot_hash: str,
    failure_injector: FailureInjector,
) -> ConfirmedImportResult:
    existing = _existing_apply(
        session,
        approved=approved,
        source_snapshot_hash=source_snapshot_hash,
    )
    if existing is not None:
        return existing

    failure_injector("before_product_writes")
    card_rows: list[tuple[ApprovedImportItem, UUID]] = []
    canonical_tag_keys: set[str] = set()
    association_count = 0
    archived_count = 0
    for approved_item in approved.items:
        current_row = approved_item.row
        card_id = _create_card(session, approved=approved, row=current_row)
        failure_injector("after_card", current_row.report.row_number)

        candidate = current_row.card_candidate
        if candidate["archived"]:
            archived_count += 1
        for display_name in candidate["tags"]:
            tag_id = _tag_id(
                session,
                owner_id=approved.owner_id,
                display_name=str(display_name),
                imported_at=approved.snapshot_captured_at,
            )
            canonical_tag_keys.add(normalize_collection_identity(str(display_name)))
            session.execute(
                text(
                    """
                    INSERT INTO learning_card_tags (
                        owner_id, card_id, tag_id, created_at
                    ) VALUES (
                        :owner_id, :card_id, :tag_id, :created_at
                    )
                    """
                ),
                {
                    "owner_id": approved.owner_id,
                    "card_id": card_id,
                    "tag_id": tag_id,
                    "created_at": approved.snapshot_captured_at,
                },
            )
            association_count += 1
        failure_injector("after_tags", current_row.report.row_number)

        _create_fresh_review_state(
            session,
            card_id=card_id,
            owner_id=approved.owner_id,
            snapshot_captured_at=approved.snapshot_captured_at,
        )
        failure_injector("after_review_state", current_row.report.row_number)
        card_rows.append((approved_item, card_id))

    failure_injector("before_apply_record")
    confirmed_run = session.execute(
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
                'completed', :row_count, :row_count, :row_count, :tag_count,
                :association_count, :row_count, :archived_count, 'pending',
                CURRENT_TIMESTAMP
            )
            RETURNING id, approved_dry_run_id, owner_id, deck_id,
                      source_namespace, status, eligible_row_count,
                      imported_card_count, source_mapping_count, tag_count,
                      card_tag_association_count, review_state_count,
                      archived_card_count, reconciliation_status, completed_at
            """
        ),
        {
            "dry_run_id": approved.dry_run_id,
            "owner_id": approved.owner_id,
            "deck_id": approved.deck_id,
            "source_namespace": approved.source_namespace,
            "row_count": len(card_rows),
            "tag_count": len(canonical_tag_keys),
            "association_count": association_count,
            "archived_count": archived_count,
        },
    ).one()

    for approved_item, card_id in card_rows:
        report = approved_item.row.report
        session.execute(
            text(
                """
                INSERT INTO confirmed_import_mappings (
                    confirmed_import_run_id, approved_dry_run_id,
                    approved_import_item_id, owner_id, source_namespace,
                    row_number, source_identity_hash, canonical_content_hash,
                    learning_card_id, outcome
                ) VALUES (
                    :confirmed_run_id, :dry_run_id, :import_item_id,
                    :owner_id, :source_namespace, :row_number,
                    :source_identity_hash, :content_hash, :card_id, 'created'
                )
                """
            ),
            {
                "confirmed_run_id": confirmed_run.id,
                "dry_run_id": approved.dry_run_id,
                "import_item_id": approved_item.import_item_id,
                "owner_id": approved.owner_id,
                "source_namespace": approved.source_namespace,
                "row_number": report.row_number,
                "source_identity_hash": report.source_identity_hash,
                "content_hash": report.content_hash,
                "card_id": card_id,
            },
        )
        failure_injector("after_mapping", report.row_number)

    return _result_from_row(
        confirmed_run,
        source_snapshot_hash=source_snapshot_hash,
        replayed=False,
    )


def apply_confirmed_import(
    session_factory: sessionmaker[Session],
    *,
    snapshot: ValidatedCsvSnapshot,
    approved_dry_run_id: UUID,
    owner_id: int,
    deck_id: UUID,
    source_namespace: str,
    target_language: str,
    snapshot_captured_at: datetime,
    validator_version: str,
    failure_injector: FailureInjector = _do_not_fail,
) -> ConfirmedImportResult:
    """Apply one reproduced approved snapshot in one owned transaction."""

    try:
        with database_transaction(session_factory) as session:
            approved = verify_approved_snapshot(
                session,
                snapshot=snapshot,
                approved_dry_run_id=approved_dry_run_id,
                owner_id=owner_id,
                deck_id=deck_id,
                source_namespace=source_namespace,
                target_language=target_language,
                snapshot_captured_at=snapshot_captured_at,
                validator_version=validator_version,
            )
            result = _apply_verified_snapshot(
                session,
                approved=approved,
                source_snapshot_hash=snapshot.report.source_snapshot_hash,
                failure_injector=failure_injector,
            )
            failure_injector("before_commit")
            return result
    except IntegrityError:
        raise ConfirmedImportError("confirmed_import_constraint_conflict") from None
