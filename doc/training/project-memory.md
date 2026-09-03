# English Learning Project Memory

Last updated: 2026-09-03

## Purpose

Build credible full-stack and backend engineering depth by evolving the existing English-learning application into a deployed multilingual product. The work should demonstrate API and schema design, safe data migration, authorization, transactions, failure recovery, frontend integration, AI safety, and operational ownership.

This is project evidence, not professional production-service experience.

## Current system

- SvelteKit 2 and Svelte 5 static frontend
- GitHub Pages deployment
- Google Identity Services sign-in in the browser
- Google Apps Script API for vocabulary retrieval and review updates
- Google Sheets as the current data store
- English review routes and shared card components
- A semantic-search proposal exists but is not an active priority

## Target system

- One repository and modular monolith
- Existing SvelteKit frontend
- Python FastAPI backend
- PostgreSQL with SQLAlchemy 2 and Alembic
- Server-side Google token verification and per-user ownership enforcement
- Shared language-aware model for English and Japanese
- Transactional review history and current review state
- Idempotent Google Sheets import and controlled cutover
- AI-assisted definitions, readings, notes, and examples through editable drafts and explicit confirmation
- Automated tests, CI, deployment, observability, rollback, and recovery documentation

## Agreed decisions

- Use this repository rather than starting a new primary full-stack repository.
- Use Python first for the backend.
- Keep frontend and backend together while deploying them independently.
- Use PostgreSQL as the eventual source of truth.
- Preserve Google Sheets during a controlled migration, then remove it from the runtime path.
- Support English and Japanese through one backend and shared model.
- Defer semantic search until the transactional core is dependable.
- AI output cannot directly become confirmed learning content.
- Avoid microservices and infrastructure without demonstrated need.

## Active milestone

Week 2 — multilingual domain schema, Issue #8.

Issue #4 current-state trace is documented in
[`current-state-flow-trace.md`](current-state-flow-trace.md). It includes the three request flows,
trust boundaries, Apps Script and Sheet contracts, a current-state diagram, actual local command
results, and a sanitized synthetic fixture.

Issue #5 multilingual product/API/schema design is complete locally. Its
[`issues/issue-5/`](issues/issue-5/README.md) index and linked artifacts cover invariants, ownership,
all 21 Sheet-field mappings, MVP API contracts,
failure/recovery, schema constraints/indexes, request/trust-boundary diagrams, a safe future AI draft
lifecycle, rejected alternatives, tradeoffs, and unresolved implementation choices. Joseph completed
the design-defense check. No backend code or migration exists yet.

Issue #6 backend-foundation implementation is complete and verified locally. The decisions are recorded in
[`issues/issue-6/README.md`](issues/issue-6/README.md): use `uv`, place the independent Python package
under `apps/api/`, use typed secret-safe configuration with disposable local PostgreSQL defaults,
keep liveness independent of PostgreSQL, return safe database-aware readiness results, and manage the
database engine through FastAPI lifespan startup and shutdown. The `uv` package and lockfile exist,
and the first liveness vertical slice is implemented through an application factory, isolated health
router, explicit response model, and HTTP-level unit test. The unit test, Ruff lint, Ruff formatting,
Uvicorn factory startup/shutdown, and a real `200` liveness request passed locally. Pytest currently
emits one upstream FastAPI `TestClient`/`httpx` deprecation warning. `apps/api/README.md` is the
canonical reference for verified API commands. Typed, frozen configuration now loads during FastAPI
lifespan without import-time side effects. It validates supported environments and log levels, keeps
the database URL secret, bounds connection timeout to 1-10 seconds, requires the Psycopg driver,
rejects the disposable local URL in production, and translates raw validation failures into safe
startup errors. The full unit suite passes with eleven tests; normal Uvicorn startup and deliberate
secret-safe startup failure were both verified. SQLAlchemy engine construction and disposal now live
in `app/database.py`; FastAPI lifespan creates the lazy engine without connecting, stores it in app
state, and disposes its pool during shutdown. The bounded `SELECT 1` readiness probe and safe
`200`/`503` endpoint now exist. Nineteen unit tests and two opt-in real-driver integration tests pass.
A live PostgreSQL stop/restart exercise changed readiness `200 -> 503 -> 200` without restarting the
API, while liveness stayed `200`. Initial available-database verification used an existing local
`postgres:12` image after the old Docker Desktop stack failed to complete the selected image pull.
After switching to OrbStack, the exact `postgres:17-alpine` Compose service pulled successfully,
became healthy, passed both integration tests, and repeated the live `200 -> 503 -> 200` recovery
exercise. The final combined suite passed all 21 unit and integration tests; Ruff lint and formatting
checks also passed. The PostgreSQL 17 Compose service is currently running with its named development
volume.

Issue #7 persistence-foundation implementation and learning checkpoint are merged on `main` at
`b1227ae`. The API now has application-scoped
session factories, short-lived transaction ownership, an empty reversible
Alembic baseline, isolated real-PostgreSQL migration and transaction patterns, a stable safe API
error envelope with server request IDs, and independent frontend/backend CI jobs. The development
database and a fresh temporary database both passed upgrade, downgrade, and re-upgrade. The full
PostgreSQL-backed backend suite passes 32 tests; Ruff and lock checks pass. The frontend production
build passes, while the already documented `npm run check` 6 errors/6 warnings and repository-wide
Prettier drift remain outside this backend ticket.

Issue #8 completed its initial coached design checkpoint. The accepted implementation boundary is
recorded in [`issues/issue-8/`](issues/issue-8/README.md): confirmed cards require nonblank term and
meaning, cards derive language from required owned decks, optional multilingual fields share one
card table, one example remains embedded, review state uses `card_id` as its primary key, redundant
constrained owner IDs enforce same-owner relationships, review history records before/after state,
and indexes map to named list, language, due-review, and history queries. Revision `20260902_0002`
now adds users, owned multilingual decks, confirmed learning cards, tags, card/tag associations, and
current review state.
Cards use a composite owned deck foreign key, require nonblank term/meaning, share optional
English/Japanese fields, and embed one example. Tags have normalized per-owner identity; two
composite foreign keys prevent cross-owner attachment, and the association primary key prevents
duplicates. Tag deletion cascades only to associations. Review-state `card_id` is the primary key;
its composite card relationship, required scheduling values, range/time checks, and restricted card
deletion are enforced by PostgreSQL. The temporary and development databases passed upgrade,
baseline downgrade, and re-upgrade; the full local backend suite passes 86 tests. The active-card,
reverse tag-filter, and due-review index definitions match their named patterns, but query-plan
effectiveness is not claimed. Review batches/events, the ER diagram, complete fixtures, and query
plans remain pending.

GitHub tracking:

- [Weeks 0–3 roadmap issue](https://github.com/JosephT5566/english-learning/issues/12)
- Training tickets: [#4](https://github.com/JosephT5566/english-learning/issues/4) through [#11](https://github.com/JosephT5566/english-learning/issues/11)

Required outputs:

- trace Google login and client-side token handling
- trace vocabulary retrieval from Google Apps Script
- trace review updates to Google Sheets
- inventory current Sheet fields and migration risks
- define English and Japanese card requirements
- draft the AI generation → editable draft → confirmation boundary
- propose the initial schema, API boundary, and trust-boundary diagram

## Open decisions

- Exact Unicode normalization/case-fold implementation and test vectors
- Canonical idempotency request serialization and scheduling algorithm version/test vectors
- Per-category repair policy for malformed imported scheduling rows
- Production API host and managed PostgreSQL provider
- AI provider and model
- Whether initial AI generation meets synchronous latency requirements
- Exact migration rollback window and handling of source-row deletions

## Current-state findings

- `getList` is unauthenticated. The Apps Script deployment is available to `Everyone` and executes
  as the script owner.
- `getList` mutates Sheet row order and contains zero-based/one-based index mismatches: intended
  `lastReview` and `reviewStage` sorts operate on `intervalDays` and `status`; the final
  `overdueDays` sort is correct.
- Review submission authenticates the allowlisted caller but trusts client-selected card IDs and
  client-calculated stage, ease factor, and dates.
- Review rows are written one at a time, formula updates run separately, and the success response
  is only `{ "ok": true }`; partial outcomes cannot be reconciled by the frontend.
- No Sheet data-validation or uniqueness rules were identified. `overdueDays` is derived as
  `TODAY() - nextReview`, while stored `intervalDays` is not updated by the current review payload.
- The most important persistence-migration risk is carrying client-controlled state transitions
  into PostgreSQL. The new backend must enforce ownership and derive and persist transitions
  transactionally.

## Current blockers

None for the active Issue #8 implementation. Remaining issue #4 uncertainties are documented rather
than hidden: blank sort behavior, the exact Apps Script exception envelope, concurrency/locking
outside the inspected function, and the absence of a repeated signed-in end-to-end update during the
documentation session.

## Next action

Implement owned idempotent `review_batches` and immutable `review_events` in revision
`20260902_0002` as the next bounded slice. Enforce cross-owner rejection, event transition checks,
and the owner/history index. Formal GitHub status for issues #4, #5, and #6 remains unverified.
