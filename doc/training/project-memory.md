# English Learning Project Memory

Last updated: 2026-09-11

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

Week 5 — frontend integration and cutover. Issue #24 is implemented and verified locally; review
the diff and remote CI before closing it. Production deployment and post-deployment verification
remain part of the later deployment milestone.

The Weeks 0-3 milestone is complete and audited locally in
[`issues/issue-12/README.md`](issues/issue-12/README.md). GitHub shows issues #4 through #11 closed,
and their merged implementations are present on `main`. Final closeout verification passed all 171
backend tests against healthy PostgreSQL 17, Ruff lint/format, the uv lock check, and the frontend
production build. Existing frontend build warnings and the upstream `TestClient` warning remain
visible. Remote CI, live Google verification, import, frontend cutover, deployment, and production
behavior are not claimed. Roadmap issue #12 is closed with every exit criterion checked. Ten bounded
Weeks 4-8 tickets are published as #22 through #31 without `ai-ready`; #22 and the synthetic
implementation boundary for #23 are complete locally.

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
now adds users, owned multilingual decks, confirmed learning cards, tags, card/tag associations,
current review state, owned review batches, and retained review events.
Cards use a composite owned deck foreign key, require nonblank term/meaning, share optional
English/Japanese fields, and embed one example. Tags have normalized per-owner identity; two
composite foreign keys prevent cross-owner attachment, and the association primary key prevents
duplicates. Tag deletion cascades only to associations. Review-state `card_id` is the primary key;
its composite card relationship, required scheduling values, range/time checks, and restricted card
deletion are enforced by PostgreSQL. The temporary and development databases passed upgrade,
baseline downgrade, and re-upgrade. Review batches enforce per-owner idempotency-key uniqueness;
events use composite owned batch/card relationships, complete before/after values, transition
checks, and duplicate-per-batch prevention. A deterministic synthetic fixture now spans every table
with English and Japanese decks/cards, shared tags, current states, and matching batch events. The
full local backend suite now passes 103 tests with one existing upstream warning. All named index
definitions match their access patterns, and a PostgreSQL 17 integration test builds a deterministic
representative dataset, runs `ANALYZE`, and verifies that all seven deliberate indexes are selected
by their executed query shapes. The implemented ER diagram covers every table, foreign key,
composite ownership constraint, cardinality, and deletion rule while separating future transaction
guarantees. Planner evidence is local and distribution-specific, not a performance benchmark;
atomic review behavior remains a future service responsibility.

Issue #9 is implemented and verified locally. The FastAPI service now exposes owner-scoped deck
list/detail, card list/detail with target-language and tag filtering, and due-review retrieval through
one English/Japanese contract. Management lists use `updated_at DESC, id DESC`; due review uses
`next_review_at ASC, card_id ASC` and carries a server-captured `as_of` instant across pages. Opaque
versioned cursors are bound to endpoint, filters, limit, and last sort tuple. A named temporary owner
dependency keeps clients from selecting identity until Issue #10 replaces it with verified auth.
Revision `20260903_0003` adds owner/update indexes, and the PostgreSQL planner test now covers nine
patterns. The full local backend suite passes 122 tests; Ruff format/lint and lock checks pass.

Issue #10 is implemented and verified locally. All `/v1` product routes now require a Google ID
token verified server-side for signature, issuer, configured audience, expiry, and verified-email
status. Verified Google `sub` values map to stable generated internal users; normalized email is
refreshable profile data rather than an ownership key. The reusable authenticated-user dependency
replaces temporary owner `1`, and every deck, card, and due-review read binds the internal owner ID.
Deck/card create, optimistic edit, and archive operations derive ownership from authenticated
context. Cross-owner IDs are masked as not found, including foreign deck IDs on card creation. The
authorization matrix matches unit and PostgreSQL horizontal-escalation tests. At that checkpoint the
full backend suite passed 152 tests; Ruff format/lint and lock checks passed. Live Google
verification, remote CI, and frontend cutover remain unverified or out of scope.

Issue #11 is implemented and verified locally. `POST /v1/reviews` accepts a bounded unique-card
batch plus a UUID idempotency key, derives all scheduling values from one backend clock, and commits
the owned batch, immutable before/after events, and current states in one transaction. Canonical
request hashes distinguish exact replay from conflicting key reuse. Target rows are locked in sorted
card-ID order, while optimistic versions make a racing different-key request stale; same-key races
replay one committed result. PostgreSQL tests cover multi-item success, authorization, validation,
exact and conflicting retries, simultaneous requests, and injected rollback. The full backend suite
passes 171 tests; Ruff checks pass. Frontend cutover, transient-deadlock retry policy, live traffic,
remote CI, and deployment remain unverified or out of scope.

Issue #22 is implemented and verified locally. A local one-time CSV CLI validates the complete
21-field legacy contract through trimmed NFC content, case-sensitive NFC source IDs, NFKC/case-fold
collection identity, canonical versioned SHA-256 hashes, and bounded content-safe diagnostics.
Revision `20260909_0004` persists only owner/deck-scoped `import_runs` and `import_items`; unchanged
snapshots replay the existing audit run. English and Japanese synthetic reports are deterministic,
and PostgreSQL tests prove cross-owner/language rejection plus zero card, tag, review-state, batch,
or event mutations. All later imported cards will start with fresh backend scheduling. The ignored
private 596-row CSV produced content-free aggregates of 11 accepted, 582 repairable, and 3 rejected:
one missing required meaning and one duplicate legacy ID affecting two rows. No private values or
report were committed. The full backend suite passed 187 tests against PostgreSQL 17; Ruff, format,
lock, migration-cycle, and whitespace checks passed. See
[`issues/issue-22/README.md`](issues/issue-22/README.md). These counts describe the Issue #22
checkpoint; the source diagnostics were subsequently corrected before the final Issue #23 dry run.

Issue #23 is implemented and verified locally. Revision `20260910_0005` adds confirmed-import runs
plus composite, owner-constrained source-to-card mappings. The local CLI rereads and reproduces the
approved Issue #22 snapshot, locks the dry run and existing active deck, and commits cards,
normalized owned tags, associations, deterministic fresh review states, mappings, and the completed
apply record in one transaction. Exact sequential and concurrent replay perform no product
mutations. Seven pre-commit failure points roll back completely; a post-commit client failure is
recovered by unchanged replay. Post-commit reconciliation checks counts, ownership, deck, hashes,
tags, archived state, fresh states, deterministic samples, and review history while persisting no
duplicate private content. The full backend suite passed 220 tests against PostgreSQL 17 with the
existing upstream warning; Ruff, format, lock, migration-cycle, and whitespace checks passed. After
the Issue #22 source diagnostics were corrected, the final zero-rejection private snapshot was
applied locally. Reconciliation reported matching expected and actual counts for 596 cards,
mappings, and fresh review states, 184 tags, 885 card/tag associations, zero archived cards, and no
review batches or events; every boolean check passed and no diagnostic codes were reported. The
private CSV and operational reports remain untracked. The runbook and sanitized evidence are
indexed in [`issues/issue-23/README.md`](issues/issue-23/README.md). Frontend cutover and the
source-of-truth transition are not claimed.

Issue #24 is implemented and verified locally. The English flip/swipe flow now reads
`GET /v1/reviews/due` and submits `POST /v1/reviews` through a typed bearer-authenticated frontend
client. `SwipeCards` emits decisions plus observed state versions and no longer calculates
schedules. One account-scoped command/key pair persists for 24 hours across ambiguous, retryable,
and same-account authentication recovery; success and definite rejection retire it, while stale
state visibly saves nothing and refetches. There is no Apps Script fallback or dual write. Ten
frontend contract/state/component tests, nine Playwright browser tests, and the complete 220-test
PostgreSQL-backed backend suite passed locally. See
[`issues/issue-24/README.md`](issues/issue-24/README.md).

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

The discovered browser preflight blocker is fixed: strict configurable CORS contracts pass, real
Uvicorn preflights succeed, and Chrome loaded 10 due cards through a live Google token and local
FastAPI/PostgreSQL. A real review write was deliberately not submitted because it changes the
user's learning schedule. Remote CI, the final production API/CORS values, deployment, and
post-deployment behavior remain unverified.
Repository-wide `npm run lint` still fails on the known Prettier baseline; touched frontend source
and tests pass targeted ESLint. The Issue #23 operator replay and backup/restore evidence limits also
remain documented.

## Next action

With explicit user approval, complete one real local review submission and confirm its PostgreSQL
transition. Then commit the CORS follow-up and push the feature branch for remote CI. Before any
production cutover, configure the real `PUBLIC_API_BASE_URL` and approved frontend CORS origin, then
follow the later deployment milestone.
