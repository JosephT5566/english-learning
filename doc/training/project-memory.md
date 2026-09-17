# English Learning Project Memory

Last updated: 2026-09-17

## Purpose

Build defensible full-stack and backend engineering depth by evolving the existing English-learning
application into a deployed multilingual product. This repository is project evidence, not
professional production-service experience.

Implementation and test results are authoritative. Repository documents may lag behind the code.
Production statements must distinguish repository-verified evidence from operator reports.

## Current system

- One repository with a SvelteKit 2/Svelte 5 static frontend and a Python FastAPI API.
- GitHub Pages hosts the frontend; Google Identity Services provides browser sign-in.
- Cloud Run in Singapore and Neon PostgreSQL in AWS Singapore are the selected production services.
- PostgreSQL is the sole writable source of truth for the deployed product.
- The backend verifies Google identity, maps it to internal users, and enforces ownership.
- English review and shared English/Japanese deck and card management use the FastAPI API.
- Review writes are transactional and idempotent; scheduling is derived by the backend.
- Legacy Apps Script/Sheet code remains only as rollback and migration evidence and is absent from
  normal runtime traffic and frontend deployment configuration.
- AI-assisted authoring and semantic search are not active product capabilities.

## Active milestone

**Week 6 - operational ownership, Issue
[#27](https://github.com/JosephT5566/english-learning/issues/27), not yet started.** Issue
[#26](issues/issue-26/README.md) is closed after the staged deployment and rollback rehearsal.

The provider-neutral container and Cloud Run/Neon release contract are complete locally. The
repository defines production TLS requirements, separate version-pinned runtime and migration
secrets, migration-before-candidate ordering, zero-traffic candidate verification, explicit
promotion, and schema-compatible application rollback.

### Repository-verified locally

- Issue #25 completed the FastAPI frontend cutover and bilingual management read/write boundary.
- The API image runs as numeric non-root user `10001:10001`, excludes development dependencies,
  honors `PORT`, exposes meaningful health endpoints, and shuts down cleanly on SIGTERM.
- Production configuration rejects insecure PostgreSQL connections and separates runtime and
  migration credentials.
- Protected workflows publish immutable commit-tagged images, invoke the Secret Manager-backed
  migration job through WIF, and deploy a zero-traffic candidate.
- The Issue #26 checkpoint passed 251 PostgreSQL-backed tests, Ruff lint and format checks, the `uv`
  lock check, Bash syntax and invalid-input checks, and whitespace validation.

### Operator-reported production results

These results are useful operational context but are not independently established by committed
repository evidence unless a linked artifact says otherwise:

- Cloud Run, Neon, and the GitHub Pages frontend are deployed.
- The Neon schema and initial data transfer completed.
- Live readiness and authenticated owned read/create calls passed.
- A controlled review write and exact idempotent replay passed.
- Candidate, post-promotion, and schema-compatible rollback smoke checks passed.
- The WIF image-publishing and production-migration workflows ran successfully.
- The operator checked effective GCP IAM permissions: the API runtime and migration job identities
  can access only their respective Neon connection secrets. No independent IAM artifact is recorded.
- The operator replaced `app_user` with `app_runtime_limited`, updated the runtime secret, observed
  `can_create_schema = false` and `can_create_in_public = false`, passed a smoke test, and removed
  the old role in Neon UI.
- The operator reports that Deploy API candidate produced revision
  `english-learning-api-156073439e6e`; authenticated candidate smoke, traffic promotion, and
  stable-URL checks were reported successful.

### Remotely verified release result

- Deploy API candidate run
  [`35185725352`](https://github.com/JosephT5566/english-learning/actions/runs/35185725352)
  completed successfully, including the zero-traffic candidate and public-health verification
  steps. This does not independently verify the operator-run authenticated smoke or promotion.

### Issue #26 evidence limits

- The operator deferred the initial `pg_dump`/`pg_restore` reconciliation. A read-only procedure is
  documented in the Issue #26 runbook, but transfer completeness remains unverified.
- The runtime PostgreSQL role restriction and GCP secret-access boundary are operator-reported,
  without independent role/IAM audit artifacts.
- The candidate run/revision IDs and successful job result are recorded; final traffic allocation
  and timings have not been independently captured.

## Completed milestone index

- **Weeks 0-3 - multilingual backend core:** Issues #4-#11 traced the legacy system, designed and
  implemented the shared domain, established FastAPI/PostgreSQL foundations, added deterministic
  reads, enforced authentication and ownership, and made review writes transactional and
  idempotent. The audited closeout is in
  [`issues/issue-12/README.md`](issues/issue-12/README.md).
- **Week 4 - controlled Sheets migration:** Issue
  [#22](issues/issue-22/README.md) implemented read-only validation and Issue
  [#23](issues/issue-23/README.md) implemented transactional import, replay, and reconciliation.
- **Week 5 - frontend cutover:** Issue [#24](issues/issue-24/README.md) moved English review to the
  authenticated API; Issue [#25](issues/issue-25/README.md) completed shared bilingual management
  reads and writes plus runtime configuration cutover.
- **Week 6 - deployment:** Issue [#26](issues/issue-26/README.md) is closed. The operator-reported
  production outcome and remaining evidence limits are recorded there.

Use the linked issue indexes for acceptance criteria, implementation detail, verification commands,
and historical limitations. Use [`evidence.md`](evidence.md) only when preparing or updating
interview evidence.

## Durable decisions

- Continue in this repository as a modular monolith; deploy frontend and backend independently.
- Use Python/FastAPI first, SQLAlchemy 2 and Alembic, and PostgreSQL as the source of truth.
- Use one owner-scoped, language-aware model for English and Japanese.
- Verify identity, ownership, validation, and state transitions on the backend.
- Use PostgreSQL constraints and explicit transactions for critical invariants.
- Preserve Sheets only through controlled migration and rollback; do not dual-write.
- Use Cloud Run `asia-southeast1` and Neon AWS Singapore under the documented low-traffic budget.
- Treat AI input and output as untrusted; AI may create an editable draft but never a confirmed card.
- Defer semantic search, queues, caches, and additional infrastructure until a measured need exists.

## Open decisions

- AI provider and model.
- Whether observed AI-generation latency and failure behavior justify synchronous or durable
  asynchronous generation.
- The operational duration of the rollback-compatible migration window.

## Known non-blocking limitations

- Repository-wide `npm run lint` retains known Prettier baseline drift; touched frontend files pass
  scoped checks.
- The upstream FastAPI `TestClient` warning remains visible in backend tests.
- Earlier private import data and operational reports remain untracked; committed evidence contains
  only sanitized aggregates and fixtures.

## Next action

Define the first acceptance boundary for Issue #27: privacy-safe request tracing and an actionable
failure signal. The initial restored-data reconciliation remains deferred, not verified; Issue #27's
independent backup/restore proof is a separate boundary.

## Context pointers

- Active issue: [Issue #27](https://github.com/JosephT5566/english-learning/issues/27)
- Completed deployment issue: [`issues/issue-26/README.md`](issues/issue-26/README.md)
- Active roadmap section: [Week 6](full-stack-backend-plan.md#week-6--deployment-and-operational-ownership)
- Current operational sequence: [`issues/issue-26/runbook.md`](issues/issue-26/runbook.md)
- Historical learning logs: [`logs/`](logs/), searched only when needed
- Legacy-system baseline: [`current-state-flow-trace.md`](current-state-flow-trace.md)
