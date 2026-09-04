# Issue #9 Multilingual Read APIs

- Date: 2026-09-03
- Status: Implemented and verified locally
- Dependency: Issue #8 schema and indexes

## Implemented boundary

- `GET /v1/decks` and `GET /v1/decks/{deck_id}`
- `GET /v1/cards` and `GET /v1/cards/{card_id}`
- `GET /v1/reviews/due`
- Shared English/Japanese response models and owner-scoped SQL
- Stable cursor pagination, filters, errors, and database-failure translation
- Reversible management-list indexes in revision `20260903_0003`

Authentication is intentionally deferred. `app.reads.current_owner_id()` is the explicit temporary
test-user composition boundary and currently returns owner `1`; no endpoint accepts owner identity
from the client. Issue #10 must replace that dependency with a server-verified identity before these
routes can be deployed as user-facing data access.

## Contract decisions

- Collections return `{ "items": [...], "next_cursor": ... }`; resources are returned directly.
- Deck and card management lists sort by `updated_at DESC, id DESC`.
- Due review sorts by `next_review_at ASC, card_id ASC`.
- Every cursor is opaque, versioned, and bound to endpoint, normalized filters, effective limit,
  and the last returned sort tuple. A changed shape or malformed cursor returns `400 invalid_cursor`.
- The first due page captures a server `as_of` instant. Later cursors retain that instant, preventing
  newly due cards from entering the middle of the traversal merely because wall time advanced.
- Card filters combine with AND. The implemented filters are `deck_id`, `target_language`, `status`,
  and one `tag_id`; status defaults to `active`.
- Due review requires `target_language` and accepts up to 20 unique repeated `deck_id` values. Every
  explicit deck must be owned, active, and in that language.
- Detail and explicit resource filters use the same non-disclosing response for missing and
  cross-owner resources.
- SQLAlchemy failures become retryable `503 database_unavailable`. SQL, credentials, exception text,
  and schema details do not cross the API boundary.

The card-management substring `query` filter described during Issue #5 was not included because
Issue #9 explicitly requests target-language and tag filtering, and search infrastructure is out of
scope. It can be added later with an explicit normalization contract and an index justified by
measured use.

## Acceptance evidence

| Criterion | Evidence |
| --- | --- |
| Deterministic ordering | Tuple ordering in `app/reads.py`; tied fixture timestamps exercise UUID tie-breaks |
| No duplicate/skip in stable data | Card and due-review multi-page HTTP tests traverse all expected IDs exactly once |
| One English/Japanese contract | Parametrized detail tests and paired filtered-list assertions use the same routes/models |
| Stable invalid cursor/filter errors | HTTP tests cover malformed, query-shape-mismatched, unsupported, language, and duplicate-deck inputs |
| Safe database failures | A forced SQLAlchemy failure returns only retryable `503 database_unavailable` |
| Query plans recorded | [Query-plan report](query-plans.md) and executable PostgreSQL assertions |
| Examples checked in | [API examples](api-examples.md) |

## Verification

- `uv run ruff format --check .`: passed; 32 files already formatted.
- `uv run ruff check .`: passed.
- `RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest -q`: 122 passed in 45.82 seconds against local
  PostgreSQL 17; one existing upstream FastAPI `TestClient` warning remains.
- `uv lock --check`: passed; 39 packages resolved.

This is local correctness and planner-selection evidence. It is not production latency, throughput,
availability, remote CI, authentication, or deployment evidence.
