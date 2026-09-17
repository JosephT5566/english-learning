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
[#27](https://github.com/JosephT5566/english-learning/issues/27), local signals and synthetic restore verified.** Issue
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
- Defer queues, caches, and additional infrastructure until a measured need exists.
- Plan the semantic vocabulary retrieval MVP after Issue #27 through
  [#38-#41](../product/rag-semantic-search-mvp.md); gate the later tutor #42 on measured retrieval
  quality. This is planned scope, not implemented evidence.

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

The operator deferred Issue #27's zero-traffic candidate verification. Local
review outcome logging now occurs after transaction commit and distinguishes
new batches from replays. Local dry-run and confirmed-import commands now emit
bounded outcome events that preserve whether the database apply committed.
An independent synthetic `pg_dump` archive was restored into a disposable
network-isolated PostgreSQL 17 container. Schema, counts, relationships, and
representative multilingual records matched; see
[`issues/issue-27/backup-restore.md`](issues/issue-27/backup-restore.md).
The owner explicitly deferred an independent Neon-to-GCS backup and recurring
backup schedule to avoid additional cost. Repository workflows have no cron
trigger; the checked GCP project has Cloud Scheduler disabled and only the
manual migration Cloud Run Job. This is a conscious exception to Issue #27's
original production backup/restore criterion, not completion evidence.
The first failure-alert filter, owner, provisional one-event condition, and
response steps are in [`issues/issue-27/failure-alert.md`](issues/issue-27/failure-alert.md).
Cloud Logging accepted the filter but found no deployed application event; no
policy or notification channel was created. A labeled local readiness failure
exercise recorded manual detection, request-ID correlation, simulated
mitigation, recovery, and corrective actions in
[`issues/issue-27/incident-exercise.md`](issues/issue-27/incident-exercise.md).
Next, prepare the deferred zero-traffic candidate verification so the
operator can check the deployed event and privacy before activating the alert.
The deployed request-ID lookup, proposed narrow platform-log exclusion (raw
URLs currently retain for 30 days in `_Default`), and live alert verification
remain open. The initial restored-data reconciliation remains deferred.

## Context pointers

- Active issue: [Issue #27](https://github.com/JosephT5566/english-learning/issues/27)
- Issue #27 baseline: [`issues/issue-27/README.md`](issues/issue-27/README.md)
- Completed deployment issue: [`issues/issue-26/README.md`](issues/issue-26/README.md)
- Active roadmap section: [Week 6](full-stack-backend-plan.md#week-6--deployment-and-operational-ownership)
- Current operational sequence: [`issues/issue-26/runbook.md`](issues/issue-26/runbook.md)
- Historical learning logs: [`logs/`](logs/), searched only when needed
- Legacy-system baseline: [`current-state-flow-trace.md`](current-state-flow-trace.md)
