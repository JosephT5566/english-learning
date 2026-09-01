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
- Limitations: No SQLAlchemy session boundary, migration, domain schema, authentication, CI backend
  job, or deployed API exists yet. One upstream FastAPI `TestClient` compatibility warning remains.
- Five-minute explanation practiced: Not yet.
- Candidate resume bullet: Not yet; revisit after CI and deployment evidence exist.
