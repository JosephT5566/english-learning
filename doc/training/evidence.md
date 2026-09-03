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
