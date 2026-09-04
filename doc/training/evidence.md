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
