# Issue #26 - Deploy API and PostgreSQL with a safe release contract

Last updated: 2026-09-12

Source: [GitHub Issue #26](https://github.com/JosephT5566/english-learning/issues/26)

## Status

Part 1, the provider-neutral API container boundary, is implemented and verified locally. Hosting,
managed PostgreSQL, encrypted connections, external secret storage, production CORS, deployment,
and rollback rehearsal remain open.

## Delivery Slices

1. Build and continuously verify a locked non-root container with meaningful health endpoints and
   graceful termination. Completed locally.
2. Select the API and managed PostgreSQL providers from actual workload, cost, TLS, migration-job,
   secret-storage, backup, and rollback needs.
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

## Next Decision

Select the API host and managed PostgreSQL provider together. The decision must record expected low
traffic, minimum monthly cost, region, enforced TLS, secret storage, connection limits/pooling,
one-off migration support, automated backups and restore testing, and application-revision rollback.
