# Engineering Evidence Ledger

Use this ledger as the fact-checked bridge between repository work and later interview or resume preparation. It is not a list of planned achievements.

## Evidence standard

An entry is ready only when it includes:

- the concrete problem and constraints
- Joseph's decision and credible alternatives considered
- the implemented files, issue, or pull request
- relevant success, failure, authorization, or concurrency verification
- measured results when making performance or reliability claims
- limitations and remaining risks
- an explanation Joseph can give without generated notes

Use precise language such as “project,” “local load test,” or “deployed personal application.” Do not imply professional production scale, team ownership, user impact, or incidents that did not occur.

## Verification labels

- **Implemented:** Code exists but has not completed all relevant checks.
- **Verified locally:** Relevant automated or manual checks passed locally.
- **Verified in CI:** Relevant CI checks passed for the linked commit or pull request.
- **Deployed and verified:** The behavior was exercised in the deployed personal application.

## Evidence entry template

### Capability or milestone

- Date:
- Status:
- Problem:
- Constraints and invariants:
- Decision:
- Alternatives considered:
- Implementation references:
- Verification and failure cases:
- Measured result:
- Limitations:
- Five-minute explanation practiced:
- Candidate resume bullet:

## Evidence entries

### FastAPI and PostgreSQL service foundation

- Date: 2026-09-01
- Status: Verified locally
- Problem: Establish an independently runnable API whose process health remains meaningful during a
  temporary database outage.
- Constraints and invariants: Preserve the existing frontend runtime path; keep secrets out of
  errors and documentation; distinguish invalid startup configuration from transient PostgreSQL
  unavailability; release pooled connections during shutdown.
- Decision: Use a `uv`-managed FastAPI package, typed lifespan-loaded configuration, a lazy
  synchronous SQLAlchemy engine, PostgreSQL 17 through Docker Compose, and separate liveness and
  database-aware readiness probes.
- Alternatives considered: Import-time configuration and connection, database-coupled liveness,
  asynchronous SQLAlchemy, and broader infrastructure were rejected for this milestone because they
  weakened test isolation or added complexity without a demonstrated requirement.
- Implementation references: `apps/api/app/`, `apps/api/tests/`, `apps/api/pyproject.toml`,
  `apps/api/README.md`, and `compose.yaml`.
- Verification and failure cases: All 21 unit and PostgreSQL integration tests passed. A live
  database stop/restart exercise produced readiness `200 -> 503 -> 200` on one API process while
  liveness stayed `200`. Invalid production configuration was also verified to fail without exposing
  the recognizable test secret.
- Measured result: Local verification only; no production availability or performance claim.
- Limitations at this milestone: No SQLAlchemy session boundary, migration, domain schema,
  authentication, CI backend job, or deployed API existed yet. The next evidence entry adds the
  session, migration, and CI-definition foundations. One upstream FastAPI `TestClient` compatibility
  warning remains.
- Five-minute explanation practiced: Not yet.
- Candidate resume bullet: Not yet; revisit after CI and deployment evidence exist.

### Persistence, migration, and safe API error foundations

- Date: 2026-09-01
- Status: Verified locally
- Problem: Establish dependable transaction, migration, error, test, and CI boundaries before
  production domain tables make persistence failures costly.
- Constraints and invariants: Keep domain schema, authentication, and frontend cutover out of scope;
  use PostgreSQL rather than SQLite substitution; close sessions on every outcome; never serialize
  exception, validation-input, credential, SQL, or connection details to clients.
- Decision: Share one application-scoped SQLAlchemy session factory while each context manager owns
  one short-lived session and transaction; use an empty reversible Alembic baseline configured
  through the application's secret-safe settings; test migrations and transactions in isolated
  temporary PostgreSQL databases; standardize errors and request IDs; run frontend and backend CI as
  independent jobs.
- Alternatives considered: Caller-owned commits were rejected because ownership becomes ambiguous;
  SQLite integration tests were rejected because they do not exercise the deployed database dialect;
  committing a database URL in Alembic configuration was rejected because it duplicates validation
  and risks secret disclosure; introducing domain tables in the baseline was deferred to keep ticket
  scope and rollback evidence clear.
- Implementation references: `apps/api/app/database.py`, `apps/api/app/errors.py`,
  `apps/api/app/request_context.py`, `apps/api/migrations/`, `apps/api/tests/`,
  `.github/workflows/ci.yml`, and `doc/training/issues/issue-7/README.md`.
- Verification and failure cases: The persistent development database and a new temporary database
  both completed upgrade, downgrade, and re-upgrade. Tests prove commit, rollback, session cleanup,
  validation redaction, unexpected exception redaction, and request-ID correlation. The full suite
  passed 32 tests against PostgreSQL 17; Ruff, lock, YAML parse, and whitespace checks passed.
- Measured result: Local verification only; no remote CI, deployment, scale, performance, or
  production reliability claim.
- Limitations: The baseline contains no domain schema; GitHub Actions has not run on the branch;
  existing frontend type/lint debt remains; one upstream FastAPI `TestClient` warning remains.
- Five-minute explanation practiced: A focused transaction/PostgreSQL checkpoint was completed;
  the full five-minute explanation has not yet been practiced.
- Candidate resume bullet: Not yet; revisit after remote CI and later domain behavior provide a
  stronger end-to-end claim.

### Owned multilingual users and learning decks

- Date: 2026-09-02
- Status: Verified locally
- Problem: Begin the production relational model with user-owned English and Japanese decks whose
  integrity does not depend only on application validation.
- Constraints and invariants: A deck requires an existing owner and supported language codes;
  Google subject is the durable unique external identity; timestamps and versions must remain
  ordered and valid; retained learning data prevents physical owner deletion; English and Japanese
  must share one model.
- Decision: Use generated `BIGINT` user identities, generated UUID deck IDs, named PostgreSQL checks,
  an explicit restricted owner foreign key, unique `(id, owner_id)` for later owned child keys,
  and a per-owner partial unique creation-idempotency index.
- Alternatives considered: Email ownership was rejected because email is not the durable Google
  identity; separate language tables were rejected because ownership and deck behavior are shared;
  application-only validation was rejected because invalid direct or buggy writes would bypass it;
  cascading owner deletion was rejected because retained learning data requires stable ownership.
- Implementation references:
  `apps/api/migrations/versions/20260902_0002_add_multilingual_learning_domain.py`,
  `apps/api/tests/integration/test_users_and_learning_decks.py`, and
  `apps/api/tests/integration/test_migrations.py`.
- Verification and failure cases: PostgreSQL tests accept English and Japanese decks through one
  table and reject missing/nonexistent owners, unsupported languages, blank identity/content,
  duplicate Google subjects and replay keys, unpaired replay data, invalid versions/timestamps, and
  owner deletion with retained decks. Temporary and development databases passed upgrade, baseline
  downgrade, and re-upgrade. The full local suite passed 40 tests; Ruff and whitespace checks passed.
- Measured result: Local correctness verification only; no performance, deployment, or user-impact
  claim.
- Limitations: Tags, review state/events, complete fixtures, ER diagram, query-plan evidence, API
  use, authentication, frontend integration, remote CI, and deployment remain pending. One
  existing upstream FastAPI `TestClient` warning remains.
- Five-minute explanation practiced: The pre-implementation ownership and constraint checkpoint was
  completed; the implemented DDL has not yet received a full explanation checkpoint.
- Candidate resume bullet: Not yet; wait for the complete domain and API boundary.

### Confirmed multilingual learning-card integrity

- Date: 2026-09-03
- Status: Verified locally
- Problem: Store confirmed English and Japanese learning content without separate language tables or
  application-only ownership validation.
- Constraints and invariants: Every card requires meaningful term and meaning data, belongs to the
  declared owner's deck, permits optional language-specific fields, keeps one embedded example
  internally consistent, and preserves archive/history identities.
- Decision: Use one UUID card table, derive language through the required deck, repeat owner ID under
  a composite owned foreign key, embed one optional example, keep bounded related-word arrays, and
  use named PostgreSQL checks plus a partial active-card listing index.
- Alternatives considered: Separate language tables were rejected because shared ownership and
  review behavior would be duplicated; application-only owner checks were rejected because valid
  owner and deck IDs can still form an invalid pair; a child example table and JSON collection were
  rejected because only one non-independent example is currently required.
- Implementation references:
  `apps/api/migrations/versions/20260902_0002_add_multilingual_learning_domain.py`,
  `apps/api/tests/integration/test_learning_cards.py`, and
  `apps/api/tests/integration/test_migrations.py`.
- Verification and failure cases: Real PostgreSQL tests accept representative English and Japanese
  cards and reject missing or cross-owner decks, absent/blank confirmed content, malformed optional
  content, invalid example dependencies, oversized/null-containing related-word arrays, invalid
  part-of-speech values, invalid replay/version/time state, and physical deck deletion with retained
  cards. The combined backend suite passed 56 tests. The development database completed downgrade
  and re-upgrade and was left at revision `20260902_0002`.
- Measured result: The index definition matches the named active-deck listing pattern. No query-plan,
  latency, scale, deployment, or user-impact claim exists.
- Limitations: Per-entry related-word trimming and normalized uniqueness remain backend validation;
  tags, reviews, API use, authentication, complete fixtures, ER diagram, `EXPLAIN`, remote CI, and
  deployment remain pending. One existing upstream FastAPI `TestClient` warning remains.
- Five-minute explanation practiced: Not yet for the implemented card constraints.
- Candidate resume bullet: Not yet; wait for the complete domain and API boundary.

### Same-owner reusable card tags

- Date: 2026-09-03
- Status: Verified locally
- Problem: Support reusable tag organization without allowing a valid tag and valid card from
  different users to form an invalid association.
- Constraints and invariants: Tag identity is normalized per owner; duplicate card/tag attachment is
  forbidden; deleting a tag removes only its metadata associations; cards retain archive-first
  deletion behavior.
- Decision: Store tags as owned UUID resources, expose unique `(id, owner_id)` parent keys, repeat
  owner ID on the association, enforce two composite foreign keys, use `(card_id, tag_id)` as the
  association primary key, and add the reverse `(tag_id, card_id)` filtering index.
- Alternatives considered: Global tag uniqueness was rejected because tags are private per-user
  organization; independent card/tag foreign keys were rejected because they do not prove shared
  ownership; embedded tag arrays were rejected because reuse, rename, filtering, and normalized
  identity require a relational resource.
- Implementation references:
  `apps/api/migrations/versions/20260902_0002_add_multilingual_learning_domain.py`,
  `apps/api/tests/integration/test_tags.py`, and
  `apps/api/tests/integration/test_migrations.py`.
- Verification and failure cases: Real PostgreSQL tests accept the same normalized name for
  different owners and reject same-owner duplicates, missing/nonexistent owners, invalid content,
  cross-owner associations through either parent, duplicate attachment, owner deletion with tags,
  and physical card deletion with an association. Tag deletion removes the association while the
  card remains. The combined backend suite passed 69 tests, and the development migration completed
  downgrade and re-upgrade.
- Measured result: The reverse index definition matches `(tag_id, card_id)`. No query-plan, latency,
  scale, deployment, or user-impact claim exists.
- Limitations: The 20-tag cap requires a future locked transaction; review tables, API behavior,
  authentication, complete fixtures, ER diagram, `EXPLAIN`, remote CI, and deployment remain
  pending. One existing upstream FastAPI `TestClient` warning remains.
- Five-minute explanation practiced: Not yet for the implemented tag constraints.
- Candidate resume bullet: Not yet; wait for the complete domain and API boundary.

### Owned current review-state integrity

- Date: 2026-09-03
- Status: Verified locally
- Problem: Persist one authoritative current schedule per card without allowing missing, invalid, or
  cross-owner state.
- Constraints and invariants: Each card has at most one state; stage is 1-5, ease is 1.30-2.50,
  interval is nonnegative, version is positive, next review is required, and a present last review
  cannot be later than next review.
- Decision: Use `card_id` as the primary key, repeat owner ID under a composite owned-card foreign
  key, require scheduling values without database defaults, restrict physical card deletion, and
  index `(owner_id, next_review_at, card_id)` for stable due retrieval.
- Alternatives considered: An unrelated review-state ID was rejected because state identity is the
  card; independent owner/card foreign keys were rejected because they allow invalid ownership
  combinations; database scheduling defaults were rejected because the backend must explicitly own
  initial schedule creation.
- Implementation references:
  `apps/api/migrations/versions/20260902_0002_add_multilingual_learning_domain.py`,
  `apps/api/tests/integration/test_review_states.py`, and
  `apps/api/tests/integration/test_migrations.py`.
- Verification and failure cases: Real PostgreSQL tests accept a valid initial state and reject five
  individually omitted scheduling fields, duplicate and cross-owner states, every range boundary
  violation, invalid last/next ordering, and physical card deletion while state remains. The full
  backend suite passed 86 tests, and the development migration completed upgrade, baseline
  downgrade, and re-upgrade.
- Measured result: The due index definition matches the named access pattern. No query-plan,
  latency, scale, deployment, or user-impact claim exists.
- Limitations: Archived card/deck filtering is a future query concern; review batches/events, API
  transactions, authentication, `EXPLAIN`, remote CI, and deployment remain pending. One existing
  upstream FastAPI `TestClient` warning remains.
- Five-minute explanation practiced: Not yet for the implemented review-state constraints.
- Candidate resume bullet: Not yet; wait for the complete domain and API boundary.

### Owned idempotent review-history schema

- Date: 2026-09-03
- Status: Verified locally
- Problem: Preserve explainable review transitions and retry identity without permitting history to
  cross a user's batch/card ownership boundary.
- Constraints and invariants: A retry key is unique per owner; one card appears at most once per
  batch; history requires valid before/after schedules, consecutive versions, and consistent
  decision/quality and timestamp values.
- Decision: Store command-level idempotency metadata once on an owned batch, retain complete
  transition snapshots on generated-identity events, enforce both owned composite foreign keys, and
  add owner, card, and batch indexes only for named history/reconstruction patterns.
- Alternatives considered: Repeating idempotency keys on each event was rejected because retry
  identity belongs to the atomic command; independent foreign keys were rejected because valid IDs
  could still cross ownership; storing only resulting values was rejected because later scheduling
  changes would make historical transitions harder to explain.
- Implementation references:
  `apps/api/migrations/versions/20260902_0002_add_multilingual_learning_domain.py`,
  `apps/api/tests/integration/test_review_history.py`, and
  `apps/api/tests/integration/test_migrations.py`.
- Verification and failure cases: PostgreSQL tests accept a complete transition; reject missing
  batch/event fields, invalid ownership pairs, duplicate retries/events, invalid metadata and
  transition values; retain batch/card identities while events exist; and verify all three index
  definitions. A complete synthetic fixture verifies English and Japanese cards, shared tags,
  current states, and matching events through one schema and rejects duplicate loading. The
  development migration cycle passed, and the full backend suite passed 102 tests.
- Measured result: Local correctness and index-definition evidence only; no query-plan, performance,
  deployment, or user-impact claim.
- Limitations: The fixture demonstrates but does not enforce batch event counts or current-state
  agreement. Request-hash replay behavior, locking,
  atomic event/state writes, and the no-mutation API contract require the future review service.
  Remote CI and deployment remain pending; one upstream `TestClient` warning remains.
- Five-minute explanation practiced: Not yet for the implemented review-history constraints.
- Candidate resume bullet: Not yet; wait for the complete domain and API boundary.

### Representative multilingual-domain query plans

- Date: 2026-09-03
- Status: Verified locally
- Problem: Confirm that the indexes justified during schema design are useful to PostgreSQL for the
  exact access patterns they were intended to support.
- Decision: Test seven named queries on one deterministic representative-volume PostgreSQL 17
  dataset after `ANALYZE`, inspect executed JSON plans recursively, and assert intended index names
  without freezing planner costs or timings.
- Implementation references: `apps/api/tests/integration/test_query_plans.py` and
  `doc/training/issues/issue-8/query-plans.md`.
- Verification: The focused test passed with 100 users, 2,000 decks, 40,000 cards/states/tag links/
  events, and 4,000 batches. PostgreSQL selected the intended indexes for active deck cards,
  owner-language decks, tag filtering, joined due retrieval, owner history, card history, and batch
  reconstruction.
- Measured result: Intended index selection for the deterministic local distribution; focused test
  duration was 9.24 seconds including migration, data generation, analysis, and all queries. The
  complete PostgreSQL-backed API suite passed 103 tests in 43.69 seconds.
- Limitations: This is not a latency, throughput, production-scale, or future planner guarantee.
  Real data skew and growth can change plans; remote CI and deployment remain unverified.
- Five-minute explanation practiced: Not yet; complete during the Issue #8 learning checkpoint.
- Candidate resume bullet: Not yet; wait for the complete issue audit and later API usage.

### Deterministic multilingual read contracts

- Date: 2026-09-03
- Status: Verified locally
- Problem: Expose growing deck, card, and due-review collections without nondeterministic pages,
  language-specific APIs, ownership parameters, or internal database disclosure.
- Constraints and invariants: English and Japanese share contracts; every query remains owner-scoped;
  cursors must reject changed query shapes; due eligibility uses server time; internal failures stay
  behind the established safe envelope; authentication and writes remain out of scope.
- Decision: Use unique-tuple keyset ordering, opaque versioned cursors bound to normalized filters and
  limit, a cursor-retained due `as_of` snapshot, compact card summaries plus complete details, and an
  explicit temporary owner dependency that Issue #10 can replace without changing routes.
- Alternatives considered: Offset pagination was rejected because inserts can shift later pages;
  language-specific routes were rejected because domain behavior is shared; accepting owner IDs was
  rejected because identity must come from the server; returning raw SQLAlchemy failures was rejected
  as an information disclosure.
- Implementation references: `apps/api/app/reads.py`, `apps/api/app/pagination.py`, revision
  `20260903_0003`, `apps/api/tests/integration/test_read_apis.py`, and
  `doc/training/issues/issue-9/`.
- Verification and failure cases: Real PostgreSQL HTTP tests cover English/Japanese list/detail,
  language/tag/deck filters, empty results, exact multi-page traversal, malformed and incompatible
  cursors, invalid filters, non-disclosing resource lookup, and database-failure redaction. Planner
  tests verify management and due index selection. The full suite passed 122 tests; Ruff and lock
  checks passed.
- Measured result: Local correctness and index-selection evidence only; the full suite took 45.82
  seconds including isolated database creation/migrations. This is not endpoint latency evidence.
- Limitations: Owner `1` is a temporary local boundary, not authentication. No write API, frontend
  integration, production workload, remote CI, or deployment has been verified. Stable-dataset cursor
  tests do not promise a full database snapshot under concurrent content updates.
- Five-minute explanation practiced: Not yet; complete at the Issue #9 checkpoint.
- Candidate resume bullet: Not yet; wait for authentication and frontend integration.

### Backend authentication and horizontal owner isolation

- Date: 2026-09-04
- Status: Verified locally
- Problem: Move identity and ownership guarantees out of the browser before exposing PostgreSQL-backed
  learning data or mutations to a frontend.
- Constraints and invariants: Tokens must be verified for Google signature, issuer, audience, expiry,
  and verified email; durable identity uses Google subject rather than mutable email; all resource
  access requires the authenticated internal owner; clients cannot select create ownership.
- Decision: Use Google's Python verifier behind a replaceable boundary, upsert internal users by
  unique subject, inject an authenticated user into handlers, mask cross-owner resources as not
  found, bind ownership on create, and use optimistic versions plus archive-first deletion.
- Implementation references: `apps/api/app/auth.py`, `apps/api/app/writes.py`,
  `apps/api/app/reads.py`, `apps/api/tests/unit/test_auth.py`,
  `apps/api/tests/integration/test_auth_and_authorization.py`, and
  `doc/training/issues/issue-10/README.md`.
- Verification and failure cases: Unit tests cover missing, expired, invalid-audience, malformed,
  invalid-signature, missing-claim, and unverified-email cases without token disclosure. Real
  PostgreSQL HTTP tests prove stable subject mapping, owner-derived deck/card creation, cross-owner
  read/due/mutation denial, foreign-parent denial, successful owner edits/archives, and stale-version
  conflicts. The full suite passed 152 tests; Ruff and lock checks passed.
- Measured result: Local correctness evidence only; no live Google, production, latency, throughput,
  user-impact, or remote-CI claim.
- Limitations: The frontend still uses Google Apps Script and Sheets; review writes are not yet
  implemented; deployment and live token verification remain untested; one upstream `TestClient`
  warning remains.
- Five-minute explanation practiced: Not yet; complete the Issue #10 learning checkpoint.
- Candidate resume bullet: Not yet; revisit after frontend integration and remote verification.

### Transactional and idempotent review submissions

- Date: 2026-09-04
- Status: Verified locally
- Problem: Make a review command safe when clients retry after an ambiguous response or submit
  against state that another request changes concurrently.
- Constraints and invariants: One logical review creates one immutable event and one current-state
  transition; a bounded multi-card request is all-or-nothing; ownership and active status are
  rechecked in the write transaction; clients cannot supply resulting schedules; the same retry key
  cannot identify different content.
- Decision: Identify the owned command with a UUID key plus canonical SHA-256 request hash, acquire
  pessimistic target-row locks in deterministic card-ID order, validate optimistic state versions,
  calculate `srs-v1` transitions from one server clock, and commit the batch, events, and states in
  one PostgreSQL transaction. Reconstruct exact retries from stored event snapshots.
- Alternatives considered: Client-calculated schedules were rejected because they cross the trust
  boundary; idempotency key without a content hash was rejected because conflicting reuse would be
  ambiguous; optimistic checks without locks were rejected because multi-card races could partially
  validate; serializable isolation was not selected because targeted row locks express the current
  contention boundary more directly.
- Implementation references: `apps/api/app/reviews.py`, `apps/api/app/writes.py`,
  `apps/api/tests/unit/test_review_submissions.py`,
  `apps/api/tests/integration/test_review_submission_transactions.py`, and
  `doc/training/issues/issue-11/README.md`.
- Verification and failure cases: Real PostgreSQL HTTP tests cover successful one- and two-card
  commits, exact response replay without duplicate effects, conflicting key reuse, validation,
  cross-owner and inactive targets, stale whole-batch rollback, simultaneous same-key replay,
  simultaneous different-key stale conflict, and injected failure between event and state writes.
  The complete backend suite passed 171 tests; Ruff lint and formatting passed.
- Measured result: Local correctness and concurrency evidence only; no latency, throughput, scale,
  deployed reliability, or user-impact claim.
- Limitations: Frontend cutover, Google Sheets import, transient-deadlock retry policy, live Google
  verification, remote CI, and deployment remain unverified; one upstream `TestClient` warning
  remains.
- Five-minute explanation practiced: Not yet; complete the Issue #11 learning checkpoint.
- Candidate resume bullet: Not yet; revisit after frontend integration and deployed verification.

### Weeks 0-3 multilingual backend core

- Date: 2026-09-04
- Status: Verified locally
- Problem: Replace unsafe browser/Sheet trust assumptions with a coherent, testable backend core
  while preserving the current frontend runtime path during migration.
- Constraints and invariants: English and Japanese share one domain; identity and ownership are
  server-derived; growing reads remain deterministic; review history and current state change
  atomically; retries and concurrent conflicts cannot create duplicate logical transitions.
- Decision: Use one FastAPI/PostgreSQL modular monolith with database-enforced composite ownership,
  keyset pagination, server-verified Google identity, owner-scoped authorization, and a locked,
  versioned, idempotent review transaction.
- Alternatives considered: Separate language applications, email-based ownership, client-computed
  schedules, offset pagination, SQLite integration substitution, and idempotency keys without
  request hashes were rejected for concrete integrity or determinism reasons.
- Implementation references: Issues #4-#11, merged revisions `d78d708` through `107ed6c`, and
  `doc/training/issues/issue-12/README.md`.
- Verification and failure cases: All 171 unit and PostgreSQL integration tests passed against a
  healthy local PostgreSQL 17 service. Coverage includes constraints, migrations, deterministic
  reads, malformed cursors, token failures, horizontal access attacks, transaction rollback, exact
  retry, conflicting key reuse, and simultaneous review submissions. Ruff lint/format, uv lock, and
  the frontend production build passed.
- Measured result: The closeout backend suite took 61.73 seconds locally. Prior deterministic planner
  evidence verified intended index selection on 40,000-card fixtures. Neither result is a production
  latency, throughput, scale, availability, or user-impact claim.
- Limitations: PostgreSQL is not yet the application's source of truth. Sheet import/reconciliation,
  frontend cutover, live Google verification, remote CI confirmation, deployment, observability,
  backup/restore, and production behavior remain unverified. Existing frontend warnings and one
  upstream `TestClient` warning remain.
- Five-minute explanation practiced: A complete script is checked in and delivered with the Issue
  #12 retrospective; independent spoken practice remains for Joseph.
- Candidate resume bullet: Not yet. Revisit only after import, frontend cutover, and deployed
  verification create an honest end-to-end outcome.

### Read-only legacy CSV import validation

- Date: 2026-09-09
- Status: Verified locally
- Problem: Explain whether every legacy Sheet row can enter the shared English/Japanese model before
  any confirmed learning data is created.
- Constraints and invariants: The private snapshot cannot be committed or echoed; all 21 fields need
  an explicit outcome; identity and hashes must be stable; ownership is server-side; dry-run retries
  are idempotent; no card, tag, review-state, batch, or event mutation is allowed.
- Decision: Use a bounded local CSV CLI with a fixed namespace and snapshot timestamp, NFC content,
  case-sensitive NFC source IDs, NFKC/case-fold collection keys, canonical SHA-256 hashes, and
  versioned audit replay. Reset later imported cards to fresh scheduling while retaining safe
  diagnostics about ignored legacy scheduling quality.
- Implementation references: `apps/api/app/imports.py`, revision `20260909_0004`,
  `apps/api/tests/unit/test_imports.py`, `apps/api/tests/integration/test_import_dry_runs.py`, and
  `doc/training/issues/issue-22/`.
- Verification and failure cases: Deterministic synthetic English/Japanese reports, header/type/range
  failures, duplicate IDs, Unicode/collection repairs, private-content exclusion, cross-owner and
  language conflicts, unchanged replay, changed content, no-learning-mutation assertions, and full
  upgrade/downgrade/re-upgrade pass. The complete suite passed 187 tests against local PostgreSQL
  17; Ruff lint/format and the uv lock check passed.
- Measured result: Local correctness evidence only. The full suite took 71.33 seconds. This is not
  import throughput, production reliability, or user-impact evidence.
- Limitations: At the Issue #22 checkpoint, the private snapshot still had three rejected rows and
  no confirmed import had been performed. Those source diagnostics were corrected before the final
  dry run and Issue #23 apply; frontend cutover, remote CI, and deployment remained outside this
  checkpoint.
- Five-minute explanation practiced: Not yet; an explanation is delivered with the Issue #22 handoff.
- Candidate resume bullet: Not yet. Wait for confirmed import, reconciliation, and frontend cutover.

### Transactional confirmed CSV import and reconciliation

- Date: 2026-09-10
- Status: Verified locally; corrected private snapshot applied and reconciled
- Problem: Apply one approved private CSV snapshot exactly once without duplicate cards, silent
  source drift, partial product mutations, or an unrecoverable post-commit client outcome.
- Constraints and invariants: The importer must reread rather than reconstruct private content from
  audit rows; owner/deck/language and every snapshot/item hash must match; one owner/source namespace
  and source identity can be applied once; cards, tags, associations, fresh states, mappings, and
  the apply record commit together; reconciliation remains content-free.
- Decision: Lock the approved dry run and existing deck, bind source mappings through composite
  PostgreSQL foreign keys and unique constraints, perform the bounded import in one transaction,
  and persist reconciliation in a separate post-commit transaction. Exact retry returns the
  completed run; a pending reconciliation can be completed after an ambiguous client interruption.
- Implementation references: `apps/api/app/confirmed_imports.py`, revision `20260910_0005`,
  `apps/api/tests/integration/test_confirmed_import_*.py`, and
  `doc/training/issues/issue-23/`.
- Verification and failure cases: Tests cover first apply, existing-tag reuse behavior, exact and
  simultaneous replay, foreign/archived/language-conflicting targets, changed and deleted source
  rows, rejected input, audit hash drift, seven pre-commit rollback points, post-commit recovery,
  reconciliation mismatches, safe reports, and clean migration cycling. The full PostgreSQL-backed
  suite passed 220 tests in 77.81 seconds with one existing upstream warning; Ruff lint/format,
  `uv lock --check`, and whitespace checks passed.
- Measured result: The corrected final snapshot reconciled with 596 eligible rows, cards, mappings,
  and fresh review states; 184 tags; 885 card/tag associations; zero archived cards; and zero review
  batches or events. Expected and actual counts matched, all reconciliation booleans were true, and
  no diagnostic codes were reported. The synthetic suite timing is not an import-throughput,
  production-reliability, or scale claim.
- Limitations: The reported private-data run proves the first apply and reconciliation, but no
  operator result for an unchanged replay or backup/restore drill has been recorded. Frontend
  cutover, source-of-truth transition, remote CI, deployment, and production behavior remain
  unverified. The private CSV and operational reports remain untracked.
- Five-minute explanation practiced: In progress through the Issue #23 transaction walkthrough.
- Candidate resume bullet: Not yet. Revisit after the private import, frontend cutover, and deployed
  verification support an honest end-to-end claim.

### Authenticated review frontend cutover

- Date: 2026-09-11
- Status: Verified locally; not deployed
- Problem: Preserve the existing English flip/swipe workflow while replacing unauthenticated Sheet
  reads and client-calculated Sheet writes with authenticated transactional API calls that remain
  safe after ambiguous client outcomes.
- Constraints and invariants: ID tokens travel only in bearer headers; FastAPI owns identity,
  authorization, validation, and scheduling; a logical retry keeps an identical body/key pair;
  stale batches save nothing; failed writes never appear successful; review runtime has no fallback
  or dual writes.
- Decision: Use a typed runtime-validated Svelte API boundary and one 24-hour, Google-subject-scoped
  pending command. Retry ambiguous/auth/retryable failures exactly, retire definite/conflicting
  commands, and recover stale state by refetching rather than reconstructing mixed batches.
- Implementation references: `src/lib/api/client.ts`, `src/lib/api/contracts.ts`,
  `src/lib/review/pending.ts`, `src/routes/review/+page.svelte`,
  `src/lib/components/SwipeCards.svelte`, `tests/frontend/`, `tests/browser/`, and
  `doc/training/issues/issue-24/README.md`.
- Verification and failure cases: Eleven frontend contract/state/component tests and ten Playwright
  Chrome tests cover flip gating, exact retries, expiry/account isolation, invalid storage, loading,
  empty, authentication, retryable failure, success cleanup, stale conflicts, preserved imported
  part-of-speech labels, and usable mobile card height. The static subpath
  build and, after the CORS follow-up, all 231 backend tests passed against PostgreSQL 17; Ruff and
  uv lock checks passed. Five
  focused CORS contracts also cover allowed due/submission preflight, rejected origins/methods/
  headers, and browser-visible request IDs. Real Uvicorn preflights passed. Chrome used a live Google
  token to submit 10 due cards through local FastAPI/PostgreSQL; the success UI reported 10 saved,
  and a content-free database check found one batch, 10 distinct events, and 10 current states
  matching their recorded `srs-v1` results.
- Measured result: Local correctness only. The full backend suite took 83.28 seconds. This is not a
  production latency, reliability, scale, or user-impact claim.
- Limitations: Remote CI, final production CORS/API hosting values, deployment, post-deployment
  verification, and production rollback are unverified. Repository-wide Prettier drift remains.
- Five-minute explanation practiced: Prepared in the issue artifact; Joseph has not yet practiced the
  complete explanation end to end.
- Candidate resume bullet: Not yet. Revisit after deployment and post-deployment verification.

### Shared bilingual management read and write cutover

- Date: 2026-09-12
- Status: Parts 1 and 2 plus the local Part 3 configuration cutover are verified; production remains open
- Problem: Add owner-scoped English/Japanese deck and card management views without duplicating the
  application or allowing the legacy Sheet path back into normal read traffic.
- Constraints and invariants: One route/client/domain boundary serves both languages; missing
  language defaults visibly to English; invalid language performs no API request; successful JSON is
  runtime validated; cross-owner and missing details remain indistinguishable; static base paths
  remain valid; uncertain mutations never appear successful.
- Decision: Use shared query-language routes and conditional language fields. Generate committed
  TypeScript from a committed deterministic FastAPI OpenAPI export, check regeneration drift in CI,
  and keep runtime guards at the network boundary.
- Write decision: Require per-owner UUID creation keys backed by stored normalized request hashes;
  retain the exact account-scoped command for unclear retries, preserve values after stale edits, and
  refetch before confirming an unclear archive.
- UI primitive decision: Generate common Sheet and Alert Dialog components from shadcn-svelte,
  retaining Bits UI underneath, and compose them behind task-specific Drawer and ConfirmDialog
  wrappers for consistent modal focus, keyboard, scroll-lock, portal, and ARIA behavior without
  splitting the visual system.
- Runtime cutover decision: Remove the Apps Script variable from CI/deployment and require explicit
  endpoint injection in the preserved legacy wrapper. Gate deployment on a configured HTTPS FastAPI
  base URL rather than shipping an empty API base or an automatic fallback.
- Implementation references: `src/routes/decks/`, `src/routes/cards/`,
  `src/lib/components/LanguageTabs.svelte`, `src/lib/components/ReadError.svelte`,
  `src/lib/management/`, `src/lib/api/client.ts`, `src/lib/api/contracts.ts`,
  `src/lib/api/generated.ts`, `apps/api/openapi.json`, `.github/workflows/ci.yml`,
  `tests/frontend/management-contracts.test.mjs`, `tests/browser/management-read-flow.spec.ts`, and
  `doc/training/issues/issue-25/README.md`.
- Verification and failure cases: Local Svelte/TypeScript, targeted lint, static subpath build, 16
  frontend tests at the Part 2 checkpoint, all 236 PostgreSQL-backed backend tests, and 28 Playwright
  Chrome flows passed. Part 3 increased frontend coverage to 20 tests and repeated the static build,
  Svelte check, and browser suite.
  Browser cases cover English-default and
  Japanese navigation, conditional fields, archive filtering, loading, empty, invalid-language
  no-request, authentication cleanup, non-disclosing not-found, retryable errors, and mobile list
  usability. A combined review/management trace found `/v1` persistence traffic only at the
  configured FastAPI origin and no Apps Script URL.
- Mutation cases cover exact ambiguous-create retry, browser-local learned date, validation,
  successful and stale edits, authorization failure, and archive outcome reconciliation. Focused
  PostgreSQL tests prove deck/card exact replay, different-content conflicts, valid keys, ownership,
  and one review state; focused CORS tests cover `PATCH` and `DELETE`. A keyboard case verifies that
  the shared drawer dismisses with Escape through the accessible primitive.
- Measured result: Local correctness only; no latency, scale, reliability, or user-impact claim.
- Part 3 artifact evidence: CI/deployment contain no Apps Script variable; the production build
  contains the configured FastAPI base and no Apps Script variable, host, or endpoint fragment. The
  deploy validator rejects missing, HTTP, credential-bearing, query-bearing, and fragment-bearing
  API values.
- Limitations: The unused legacy wrapper and sanitized snapshot remain as evidence. No production API
  host is recorded, so remote CI, live management authorization, deployment, production network
  traffic, and the production rollback boundary are unverified.
- Five-minute explanation practiced: Prepared in the Issue #25 artifact; Joseph has not yet practiced
  it end to end.
- Candidate resume bullet: Not yet. Revisit after complete write cutover and deployment evidence.

### Provider-neutral API container boundary

- Date: 2026-09-12
- Status: Verified locally; provider and deployment remain open
- Problem: Make the FastAPI service independently deployable without root privileges, unlocked
  dependencies, implicit schema mutation, or a process wrapper that absorbs termination signals.
- Decision: Use a two-stage Python 3.12 slim image, synchronize runtime dependencies from `uv.lock`,
  run a direct Python/Uvicorn PID 1 as numeric UID/GID `10001:10001`, honor `PORT`, and keep Alembic
  as an explicit pre-deploy command.
- Implementation references: `apps/api/Dockerfile`, `apps/api/.dockerignore`,
  `apps/api/app/serve.py`, `apps/api/scripts/verify_container.sh`,
  `apps/api/tests/unit/test_serve.py`, `.github/workflows/ci.yml`, and
  `doc/training/issues/issue-26/README.md`.
- Verification: The locked image built locally; the configured and effective identity was
  `10001:10001`; `/health/live` succeeded through a random host port; SIGTERM completed FastAPI
  lifespan shutdown and exited `0` without OOM termination. Readiness returned safe `503` without
  PostgreSQL, and the final image contained no environment file or `uv` binary. Thirty-one focused
  serve/config/health tests and scoped Ruff checks passed. CI now repeats the image build and runtime
  smoke test.
- Measured result: Local correctness only; no production availability, traffic, latency, or graceful
  drain claim.
- Limitations: Registry, remote CI, provider, encrypted PostgreSQL, external secrets, production
  probes/CORS, migration execution, deployment, and rollback rehearsal are unverified.
- Candidate resume bullet: Not yet. Revisit after deployment and recovery evidence.

### Cloud Run and Neon staged-release rehearsal

- Date: 2026-09-15
- Status: Operator-verified production rehearsal and WIF publishing/migration automation; safe
  identifiers and data reconciliation remain open
- Problem: Prove that the deployed frontend/API/database path supports authenticated owned access,
  a real transactional review write, staged candidate verification, promotion, and
  schema-compatible application rollback.
- Decision: Keep Neon as the only production source of truth, migrate before deploying a
  zero-traffic Cloud Run candidate, require authenticated smoke checks before promotion, and roll
  application traffic back without automatically downgrading PostgreSQL.
- Implementation references: `deploy/cloud-run/smoke.sh`, `deploy/cloud-run/release.sh`,
  `.github/workflows/migrate-production.yml`, `.github/workflows/publish-api-image.yml`,
  `.github/workflows/deploy-api-candidate.yml`, and `doc/training/issues/issue-26/runbook.md`.
- Verification: The operator reported that the deployed GitHub Pages frontend's authenticated
  read/create API calls succeeded. The production smoke script printed
  `Public health and authenticated owned-read checks passed` and
  `Controlled review write and exact idempotent replay passed`. The operator then reported
  successful smoke checks for the zero-traffic candidate, the promoted revision, and the compatible
  rollback target. The operator later reported successful remote runs of the protected WIF image
  publishing and production migration workflows.
- Measured result: One live owned-read path and one controlled review transaction with exact
  same-key replay succeeded; smoke checks passed across candidate, promotion, and rollback stages.
  This is not a latency, availability, scale, or SLA measurement.
- Limitations: This evidence is operator-reported and does not include workflow run/revision IDs,
  timings, raw logs, complete restored-data counts/relationships, independent database-role proof,
  or a remote execution of the new candidate-deployment workflow.
- Candidate resume bullet: Deployed a containerized FastAPI/PostgreSQL application to Cloud Run and
  Neon using staged candidate verification, an authenticated transactional smoke test with
  idempotent replay, and schema-compatible traffic rollback. Describe this as project experience,
  not professional production-service ownership.

### Issue #27 candidate request correlation

- Date: 2026-09-18
- Status: Verified on a zero-traffic Cloud Run candidate; production and alert delivery remain open.
- Problem: Trace a reported request from its response ID to a privacy-safe backend event.
- Implementation references: `apps/api/app/request_context.py`,
  `doc/training/issues/issue-27/candidate-verification.md`, and
  `doc/training/issues/issue-27/failure-alert.md`.
- Verification: CI passed for commit `3704a2a`; protected image publish and candidate deploy runs
  succeeded. Cloud Run kept the existing revision at 100% traffic. One candidate `GET /v1/cards`
  returned 401 with an ID matching exactly one parsed stdout completion event. The payload keys
  matched the allowlist, with route template, stable auth code, status, and duration. A separate
  platform request log still had a raw URL field.
- Measured result: One candidate request was correlated. No traffic rate, latency distribution,
  availability, alert delivery, or production incident result is inferred.
- Limitations: The operator reports completing manual candidate smoke, but its result, exact
  calls, and outputs were not shared. There is no promotion for this commit, deployed database/unexpected failure
  event, or live failure alert delivery test. A separate temporary 401
  policy matched a new candidate event; the operator reported receiving its email and finding the
  alert, then deleted the test policy. The first 5xx failure policy is enabled and its exact
  configuration was read back; see `doc/training/issues/issue-27/failure-alert.md` and
  `doc/training/issues/issue-27/notification-test.md`. The platform-log exclusion remains unapplied.

### Owner-safe semantic vocabulary retrieval

- Date: 2026-09-26
- Status: Deployed and verified through the stable Cloud Run service URL and deployed frontend;
  bounded provider-backed Top-K quality smoke passed.
- Problem: Expose meaning-based vocabulary retrieval without allowing the vector ranking path or
  client filters to bypass authenticated ownership and lifecycle predicates.
- Constraints and invariants: Reject malformed and unauthenticated requests before provider spend;
  make one bounded query-embedding call; filter owner, archive, language, optional deck, active
  model, ready vector, and current content hash in SQL before Top-K; never return raw vectors or
  another owner's data; distinguish provider failure from a successful empty result.
- Decision: Use exact pgvector cosine ranking inside the existing FastAPI/PostgreSQL service, with a
  stable distance/score contract and explicit complete/partial/empty coverage metadata. Keep HNSW
  deferred until measurements justify it.
- Implementation references: `apps/api/app/semantic_search.py`,
  `deploy/cloud-run/validate_semantic_smoke.py`, `.github/workflows/smoke-api-candidate.yml`, the
  static Svelte `/search` route, and `doc/training/issues/issue-40/README.md`.
- Verification and failure cases: Deterministic real-PostgreSQL tests proved ordering and exclusion
  of cross-owner, archived, and missing-vector rows; malformed/unauthenticated input made zero fake
  provider calls; provider timeout returned retryable 503. The full backend and frontend checks plus
  one critical browser flow passed. The operator reported that zero-traffic revision
  `english-learning-api-98034f911a63` passed owned read, controlled review write/replay, and one
  explicitly enabled provider-backed semantic smoke with five results, complete 596/596 coverage,
  and request ID `f54491aa-b291-4d7a-b142-42035b4feb67`. The operator then promoted the same
  revision and reported that the stable service URL passed health, authenticated owned read, and
  semantic smoke with five results, complete 596/596 coverage, and request ID
  `d581e030-222e-497d-9c1b-38ea4bd7b9b3`. The operator also reported that the deployed search page
  worked correctly against the promoted API without retaining private result content. A human check
  of the fixed recovery-after-difficulty query found an expected directly related concept at rank 1
  and was recorded only as a pass with rank bucket.
- Measured result: A warm production SQL Editor plan ranked 596 eligible English vectors in 10.054
  ms with a 27 kB in-memory Top-K sort and no temporary I/O. The candidate semantic request took
  2.058828 seconds end to end, and the post-promotion stable-URL request took 2.265995 seconds. These
  are individual observations, not p50/p95, scale, availability, or SLA claims.
- Limitations: Candidate, promotion, stable-URL, deployed frontend, and bounded quality results are
  operator-reported. One human-judged query does not establish aggregate production retrieval
  quality, user impact, latency distribution, or an SLA; broader evaluation remains Issue #41.
- Five-minute explanation practiced: Ownership and SQL-plus-vector boundary are documented; an
  end-to-end spoken practice has not yet been recorded.
- Candidate resume bullet: Built and deployed owner-safe semantic vocabulary search using FastAPI,
  PostgreSQL/pgvector, and Vertex AI, with SQL-enforced authorization and lifecycle filters,
  deterministic ranking/leakage tests, staged Cloud Run verification, and a base-path-safe Svelte
  search flow. Describe this only as deployed personal-project evidence and keep point latency
  observations distinct from production performance claims.
