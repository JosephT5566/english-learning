# English Learning Project Memory

Last updated: 2026-09-27

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
- AI-assisted authoring is not an active product capability. Semantic search is implemented,
  promoted on the API, and verified through the stable Cloud Run service URL and deployed search
  page; its bounded provider-backed Top-K quality smoke passed.

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
- Issues #38-#41 implemented and evaluated the semantic vocabulary retrieval MVP. Keep the current
  limited search, model/canonical text, and exact scan; gate tutor #42 on a measured relevance/
  no-answer boundary that handles negative and ambiguous queries.

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

Issue #41's evaluation boundary is complete with an **iterate** decision; see
[`issues/issue-41/README.md`](issues/issue-41/README.md). The sanitized metric and gate, deterministic
versus provider evaluation split, failure matrix, operator commands, result template, and
content-safe production inspection SQL were frozen before inspecting final Issue #41 results. The
local lexical baseline reproduced macro nDCG@5 `0.5655` and grade-2 Recall@5 `0.6429`; 21 focused
unit tests and 9 PostgreSQL/pgvector integration tests passed, and the inspection SQL executed
successfully against the empty disposable schema. The operator-reported 17-request Vertex run
passed the synthetic gate with macro nDCG@5 and grade-2 Recall@5 both `1.0`; it reported 314 input
tokens, provider-request p50 `1354.4 ms`, and p95 `3464.7 ms`. The operator-reported Neon aggregate
showed 596/596 current ready English embeddings, with zero null vectors or stale hashes, on
PostgreSQL 18.6 and pgvector 0.8.6. Its coverage plan completed in `2.030 ms` with shared hits only.
The stored-vector Top-5 diagnostic ranked 596 current authorized candidates with a 25 kB in-memory
Top-N sort and no temporary I/O. Two executions took `132.961 ms` and `122.666 ms`, each with 205
shared reads; the repeated result rejected the tentative cold-versus-warm explanation. Because the
materialized database vector is scanned 596 times, that diagnostic is not API-shaped latency. A new
content-safe plan used one synthetic vector constant in the API parameter's role and ranked 596
candidates in `130.020 ms` after `38.884 ms` planning, with a 25 kB Top-N sort, no temporary I/O,
3,665 shared hits, and 262 shared reads. This is a read-heavy/cold-compute observation, not a warm
distribution; compared with Issue #40's separate 10.054 ms shared-hit-only plan, it demonstrates
cache/environment sensitivity and still gives no measured reason for HNSW. Next, complete the
cache/environment sensitivity and still gives no measured reason for HNSW.

The 2026-09-27 deployed workload returned 30/30 HTTP 200 responses with complete 596/596 coverage;
end-to-end p50 was `1789.565 ms`, p95 was `2793.855 ms`, and one first request took `10824.294 ms`.
The later corpus check found zero active exact-term cards for all 17 expected terms in the nine
positive queries: deployed fixture v1 was based on synthetic concepts absent from the owned corpus.
Its grades and hit/miss rates are invalid as relevance evidence, while latency, availability,
coverage, and the unthresholded negative-control behavior remain valid. Next, build and preflight a
sanitized corpus-grounded v2 fixture. Eight consenting active-card terms now ground 10 queries; the
frozen v2 SHA-256 is `4756caf33424266c5722b344124a5d226427fc065dece6e02c8746fd7e86a5a4`.
The operator-reported Neon preflight found exactly one active English card for every v2 target, so
the corpus-grounding gate passed. The v2 run returned 10/10 HTTP 200 responses with complete 596/596
coverage. Eight of nine positive queries had a grade-2 Top-5 result (`0.8889`); seven were rank 1,
while ambiguous severance missed. The negative control returned five grade-0 neighbors, confirming
that unthresholded Top-K is unsafe as automatic tutor context. The evidence supports keeping search
but iterating before tutor use. The 10-query cost probe reported 84 input tokens, provider p50
`1280.6 ms`, p95 `1713.1 ms`, and a published-rate estimate of `$0.0000126`; actual billing was not
inspected. Eleven focused PostgreSQL/pgvector tests passed the empty/unindexed, partial, edit,
archive, version, outage, cross-owner, and ordering boundaries. Issue #41 is complete with an
**iterate** decision: keep the current search/model/canonical text and exact scan, but do not begin
tutor work until a frozen score/no-answer gate handles negative and ambiguous queries. Next define
that bounded retrieval iteration or return to Issue #27's remaining operational evidence gaps.

Issue #40's authenticated semantic-search API and static Svelte search flow are implemented; see
[`issues/issue-40/README.md`](issues/issue-40/README.md). Focused deterministic PostgreSQL/pgvector
tests verify ranking and the owner/archive/missing-vector boundary; the full 289-test backend suite,
frontend checks/build, and one critical browser flow pass. An operator-supplied read-only production
plan over 596 English candidates observed a 10.054 ms warm exact query with an in-memory 27 kB Top-K
sort and no temporary I/O; no HNSW need was measured. The candidate smoke tooling now supports one
explicit provider-backed semantic request with content-safe contract, ordering, coverage, request-ID,
and total-time validation. The operator reported that candidate revision
`english-learning-api-98034f911a63` passed owned-read, controlled write/replay, and provider-backed
semantic smoke: five results, complete 596/596 coverage, request ID
`f54491aa-b291-4d7a-b142-42035b4feb67`, and one 2.058828-second end-to-end observation. The operator
then promoted that revision and reported a successful stable-URL smoke: five results, complete
596/596 coverage, request ID `d581e030-222e-497d-9c1b-38ea4bd7b9b3`, and one 2.265995-second
observation. The operator also reported that the deployed search page worked correctly against the
promoted API and that the fixed recovery-after-difficulty query returned an expected directly
related concept at rank 1. Issue #40 is complete; Issue #41 contains the broader quality, cost,
failure, and release decision.

Issue #39's retryable embedding lifecycle is merged and verified; see
[`issues/issue-39/README.md`](issues/issue-39/README.md). On an isolated Neon branch, the operator
reported a successful migration cycle, runtime privilege checks, 597-card owner-bounded backfill,
zero hash mismatches, unchanged card/review counts, and an empty replay with no provider work.
The operator subsequently reported the production migration, a dedicated Cloud Run Job backfill
of all 597 cards, matching aggregate/hash checks, an empty replay, and a zero-traffic candidate
environment smoke test using the runtime service identity. No production traffic promotion or
real-card retrieval quality is established. Next action: promote and verify the candidate through
the existing release process, then begin Issue #40's owner-safe retrieval API boundary.

Issue #27 still has the operational evidence gaps below; #38 does not close them.

Issue #27's request, review, and import signals passed local verification. A
synthetic isolated restore passed, while the owner deferred an independent
Neon-to-GCS backup and schedule for cost reasons; see
[`issues/issue-27/backup-restore.md`](issues/issue-27/backup-restore.md). A
labeled local readiness failure drill is in
[`issues/issue-27/incident-exercise.md`](issues/issue-27/incident-exercise.md).
Protected workflows deployed commit `3704a2a` as a zero-traffic candidate.
One 401 response matched exactly one allowlisted stdout event by request ID;
the platform request log still had a raw URL field. See
[`issues/issue-27/candidate-verification.md`](issues/issue-27/candidate-verification.md).
PR #43 was merged as `dc06acc`. The operator reports publishing and deploying
the new candidate, smoke testing it, moving traffic to it, and smoke testing
again through the service URL. Exact smoke calls, response IDs, and outputs
were not shared. A read-only Cloud Run check showed revision
`english-learning-api-dc06acc6807d` at 100% traffic; production stdout had
parsed request events for readiness and API reads. See
[`issues/issue-27/candidate-verification.md`](issues/issue-27/candidate-verification.md).
Routing preflight found only `_Required` and `_Default` sinks, no user-defined
log metrics, and no Monitoring policies at that time. The operator created an
email channel, reported receiving a temporary candidate 401 alert, and deleted
the test policy; see
[`issues/issue-27/notification-test.md`](issues/issue-27/notification-test.md).
The first 5xx failure policy is now enabled with the exact bounded filter,
email channel, 30-minute provisional interval, and runbook; see
[`issues/issue-27/failure-alert.md`](issues/issue-27/failure-alert.md).

Next, correlate one production response ID with its application event and
revisit the narrow platform-log exclusion. The actual 5xx alert condition
still needs a safe trigger or natural matching event and delivery verification.
The initial restored-data reconciliation remains deferred.

## Context pointers

- Active issue: [Issue #27](https://github.com/JosephT5566/english-learning/issues/27)
- Issue #27 baseline: [`issues/issue-27/README.md`](issues/issue-27/README.md)
- Completed deployment issue: [`issues/issue-26/README.md`](issues/issue-26/README.md)
- Active roadmap section: [Week 6](full-stack-backend-plan.md#week-6--deployment-and-operational-ownership)
- Current operational sequence: [`issues/issue-26/runbook.md`](issues/issue-26/runbook.md)
- Historical learning logs: [`logs/`](logs/), searched only when needed
- Legacy-system baseline: [`current-state-flow-trace.md`](current-state-flow-trace.md)
