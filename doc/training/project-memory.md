# English Learning Project Memory

Last updated: 2026-08-31

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

Week 1 — backend foundation, Issue #6.

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

Issue #6 backend-foundation implementation is in progress. The initial decisions are recorded in
[`issues/issue-6/README.md`](issues/issue-6/README.md): use `uv`, place the independent Python package
under `apps/api/`, use typed secret-safe configuration with disposable local PostgreSQL defaults,
keep liveness independent of PostgreSQL, return safe database-aware readiness results, and manage the
database engine through FastAPI lifespan startup and shutdown. The `uv` package and lockfile exist,
and the first liveness vertical slice is implemented through an application factory, isolated health
router, explicit response model, and HTTP-level unit test. The unit test, Ruff lint, Ruff formatting,
Uvicorn factory startup/shutdown, and a real `200` liveness request passed locally. Pytest currently
emits one upstream FastAPI `TestClient`/`httpx` deprecation warning. `apps/api/README.md` is the
canonical reference for verified API commands. Typed configuration, database lifecycle, Compose,
readiness, and PostgreSQL integration tests do not exist yet.

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

None. Remaining issue #4 uncertainties are documented rather than hidden: blank sort behavior,
the exact Apps Script exception envelope, concurrency/locking outside the inspected function, and
the absence of a repeated signed-in end-to-end update during the documentation session.

## Next action

Implement the Issue #6 typed configuration boundary and unit tests. Reject the disposable local
database URL in production and prove that invalid configuration cannot expose a recognizable fake
password before adding database lifecycle or readiness behavior. Keep domain tables, authentication,
card/review endpoints, and production deployment out of scope. Formal GitHub status for issues #4
and #5 remains unverified.
