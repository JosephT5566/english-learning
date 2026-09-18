"""Transactional confirmed import of an approved legacy CSV snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.orm.session import sessionmaker

from app.config import ConfigurationError, load_settings
from app.database import (
    create_database_engine,
    create_database_session_factory,
    database_transaction,
    dispose_database_engine,
)
from app.import_events import emit_import_event
from app.imports import (
    SUPPORTED_LANGUAGES,
    CanonicalImportRow,
    ImportBoundaryError,
    ValidatedCsvSnapshot,
    canonical_content_hash,
    normalize_collection_identity,
    read_validated_csv_snapshot,
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


@dataclass(frozen=True)
class ReconciliationSample:
    """Content-free deterministic field comparison for one imported row."""

    row_number: int
    source_identity_hash: str
    canonical_content_hash: str
    fields: dict[str, bool]


@dataclass(frozen=True)
class ReconciliationResult:
    """Bounded content-safe reconciliation result persisted after apply commit."""

    schema_version: str
    confirmed_import_run_id: str
    approved_dry_run_id: str
    source_snapshot_hash: str
    status: str
    expected_counts: dict[str, int]
    actual_counts: dict[str, int]
    checks: dict[str, bool]
    diagnostic_codes: list[str]
    samples: list[ReconciliationSample]


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
        # This context owns the complete apply transaction. The dry-run/deck locks,
        # cards, tags, associations, fresh states, mappings, and completed run are
        # committed only when the block exits normally. Any exception—including a
        # commit failure or injected interruption—rolls the entire unit back.
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


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat()


def _iso_date(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _database_candidate(card, tags: list[str]) -> dict[str, object]:
    return {
        "target_language": card.target_language,
        "term": card.term,
        "meaning": card.meaning,
        "reading": card.reading,
        "pronunciation": card.pronunciation,
        "romanization": card.romanization,
        "target_language_definition": card.target_language_definition,
        "synonyms": list(card.synonyms),
        "antonyms": list(card.antonyms),
        "tags": tags,
        "note": card.note,
        "supplementary_note": card.supplementary_note,
        "example_sentence": card.example_sentence,
        "example_translation": card.example_translation,
        "example_source": card.example_source,
        "part_of_speech": card.part_of_speech,
        "part_of_speech_detail": card.part_of_speech_detail,
        "learned_on": _iso_date(card.learned_on),
        "archived": card.archived_at is not None,
        "created_at": _iso_utc(card.created_at),
        "fresh_review_state": {
            "review_stage": card.review_stage,
            "ease_factor": (
                format(card.ease_factor, ".2f")
                if isinstance(card.ease_factor, Decimal)
                else None
            ),
            "interval_days": card.interval_days,
            "last_reviewed_at": _iso_utc(card.last_reviewed_at),
            "next_review_at": _iso_utc(card.next_review_at),
            "version": card.state_version,
        },
    }


def _stored_reconciliation(value: dict[str, object]) -> ReconciliationResult:
    return ReconciliationResult(
        schema_version=str(value["schema_version"]),
        confirmed_import_run_id=str(value["confirmed_import_run_id"]),
        approved_dry_run_id=str(value["approved_dry_run_id"]),
        source_snapshot_hash=str(value["source_snapshot_hash"]),
        status=str(value["status"]),
        expected_counts={
            str(key): int(count)
            for key, count in dict(value["expected_counts"]).items()
        },
        actual_counts={
            str(key): int(count) for key, count in dict(value["actual_counts"]).items()
        },
        checks={
            str(key): bool(result) for key, result in dict(value["checks"]).items()
        },
        diagnostic_codes=[str(code) for code in list(value["diagnostic_codes"])],
        samples=[
            ReconciliationSample(
                row_number=int(sample["row_number"]),
                source_identity_hash=str(sample["source_identity_hash"]),
                canonical_content_hash=str(sample["canonical_content_hash"]),
                fields={
                    str(key): bool(result)
                    for key, result in dict(sample["fields"]).items()
                },
            )
            for sample in list(value["samples"])
        ],
    )


def reconcile_confirmed_import(
    session_factory: sessionmaker[Session],
    *,
    apply_result: ConfirmedImportResult,
    snapshot: ValidatedCsvSnapshot,
    sample_size: int = 5,
) -> ReconciliationResult:
    """Reconcile a committed apply and persist a safe pass/fail result."""

    if not 1 <= sample_size <= 20:
        raise ConfirmedImportError("reconciliation_sample_size_invalid")

    with database_transaction(session_factory) as session:
        persisted_run = session.execute(
            text(
                """
                SELECT id, approved_dry_run_id, owner_id, deck_id,
                       source_namespace, eligible_row_count, imported_card_count,
                       source_mapping_count, tag_count,
                       card_tag_association_count, review_state_count,
                       archived_card_count, reconciliation_status,
                       reconciliation_result
                FROM confirmed_import_runs
                WHERE id = :run_id
                  AND approved_dry_run_id = :dry_run_id
                  AND owner_id = :owner_id
                  AND deck_id = :deck_id
                  AND source_namespace = :source_namespace
                FOR UPDATE
                """
            ),
            {
                "run_id": apply_result.run_id,
                "dry_run_id": apply_result.approved_dry_run_id,
                "owner_id": apply_result.owner_id,
                "deck_id": apply_result.deck_id,
                "source_namespace": apply_result.source_namespace,
            },
        ).one_or_none()
        if persisted_run is None:
            raise ConfirmedImportError("confirmed_import_run_not_found")
        if persisted_run.reconciliation_status != "pending":
            if persisted_run.reconciliation_result is None:
                raise ConfirmedImportError("reconciliation_result_missing")
            return _stored_reconciliation(persisted_run.reconciliation_result)

        mappings = session.execute(
            text(
                """
                SELECT m.row_number, m.source_identity_hash,
                       m.canonical_content_hash, m.learning_card_id,
                       c.owner_id AS card_owner_id, c.deck_id AS card_deck_id,
                       d.target_language, c.term, c.meaning, c.reading,
                       c.pronunciation, c.romanization,
                       c.target_language_definition, c.synonyms, c.antonyms,
                       c.note, c.supplementary_note, c.example_sentence,
                       c.example_translation, c.example_source,
                       c.part_of_speech, c.part_of_speech_detail, c.learned_on,
                       c.archived_at, c.created_at,
                       s.review_stage, s.ease_factor, s.interval_days,
                       s.last_reviewed_at, s.next_review_at,
                       s.version AS state_version
                FROM confirmed_import_mappings AS m
                LEFT JOIN learning_cards AS c
                  ON (c.id, c.owner_id) = (m.learning_card_id, m.owner_id)
                LEFT JOIN learning_decks AS d
                  ON (d.id, d.owner_id) = (c.deck_id, c.owner_id)
                LEFT JOIN review_states AS s
                  ON (s.card_id, s.owner_id) = (c.id, c.owner_id)
                WHERE m.confirmed_import_run_id = :run_id
                ORDER BY m.row_number
                """
            ),
            {"run_id": apply_result.run_id},
        ).all()
        tag_rows = session.execute(
            text(
                """
                SELECT m.row_number, t.display_name, t.normalized_name
                FROM confirmed_import_mappings AS m
                JOIN learning_card_tags AS ct
                  ON (ct.card_id, ct.owner_id) =
                     (m.learning_card_id, m.owner_id)
                JOIN tags AS t
                  ON (t.id, t.owner_id) = (ct.tag_id, ct.owner_id)
                WHERE m.confirmed_import_run_id = :run_id
                ORDER BY m.row_number, t.normalized_name, t.id
                """
            ),
            {"run_id": apply_result.run_id},
        ).all()
        review_history_counts = session.execute(
            text(
                """
                SELECT count(*) AS event_count,
                       count(DISTINCT e.batch_id) AS batch_count
                FROM review_events AS e
                JOIN confirmed_import_mappings AS m
                  ON m.learning_card_id = e.card_id
                 AND m.owner_id = e.owner_id
                WHERE m.confirmed_import_run_id = :run_id
                """
            ),
            {"run_id": apply_result.run_id},
        ).one()

        source_rows = {row.report.row_number: row for row in snapshot.rows}
        tags_by_row: dict[int, list[tuple[str, str]]] = {}
        for tag in tag_rows:
            tags_by_row.setdefault(tag.row_number, []).append(
                (tag.display_name, tag.normalized_name)
            )

        ownership_matches = True
        fresh_states_match = True
        content_hashes_match = True
        archived_count = 0
        card_ids: set[UUID] = set()
        canonical_tag_keys: set[str] = set()
        samples_by_row: dict[int, ReconciliationSample] = {}
        for card in mappings:
            source_row = source_rows.get(card.row_number)
            if source_row is None or card.card_owner_id is None:
                ownership_matches = False
                fresh_states_match = False
                content_hashes_match = False
                continue
            card_ids.add(card.learning_card_id)
            ownership_matches = ownership_matches and (
                card.card_owner_id == apply_result.owner_id
                and card.card_deck_id == apply_result.deck_id
            )

            expected_tags = list(source_row.card_candidate["tags"])
            actual_tag_rows = tags_by_row.get(card.row_number, [])
            actual_tag_keys = {normalized for _, normalized in actual_tag_rows}
            expected_tag_keys = {
                normalize_collection_identity(str(tag)) for tag in expected_tags
            }
            tag_fields_match = actual_tag_keys == expected_tag_keys
            canonical_tag_keys.update(actual_tag_keys)

            state_matches = (
                card.review_stage == 1
                and card.ease_factor == Decimal("2.50")
                and card.interval_days == 0
                and card.last_reviewed_at is None
                and card.next_review_at
                == datetime.fromisoformat(snapshot.report.snapshot_captured_at)
                and card.state_version == 1
            )
            fresh_states_match = fresh_states_match and state_matches

            database_tags = (
                expected_tags
                if tag_fields_match
                else [display_name for display_name, _ in actual_tag_rows]
            )
            database_candidate = _database_candidate(card, database_tags)
            database_hash = canonical_content_hash(database_candidate)
            row_hash_matches = (
                card.canonical_content_hash == source_row.report.content_hash
                and database_hash == source_row.report.content_hash
            )
            content_hashes_match = content_hashes_match and row_hash_matches
            if card.archived_at is not None:
                archived_count += 1

            fields = {
                "term": card.term == source_row.card_candidate["term"],
                "meaning": card.meaning == source_row.card_candidate["meaning"],
                "tags": tag_fields_match,
                "archived": (card.archived_at is not None)
                == bool(source_row.card_candidate["archived"]),
                "fresh_review_state": state_matches,
                "canonical_content_hash": row_hash_matches,
            }
            samples_by_row[card.row_number] = ReconciliationSample(
                row_number=card.row_number,
                source_identity_hash=card.source_identity_hash,
                canonical_content_hash=card.canonical_content_hash,
                fields=fields,
            )

        expected_tag_keys = {
            normalize_collection_identity(str(tag))
            for row in snapshot.rows
            for tag in row.card_candidate["tags"]
        }
        expected_associations = sum(
            len(row.card_candidate["tags"]) for row in snapshot.rows
        )
        actual_counts = {
            "eligible_rows": snapshot.report.accepted_rows
            + snapshot.report.repaired_rows,
            "mappings": len(mappings),
            "cards": len(card_ids),
            "tags": len(canonical_tag_keys),
            "card_tag_associations": len(tag_rows),
            "review_states": sum(row.state_version is not None for row in mappings),
            "archived_cards": archived_count,
            "review_events": review_history_counts.event_count,
            "review_batches": review_history_counts.batch_count,
        }
        eligible_rows = snapshot.report.accepted_rows + snapshot.report.repaired_rows
        expected_counts = {
            "eligible_rows": eligible_rows,
            "mappings": eligible_rows,
            "cards": eligible_rows,
            "tags": len(expected_tag_keys),
            "card_tag_associations": expected_associations,
            "review_states": eligible_rows,
            "archived_cards": sum(
                bool(row.card_candidate["archived"]) for row in snapshot.rows
            ),
            "review_events": 0,
            "review_batches": 0,
        }
        deterministic_rows = sorted(
            snapshot.rows,
            key=lambda row: (
                row.report.source_identity_hash,
                row.report.row_number,
            ),
        )[:sample_size]
        samples = [
            samples_by_row.get(
                row.report.row_number,
                ReconciliationSample(
                    row_number=row.report.row_number,
                    source_identity_hash=row.report.source_identity_hash,
                    canonical_content_hash=row.report.content_hash,
                    fields={"mapped": False},
                ),
            )
            for row in deterministic_rows
        ]
        checks = {
            "eligible_rows_match_mappings": expected_counts["eligible_rows"]
            == actual_counts["mappings"]
            == persisted_run.source_mapping_count,
            "mappings_match_cards": actual_counts["mappings"]
            == actual_counts["cards"]
            == persisted_run.imported_card_count,
            "ownership_and_deck_match": ownership_matches,
            "fresh_review_states_match": fresh_states_match
            and actual_counts["review_states"] == expected_counts["review_states"]
            and persisted_run.review_state_count == expected_counts["review_states"],
            "canonical_content_hashes_match": content_hashes_match,
            "tag_count_matches": actual_counts["tags"]
            == expected_counts["tags"]
            == persisted_run.tag_count,
            "tag_association_count_matches": actual_counts["card_tag_associations"]
            == expected_counts["card_tag_associations"]
            == persisted_run.card_tag_association_count,
            "archived_card_count_matches": actual_counts["archived_cards"]
            == expected_counts["archived_cards"]
            == persisted_run.archived_card_count,
            "sample_fields_match": all(
                all(sample.fields.values()) for sample in samples
            ),
            "no_review_history_created": (
                review_history_counts.event_count == 0
                and review_history_counts.batch_count == 0
            ),
        }
        diagnostic_codes = [
            f"reconciliation_{name}_failed"
            for name, passed in checks.items()
            if not passed
        ]
        result = ReconciliationResult(
            schema_version="confirmed-import-reconciliation-v1",
            confirmed_import_run_id=str(apply_result.run_id),
            approved_dry_run_id=str(apply_result.approved_dry_run_id),
            source_snapshot_hash=apply_result.source_snapshot_hash,
            status="passed" if all(checks.values()) else "failed",
            expected_counts=expected_counts,
            actual_counts=actual_counts,
            checks=checks,
            diagnostic_codes=diagnostic_codes,
            samples=samples,
        )
        session.execute(
            text(
                """
                UPDATE confirmed_import_runs
                SET reconciliation_status = :status,
                    reconciliation_result = CAST(:result AS jsonb),
                    reconciled_at = CURRENT_TIMESTAMP
                WHERE id = :run_id AND reconciliation_status = 'pending'
                """
            ),
            {
                "status": result.status,
                "result": json.dumps(asdict(result)),
                "run_id": apply_result.run_id,
            },
        )
        return result


def execute_confirmed_import(
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
) -> tuple[ConfirmedImportResult, ReconciliationResult]:
    """Apply, expose the post-commit interruption seam, then reconcile."""

    apply_result = apply_confirmed_import(
        session_factory,
        snapshot=snapshot,
        approved_dry_run_id=approved_dry_run_id,
        owner_id=owner_id,
        deck_id=deck_id,
        source_namespace=source_namespace,
        target_language=target_language,
        snapshot_captured_at=snapshot_captured_at,
        validator_version=validator_version,
        failure_injector=failure_injector,
    )
    failure_injector("after_commit")
    reconciliation = reconcile_confirmed_import(
        session_factory,
        apply_result=apply_result,
        snapshot=snapshot,
    )
    return apply_result, reconciliation


def confirmed_import_report_as_dict(
    apply_result: ConfirmedImportResult,
    reconciliation: ReconciliationResult,
) -> dict[str, object]:
    """Return a JSON-safe operational report without private learning content."""

    return {
        "schema_version": "confirmed-import-report-v1",
        "confirmed_import_run_id": str(apply_result.run_id),
        "approved_dry_run_id": str(apply_result.approved_dry_run_id),
        "owner_id": apply_result.owner_id,
        "deck_id": str(apply_result.deck_id),
        "source_namespace": apply_result.source_namespace,
        "source_snapshot_hash": apply_result.source_snapshot_hash,
        "status": apply_result.status,
        "replayed": apply_result.replayed,
        "completed_at": apply_result.completed_at.isoformat(),
        "reconciliation_status": reconciliation.status,
        "counts": {
            "eligible_rows": apply_result.eligible_row_count,
            "imported_cards": apply_result.imported_card_count,
            "source_mappings": apply_result.source_mapping_count,
            "tags": apply_result.tag_count,
            "card_tag_associations": apply_result.card_tag_association_count,
            "review_states": apply_result.review_state_count,
            "archived_cards": apply_result.archived_card_count,
        },
    }


def reconciliation_report_as_dict(
    reconciliation: ReconciliationResult,
) -> dict[str, object]:
    """Return the already content-safe reconciliation payload."""

    return asdict(reconciliation)


def _write_report(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _parse_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply one approved legacy CSV snapshot to an existing deck"
    )
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--approved-dry-run-id", required=True, type=UUID)
    parser.add_argument("--owner-id", required=True, type=int)
    parser.add_argument("--deck-id", required=True, type=UUID)
    parser.add_argument("--source-namespace", required=True)
    parser.add_argument(
        "--target-language", required=True, choices=sorted(SUPPORTED_LANGUAGES)
    )
    parser.add_argument(
        "--snapshot-captured-at", required=True, type=datetime.fromisoformat
    )
    parser.add_argument("--validator-version", required=True)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--reconciliation-report", required=True, type=Path)
    return parser.parse_args()


def _safe_error(error: ConfirmedImportError) -> str:
    payload: dict[str, object] = {"code": error.code}
    if error.row_number is not None:
        payload["row_number"] = error.row_number
    return json.dumps({"error": payload}, sort_keys=True)


def main() -> int:
    """Run the local confirmed-import CLI and emit only bounded safe failures."""

    args = _parse_cli_args()
    outcome = "unexpected_error"
    phase = "validation"
    database_committed = False
    reports_written = 0
    replayed = False
    try:
        snapshot = read_validated_csv_snapshot(
            args.csv,
            source_namespace=args.source_namespace,
            target_language=args.target_language,
            snapshot_captured_at=args.snapshot_captured_at,
        )
        phase = "database"
        settings = load_settings()
        engine = create_database_engine(settings)
        try:
            apply_result = apply_confirmed_import(
                create_database_session_factory(engine),
                snapshot=snapshot,
                approved_dry_run_id=args.approved_dry_run_id,
                owner_id=args.owner_id,
                deck_id=args.deck_id,
                source_namespace=snapshot.report.source_namespace,
                target_language=args.target_language,
                snapshot_captured_at=args.snapshot_captured_at,
                validator_version=args.validator_version,
            )
            database_committed = True
            replayed = apply_result.replayed
            phase = "reconciliation"
            reconciliation = reconcile_confirmed_import(
                create_database_session_factory(engine),
                apply_result=apply_result,
                snapshot=snapshot,
            )
        finally:
            dispose_database_engine(engine)
        phase = "report"
        _write_report(
            args.report,
            confirmed_import_report_as_dict(apply_result, reconciliation),
        )
        reports_written = 1
        _write_report(
            args.reconciliation_report,
            reconciliation_report_as_dict(reconciliation),
        )
        reports_written = 2
        outcome = (
            "passed" if reconciliation.status == "passed" else "reconciliation_failed"
        )
        phase = "done"
        return 0 if reconciliation.status == "passed" else 3
    except ConfirmedImportError as error:
        outcome = "import_error"
        print(_safe_error(error), file=sys.stderr)
        return 2
    except ImportBoundaryError as error:
        outcome = "validation_error"
        print(json.dumps({"error": {"code": str(error)}}), file=sys.stderr)
        return 2
    except ConfigurationError:
        outcome = "configuration_error"
        print(json.dumps({"error": {"code": "configuration_invalid"}}), file=sys.stderr)
        return 2
    except SQLAlchemyError:
        outcome = "database_error"
        print(json.dumps({"error": {"code": "database_unavailable"}}), file=sys.stderr)
        return 2
    except OSError:
        outcome = "io_error"
        code = "report_write_failed" if phase == "report" else "import_io_failed"
        print(json.dumps({"error": {"code": code}}), file=sys.stderr)
        return 2
    except Exception:  # noqa: BLE001 - CLI must bound every unexpected failure.
        print(
            json.dumps({"error": {"code": "confirmed_import_failed"}}), file=sys.stderr
        )
        return 2
    finally:
        emit_import_event(
            operation="confirmed",
            outcome=outcome,
            phase=phase,
            database_committed=database_committed,
            reports_written=reports_written,
            replayed=replayed,
        )


if __name__ == "__main__":
    raise SystemExit(main())
