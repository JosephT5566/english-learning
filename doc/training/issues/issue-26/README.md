# Issue #26 - Deploy API and PostgreSQL with a safe release contract

Last updated: 2026-09-14

Source: [GitHub Issue #26](https://github.com/JosephT5566/english-learning/issues/26)

## Status

Part 1, the provider-neutral API container boundary, is implemented and verified locally. Part 2
selects Cloud Run in Singapore plus Neon PostgreSQL in AWS Singapore, with Neon as the only source
of truth. The checked-in release contract now enforces production PostgreSQL transport security,
separates version-pinned runtime and migration secrets, runs migration before a zero-traffic
candidate, and defines smoke/promotion/rollback operations. Cloud resources, remote execution,
production CORS, live traffic, and rollback rehearsal were still open at that local checkpoint.

On 2026-09-14, the operator reported that Cloud Run was deployed, the Neon schema was upgraded from
the local checkout with `uv run alembic upgrade head`, and data was transferred with
`pg_dump`/`pg_restore`. The operator also observed the deployed `/health/ready` response
`{"status":"ready","checks":{"database":"ok"}}`, confirming that the running API could execute its
database readiness query. Owner-scoped reads/writes, restored-data reconciliation, secret/role
separation, and rollback have not yet been independently verified from repository evidence. Future
schema upgrades now have a protected, OIDC-based GitHub Actions path that invokes the Secret
Manager-backed Cloud Run migration job; remote execution of that workflow remains unverified.

## Delivery Slices

1. Build and continuously verify a locked non-root container with meaningful health endpoints and
   graceful termination. Completed locally.
2. Select the API and managed PostgreSQL providers from actual workload, cost, TLS, migration-job,
   secret-storage, backup, and rollback needs. Completed locally.
3. Configure production identity, encrypted database access, exact CORS, secrets, and probes; then
   deploy without importing private data automatically.
4. Run migrations as a reviewed pre-deploy job, smoke-test owned reads and a review write, stage the
   frontend cutover, and rehearse application rollback inside the compatibility window.

## Part 1 Container Contract

- `apps/api/Dockerfile` uses a two-stage Python 3.12 Debian slim build. Runtime dependencies are
  synchronized from `uv.lock` with development dependencies excluded.
- The final image does not contain the `uv` installer. Application files, migrations, and the
  virtual environment are owned by the numeric runtime identity `10001:10001`.
- `python -m app.serve` is the direct PID 1 command. It validates the platform `PORT`, binds all
  interfaces, creates the existing FastAPI factory, and gives Uvicorn eight seconds to drain on
  termination.
- `/health/live` remains database-independent. `/health/ready` keeps its fresh PostgreSQL probe and
  will be the traffic-readiness signal after an encrypted production database is configured.
- Alembic is present for a separate release job. The web process does not migrate at startup, so
  multiple instances cannot race schema changes and a migration failure can stop rollout before
  traffic moves.
- `.env` files, tests, local virtual environments, and caches are excluded from the image context.

## Local Verification

Verified on 2026-09-12:

- Locked image build: passed.
- Configured and effective runtime identity: `10001:10001`.
- Liveness through a randomly published local port: HTTP success.
- Readiness without PostgreSQL: safe HTTP `503`; the final image contained neither `/app/.env` nor
  the build-only `uv` binary.
- Docker SIGTERM with a ten-second platform deadline: FastAPI application shutdown completed and
  the container exited `0`; it was not OOM-killed.
- Focused serve/config/health tests: 31 passed with one existing upstream TestClient warning.
- Ruff check and format check for the new Python files: passed.
- CI now builds the same image and runs `scripts/verify_container.sh` after the PostgreSQL-backed
  backend suite.

This proves the local container contract only. It does not prove a registry push, remote CI, a
deployed revision, encrypted database connectivity, production probes, or live graceful draining.

Part 2 local verification on 2026-09-13:

- All 251 backend tests passed against PostgreSQL 17; Ruff check, Ruff format check, and the uv lock
  check passed.
- Production configuration tests accept certificate verification or required TLS channel binding,
  reject weaker transport settings, and keep the database password out of errors.
- Both Cloud Run scripts pass Bash syntax checks. Their invalid-input paths fail safely, and the
  checked-in `gcloud` help confirms every deployed probe flag; database readiness remains an
  explicit pre-promotion smoke check because Cloud Run has no readiness-probe deploy setting.
- `git diff --check` passed.

This does not verify Neon connectivity, GCP IAM or Secret Manager permissions, a remote migration,
candidate behavior, traffic promotion, or rollback.

## Part 2 Provider And Release Decision

- Use Cloud Run `asia-southeast1` for the API and Neon AWS Singapore for PostgreSQL.
- Neon is the only writable source of truth. Do not add a database-provider switch, dual write, or
  continuous Cloud SQL replica.
- Keep the expected low-traffic bill inside a USD 10 monthly ceiling. Start Cloud Run at zero minimum
  and one maximum instance; accept cold starts and Neon Free recovery/SLA limits.
- Use a pooled least-privilege runtime URL and a direct schema-owning migration URL. Store them as
  distinct version-pinned Secret Manager secrets injected into different Cloud Run identities.
- Require verified TLS or TLS plus required channel binding in production configuration.
- Run Alembic as a single-task, zero-retry pre-deploy job. Deploy the resulting application revision
  with a candidate tag and zero production traffic.
- Promote only after health, ownership, and controlled idempotent-write checks. Roll application
  traffic back only to a schema-compatible revision; never automatically downgrade production.
- Defer independent GCS backup/restore proof and incident response to Issue #27.

The executable configuration and operator sequence are in [`runbook.md`](runbook.md) and
`deploy/cloud-run/`.

A Traditional Chinese walkthrough of the provider choice, Artifact Registry and Console deployment,
Neon bootstrap, database roles, and migration automation is in
[`deployment-notes.zh-TW.md`](deployment-notes.zh-TW.md).

The manual production migration workflow is in `.github/workflows/migrate-production.yml`. It
requires an already-pushed commit-tagged image, a protected `production` GitHub environment, and
Workload Identity Federation. It never receives the Neon URL and never restores application data.

## Next Action

Configure the protected GitHub environment and Google Workload Identity Federation, then exercise
the migration workflow against an already-current schema. Capture its safe job/revision evidence,
verify live health plus owner-scoped reads/writes, reconcile the restored data, and rehearse
application rollback before closing the issue.
