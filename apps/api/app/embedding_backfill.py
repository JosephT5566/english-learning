"""Operator-invoked, owner-bounded embedding repair. No implicit provider calls."""

import argparse
import json
import sys
import time
from collections import Counter
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import ConfigurationError, load_settings
from app.database import create_database_engine, create_database_session_factory
from app.embeddings import process_card, vertex_document_embedding
from app.semantic_text import MODEL_VERSION


def run(
    *,
    owner_id: int,
    cursor: UUID | None,
    limit: int,
    dry_run: bool = False,
    retry_exhausted: bool = False,
) -> dict:
    settings = load_settings()
    if not dry_run and not settings.vertex_project_id:
        raise ValueError("VERTEX_PROJECT_ID is required for provider calls")
    engine = create_database_engine(settings)
    factory = create_database_session_factory(engine)
    counts: Counter[str] = Counter()
    last_id = cursor
    scan_complete = False
    started = time.monotonic()
    try:
        # Each page is short-lived; a card may change while the provider is running.
        while sum(counts.values()) < limit and time.monotonic() - started < 1800:
            with factory() as session:
                rows = (
                    session.execute(
                        text("""
                    SELECT c.id FROM learning_cards c
                    JOIN learning_decks d ON (d.id, d.owner_id) = (c.deck_id, c.owner_id)
                    LEFT JOIN card_embeddings e ON (e.card_id, e.owner_id) = (c.id, c.owner_id)
                      AND e.model_version = :model
                    WHERE c.owner_id = :owner_id AND c.archived_at IS NULL
                      AND d.archived_at IS NULL
                      AND (CAST(:cursor AS uuid) IS NULL OR c.id > CAST(:cursor AS uuid))
                      AND (c.semantic_content_hash IS NULL OR e.card_id IS NULL
                        OR e.content_hash IS DISTINCT FROM c.semantic_content_hash
                        OR (e.state = 'retryable' AND e.next_retry_at <= CURRENT_TIMESTAMP)
                        OR (e.state = 'pending' AND e.last_attempt_at < CURRENT_TIMESTAMP - INTERVAL '2 minutes')
                        OR (:retry_exhausted AND e.state = 'exhausted'))
                    ORDER BY c.id LIMIT :page_size
                """),
                        {
                            "model": MODEL_VERSION,
                            "owner_id": owner_id,
                            "retry_exhausted": retry_exhausted,
                            "cursor": last_id,
                            "page_size": min(100, limit - sum(counts.values())),
                        },
                    )
                    .scalars()
                    .all()
                )
            if not rows:
                scan_complete = True
                break
            for card_id in rows:
                last_id = card_id
                if dry_run:
                    counts["eligible"] += 1
                else:
                    outcome = process_card(
                        factory,
                        card_id,
                        owner_id,
                        lambda content: vertex_document_embedding(
                            content,
                            project=settings.vertex_project_id,
                            location=settings.vertex_location,
                        ),
                        force=retry_exhausted,
                    )
                    counts[outcome] += 1
                if time.monotonic() - started >= 1800:
                    break
        return {
            "counts": dict(sorted(counts.items())),
            "next_cursor": str(last_id) if last_id and not scan_complete else None,
            "time_limit_reached": time.monotonic() - started >= 1800,
        }
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-id", type=int, required=True)
    parser.add_argument("--cursor", type=UUID)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--retry-exhausted", action="store_true")
    args = parser.parse_args()
    if args.owner_id < 1 or not 1 <= args.limit <= 500:
        parser.error("owner-id must be positive and limit must be 1..500")
    try:
        result = run(
            owner_id=args.owner_id,
            cursor=args.cursor,
            limit=args.limit,
            dry_run=args.dry_run,
            retry_exhausted=args.retry_exhausted,
        )
    except (ConfigurationError, ValueError, SQLAlchemyError):
        print(json.dumps({"status": "failed", "error_code": "backfill_unavailable"}))
        sys.exit(1)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
