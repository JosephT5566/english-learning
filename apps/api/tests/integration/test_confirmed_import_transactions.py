"""PostgreSQL transaction tests for confirmed CSV application."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.confirmed_imports import apply_confirmed_import
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


def _arrange_approved_import(
    engine: Engine,
    csv_path: Path = FIXTURES / "import-valid-en.csv",
):
    owner_id = _insert_user(engine)
    deck_id = _insert_deck(engine, owner_id)
    snapshot = read_validated_csv_snapshot(
        csv_path,
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
    return owner_id, deck_id, snapshot, dry_run_id


def _apply(engine: Engine, owner_id, deck_id, snapshot, dry_run_id, **kwargs):
    return apply_confirmed_import(
        create_database_session_factory(engine),
        snapshot=snapshot,
        approved_dry_run_id=dry_run_id,
        owner_id=owner_id,
        deck_id=deck_id,
        source_namespace=SOURCE_NAMESPACE,
        target_language="en",
        snapshot_captured_at=SNAPSHOT_AT,
        validator_version=VALIDATOR_VERSION,
        **kwargs,
    )


def _mutation_snapshot(engine: Engine) -> dict[str, list[tuple]]:
    queries = {
        "decks": "SELECT id, version, created_at, updated_at FROM learning_decks ORDER BY id",
        "cards": "SELECT id, version, created_at, updated_at, archived_at FROM learning_cards ORDER BY id",
        "tags": "SELECT id, version, created_at, updated_at FROM tags ORDER BY id",
        "associations": "SELECT owner_id, card_id, tag_id, created_at FROM learning_card_tags ORDER BY card_id, tag_id",
        "states": "SELECT card_id, version, updated_at FROM review_states ORDER BY card_id",
        "runs": "SELECT id, status, completed_at, reconciliation_status FROM confirmed_import_runs ORDER BY id",
        "mappings": "SELECT id, learning_card_id, created_at FROM confirmed_import_mappings ORDER BY id",
    }
    with engine.connect() as connection:
        return {
            name: [tuple(row) for row in connection.execute(text(query)).all()]
            for name, query in queries.items()
        }


def _product_counts(engine: Engine) -> dict[str, int]:
    tables = (
        "learning_decks",
        "learning_cards",
        "tags",
        "learning_card_tags",
        "review_states",
        "review_batches",
        "review_events",
        "confirmed_import_runs",
        "confirmed_import_mappings",
    )
    with engine.connect() as connection:
        return {
            table: connection.execute(
                text(f"SELECT count(*) FROM {table}")
            ).scalar_one()
            for table in tables
        }


def test_first_apply_creates_card_tags_fresh_state_and_mapping_once(
    migrated_database_engine: Engine,
) -> None:
    owner_id, deck_id, snapshot, dry_run_id = _arrange_approved_import(
        migrated_database_engine
    )

    result = _apply(migrated_database_engine, owner_id, deck_id, snapshot, dry_run_id)

    assert result.replayed is False
    assert result.approved_dry_run_id == dry_run_id
    assert result.imported_card_count == 1
    assert result.source_mapping_count == 1
    assert result.tag_count == 1
    assert result.card_tag_association_count == 1
    assert result.review_state_count == 1
    assert result.archived_card_count == 0
    assert result.reconciliation_status == "pending"

    with migrated_database_engine.connect() as connection:
        card = connection.execute(
            text(
                """
                SELECT c.owner_id, c.deck_id, c.term, c.meaning, c.pronunciation,
                       c.target_language_definition, c.synonyms, c.antonyms,
                       c.part_of_speech, c.learned_on, c.archived_at, c.version,
                       s.review_stage, s.ease_factor, s.interval_days,
                       s.last_reviewed_at, s.next_review_at, s.version AS state_version
                FROM learning_cards AS c
                JOIN review_states AS s ON s.card_id = c.id
                """
            )
        ).one()
        tag = connection.execute(
            text("SELECT display_name, normalized_name, version FROM tags")
        ).one()
        mapping = connection.execute(
            text(
                """
                SELECT m.owner_id, m.source_namespace, m.row_number,
                       m.source_identity_hash, m.canonical_content_hash,
                       m.learning_card_id, m.outcome
                FROM confirmed_import_mappings AS m
                """
            )
        ).one()

        assert (
            connection.execute(text("SELECT count(*) FROM learning_decks")).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM learning_card_tags")
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(text("SELECT count(*) FROM review_batches")).scalar_one()
            == 0
        )
        assert (
            connection.execute(text("SELECT count(*) FROM review_events")).scalar_one()
            == 0
        )

    candidate = snapshot.rows[0].card_candidate
    assert card.owner_id == owner_id
    assert card.deck_id == deck_id
    assert card.term == candidate["term"]
    assert card.meaning == candidate["meaning"]
    assert card.pronunciation == candidate["pronunciation"]
    assert card.target_language_definition == candidate["target_language_definition"]
    assert card.synonyms == candidate["synonyms"]
    assert card.antonyms == candidate["antonyms"]
    assert card.part_of_speech == candidate["part_of_speech"]
    assert card.learned_on.isoformat() == candidate["learned_on"]
    assert card.archived_at is None
    assert card.version == 1
    assert card.review_stage == 1
    assert card.ease_factor == Decimal("2.50")
    assert card.interval_days == 0
    assert card.last_reviewed_at is None
    assert card.next_review_at == SNAPSHOT_AT
    assert card.state_version == 1
    assert tag.display_name == "fixture"
    assert tag.normalized_name == "fixture"
    assert tag.version == 1
    assert mapping.owner_id == owner_id
    assert mapping.source_namespace == SOURCE_NAMESPACE
    assert mapping.row_number == 2
    assert mapping.source_identity_hash == snapshot.rows[0].report.source_identity_hash
    assert mapping.canonical_content_hash == snapshot.rows[0].report.content_hash
    assert mapping.outcome == "created"


def test_exact_replay_returns_existing_result_without_any_mutation(
    migrated_database_engine: Engine,
) -> None:
    owner_id, deck_id, snapshot, dry_run_id = _arrange_approved_import(
        migrated_database_engine
    )
    first = _apply(migrated_database_engine, owner_id, deck_id, snapshot, dry_run_id)
    before_replay = _mutation_snapshot(migrated_database_engine)

    replay = _apply(migrated_database_engine, owner_id, deck_id, snapshot, dry_run_id)

    assert replay.replayed is True
    assert replay.run_id == first.run_id
    assert replay.completed_at == first.completed_at
    assert _mutation_snapshot(migrated_database_engine) == before_replay


def test_apply_reuses_existing_normalized_owned_tag_without_modifying_it(
    migrated_database_engine: Engine,
) -> None:
    owner_id, deck_id, snapshot, dry_run_id = _arrange_approved_import(
        migrated_database_engine
    )
    with migrated_database_engine.begin() as connection:
        existing = connection.execute(
            text(
                """
                INSERT INTO tags (owner_id, display_name, normalized_name)
                VALUES (:owner_id, 'Existing fixture label', 'fixture')
                RETURNING id, display_name, version, created_at, updated_at
                """
            ),
            {"owner_id": owner_id},
        ).one()

    _apply(migrated_database_engine, owner_id, deck_id, snapshot, dry_run_id)

    with migrated_database_engine.connect() as connection:
        persisted = connection.execute(
            text(
                """
                SELECT id, display_name, version, created_at, updated_at
                FROM tags WHERE owner_id = :owner_id
                """
            ),
            {"owner_id": owner_id},
        ).one()
        association_tag_id = connection.execute(
            text("SELECT tag_id FROM learning_card_tags")
        ).scalar_one()
        tag_count = connection.execute(text("SELECT count(*) FROM tags")).scalar_one()

    assert persisted == existing
    assert association_tag_id == existing.id
    assert tag_count == 1


def test_apply_preserves_archived_source_state(
    migrated_database_engine: Engine,
    tmp_path: Path,
) -> None:
    archived_path = tmp_path / "archived.csv"
    archived_path.write_text(
        (FIXTURES / "import-valid-en.csv")
        .read_text(encoding="utf-8")
        .replace(",active,", ",inactive,"),
        encoding="utf-8",
    )
    owner_id, deck_id, snapshot, dry_run_id = _arrange_approved_import(
        migrated_database_engine,
        archived_path,
    )

    result = _apply(migrated_database_engine, owner_id, deck_id, snapshot, dry_run_id)

    assert result.archived_card_count == 1
    with migrated_database_engine.connect() as connection:
        archived_at = connection.execute(
            text("SELECT archived_at FROM learning_cards")
        ).scalar_one()
    assert archived_at is not None
    assert archived_at >= datetime.fromisoformat(
        str(snapshot.rows[0].card_candidate["created_at"])
    )


def test_concurrent_exact_apply_creates_one_result_and_one_replay(
    migrated_database_engine: Engine,
) -> None:
    owner_id, deck_id, snapshot, dry_run_id = _arrange_approved_import(
        migrated_database_engine
    )
    start = Barrier(2)

    def apply_after_barrier():
        start.wait()
        return _apply(migrated_database_engine, owner_id, deck_id, snapshot, dry_run_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: apply_after_barrier(), range(2)))

    assert sorted(result.replayed for result in results) == [False, True]
    assert results[0].run_id == results[1].run_id
    counts = _product_counts(migrated_database_engine)
    assert counts["learning_decks"] == 1
    assert counts["learning_cards"] == 1
    assert counts["tags"] == 1
    assert counts["learning_card_tags"] == 1
    assert counts["review_states"] == 1
    assert counts["confirmed_import_runs"] == 1
    assert counts["confirmed_import_mappings"] == 1


@pytest.mark.parametrize(
    "failure_point",
    [
        "before_product_writes",
        "after_card",
        "after_tags",
        "after_review_state",
        "before_apply_record",
        "after_mapping",
        "before_commit",
    ],
)
def test_injected_failure_rolls_back_every_product_mutation(
    migrated_database_engine: Engine,
    failure_point: str,
) -> None:
    owner_id, deck_id, snapshot, dry_run_id = _arrange_approved_import(
        migrated_database_engine
    )
    before = _product_counts(migrated_database_engine)

    def fail_at(point: str, row_number: int | None = None) -> None:
        del row_number
        if point == failure_point:
            raise RuntimeError("synthetic_failure")

    with pytest.raises(RuntimeError, match="synthetic_failure"):
        _apply(
            migrated_database_engine,
            owner_id,
            deck_id,
            snapshot,
            dry_run_id,
            failure_injector=fail_at,
        )

    assert _product_counts(migrated_database_engine) == before
