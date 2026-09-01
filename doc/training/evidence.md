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
