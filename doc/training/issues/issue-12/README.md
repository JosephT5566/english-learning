# Issue #12 - Weeks 0-3 Milestone Retrospective

- Date: 2026-09-04
- Status: Complete; GitHub issue closed
- Scope: Issues #4 through #11

## Outcome

The first four training milestones produced a documented legacy boundary and a PostgreSQL-backed
FastAPI core for English and Japanese learning. The frontend still uses Google Apps Script and
Google Sheets, so this closes the backend foundation rather than the product migration.

GitHub shows issues #4 through #12 closed. The #4-#11 merged revisions are `d78d708`, `fd0fe7f`,
`eb9d624`, `b1227ae`, `bf0503d`, `100f570`, `8cae84b`, and `107ed6c` on `main`. Issue #12's
checklist and exit criteria are checked, its closeout comment records verification limits, and the
next roadmap is published as issues #22 through #31.

## Exit-criteria audit

| Criterion                                                                           | Result      | Evidence and limits                                                                                                                                                 |
| ----------------------------------------------------------------------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Existing behavior and Sheet contracts are documented before backend work.           | Met         | `doc/training/current-state-flow-trace.md` records auth, vocabulary, review, all 21 fields, trust gaps, and a sanitized fixture.                                    |
| The API and PostgreSQL start reproducibly and pass independent checks.              | Met locally | `apps/api/README.md`, `compose.yaml`, health tests, migration tests, and the 2026-09-04 closeout run against healthy PostgreSQL 17. Deployment is not yet verified. |
| English and Japanese share a constrained relational model.                          | Met         | Revision `20260902_0002`, PostgreSQL constraint tests, bilingual fixture, and the Issue #8 ER diagram.                                                              |
| Read APIs have deterministic pagination and tested database behavior.               | Met         | Issue #9 keyset contracts and PostgreSQL HTTP/planner tests. The tests cover stable traversal, not snapshot isolation during arbitrary concurrent edits.            |
| Google identity is verified server-side and ownership attacks are tested.           | Met locally | Issue #10 token-verifier unit tests and PostgreSQL horizontal-escalation tests. A live Google token/key exchange is not yet verified.                               |
| Review writes are atomic, idempotent, and safe under the chosen concurrency policy. | Met locally | Issue #11 transaction, replay, conflict, simultaneous-request, and injected-rollback tests. No production throughput or universal deadlock-freedom claim is made.   |
| Project memory, weekly logs, and verified evidence stay current.                    | Met         | This retrospective, `doc/training/project-memory.md`, `doc/training/logs/2026-W36.md`, and `doc/training/evidence.md`.                                              |

## Verification snapshot

Final closeout verification on 2026-09-04:

- `docker compose ps postgres`: PostgreSQL 17 service healthy.
- `RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest -q`: 171 passed, one upstream
  FastAPI/Starlette `TestClient` warning.
- `uv run ruff check app tests`: passed.
- `uv run ruff format --check app tests`: passed; 34 files already formatted.
- `uv lock --check`: passed; 48 packages resolved.
- `npm run build`: passed with the existing route, unused-CSS, accessibility, and non-reactive
  assignment warnings.

This is local correctness evidence. Remote CI, live Google verification, import, frontend cutover,
deployment, and production behavior remain future work.

## What changed in our understanding

1. The largest legacy risk was not merely replacing Sheets. The browser currently selects card IDs
   and calculates review transitions, so identity, ownership, scheduling, and atomicity had to move
   together into one backend transaction.
2. Repeating `owner_id` under composite foreign keys is intentional integrity data. It lets
   PostgreSQL reject cross-owner relationships even when each individual ID exists.
3. A unique idempotency key prevents duplicate command rows but does not prove that retries contain
   the same request. The canonical request hash closes that ambiguity.
4. Deterministic lock order reduces overlapping-batch deadlock risk, while optimistic versions make
   the losing logical update explicit. This is a policy, not a claim that PostgreSQL can never
   deadlock.
5. The frontend and migration now represent the largest delivery risk. The backend is locally
   verified but unused by the deployed user flow, and PostgreSQL is not yet the source of truth.

## Corrections that improved the design

- Integration tests use PostgreSQL rather than SQLite because the constraints, locking, indexes,
  and migrations are PostgreSQL behavior.
- Due-review cursors retain the first page's server `as_of` time so wall-clock movement cannot add
  newly due rows midway through stable traversal.
- Concurrent review tests use independent clients; a shared test client had serialized requests
  before they reached PostgreSQL.
- Authentication updates the stored email only when it changes, avoiding an unrelated user-row lock
  that had accidentally serialized same-user review tests.
- The frontend's existing type/lint debt was recorded instead of being folded into backend tickets.

## Five-minute explanation

The project began as a static SvelteKit application where Google Identity ran in the browser, reads
came from an unauthenticated Apps Script endpoint, and review updates trusted browser-selected row
IDs and browser-calculated schedules. We first documented those contracts so the migration would
preserve behavior without preserving unsafe trust assumptions.

We chose a modular monolith: the existing static frontend and one independently deployable FastAPI
service backed by PostgreSQL. English and Japanese share decks, cards, tags, and review tables.
Language-specific fields are nullable on the shared card model, while ownership and review behavior
remain common. Composite foreign keys repeat owner IDs deliberately so cross-user relationships are
invalid at the database boundary.

Reads use keyset pagination. Management pages sort by update time and UUID; due reviews sort by due
time and card UUID. Cursors are opaque and bound to filters, limits, endpoint identity, and sort
position. Due cursors also preserve the server time captured on the first page. That avoids offset
page drift and time-based eligibility drift in the behavior we explicitly support.

Authentication verifies Google ID tokens on the server and maps Google's stable subject to an
internal user. Email is profile data, not an ownership key. Authorization is separate: every query
combines the requested resource ID with the authenticated internal owner, and cross-owner detail
requests are masked as not found. Creates derive ownership only from the authenticated context.

Review submission is one PostgreSQL transaction. A UUID idempotency key plus a canonical request
hash identifies the logical command. The service locks all target rows in sorted card-ID order,
checks ownership, active status, and expected versions, calculates every transition from one backend
clock, writes immutable events, and updates current state. Exact retries reconstruct the stored
result; conflicting key reuse fails; a concurrent different command becomes stale. Any failure
rolls back the batch, events, and states together.

The important limit is that this is a locally verified backend core, not a completed migration or
production reliability claim. The next milestone must import and reconcile Sheet data before the
frontend cuts over. After that come deployment and operations, the human-confirmed AI draft flow,
and evidence-based hardening.

## Evidence-based Weeks 4-8 ticket plan

The next work stays sequential. Each issue must end with relevant checks, a learning-log update, and
a five-minute decision explanation.

### Week 4 - Google Sheets migration

1. **[#22 - Design and implement dry-run Sheet validation](https://github.com/JosephT5566/english-learning/issues/22).** Add import run/item schema, stable source
   identity, content hashing, all 21 legacy-field mappings, normalization rules, and row diagnostics.
   Prove malformed headers, types, ranges, duplicate IDs, and scheduling repair decisions without
   mutating confirmed learning data.
2. **[#23 - Implement idempotent import, reconciliation, and recovery](https://github.com/JosephT5566/english-learning/issues/23).** Cover first import, unchanged
   replay, changed rows, deleted source rows, injected interruption, counts/hashes/sample comparison,
   and a source-of-truth/rollback runbook.

### Week 5 - Frontend integration and cutover

3. **[#24 - Cut the existing review flow over behind a fallback switch](https://github.com/JosephT5566/english-learning/issues/24).** Add the typed API/auth boundary,
   replace Sheet due reads and review writes, preserve flip-before-answer behavior, keep retry keys
   across ambiguous failures, and test loading/empty/auth/conflict/retry/server states.
4. **[#25 - Add shared English/Japanese card management and remove runtime Sheet access](https://github.com/JosephT5566/english-learning/issues/25).** Reuse contracts
   and components, add create/edit/archive, verify critical end-to-end flows, perform read-before-write
   cutover, and document rollback consistency limits.

### Week 6 - Deployment and operations

5. **[#26 - Deploy the API and PostgreSQL with a safe release contract](https://github.com/JosephT5566/english-learning/issues/26).** Add a non-root container,
   encrypted database connection, secret handling, production CORS, migration-before-deploy,
   backward compatibility, staged rollout, and rollback rehearsal.
6. **[#27 - Add observability, backup/restore proof, and an incident exercise](https://github.com/JosephT5566/english-learning/issues/27).** Use structured secret-safe
   logs, correlation IDs, useful request/auth/review/import/database metrics, actionable alerts,
   restore verification, and one written incident timeline with corrective actions.

### Week 7 - AI-assisted authoring

7. **[#28 - Implement owned, validated AI generation and editable drafts](https://github.com/JosephT5566/english-learning/issues/28).** Add strict bilingual input and
   output contracts, immutable raw provenance, editable validated fields, versions, limits, timeout
   behavior, redacted provider failures, and no path from model output directly to confirmed cards.
8. **[#29 - Implement idempotent draft confirmation, user review, and evaluation](https://github.com/JosephT5566/english-learning/issues/29).** Create at most one card
   transactionally, reject stale/double confirmation and late results, add visible correction/failure
   states, measure synchronous latency before considering durable async work, and run a small labeled
   English/Japanese evaluation.

### Week 8 - Hardening and interview readiness

9. **[#30 - Measure and harden the completed product](https://github.com/JosephT5566/english-learning/issues/30).** Record repeatable read/write load baselines, diagnose
   one real bottleneck before optimizing, compare results, and complete security reviews for auth,
   CORS, secrets, validation, logging, AI boundaries, retention, and cost controls.
10. **[#31 - Complete reviewer documentation and interview evidence](https://github.com/JosephT5566/english-learning/issues/31).** Refresh setup/demo/architecture/API/
    migration/operations docs, create a concise case study, record the five-minute explanation and
    30-minute walkthrough, run project-grounded mock interviews, and keep future ideas in a backlog.

## Guardrails retained

- Do not apply `ai-ready` automatically.
- Do not start semantic search, Go, microservices, queues without measured need, or Kubernetes.
- Do not describe planned or merely local work as deployed or professional production evidence.
