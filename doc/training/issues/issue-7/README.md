# Issue #7 - Persistence Foundations, Migrations, Tests, and CI

- Date started: 2026-09-01
- Status: Complete locally; publication pending
- Outcome: Create dependable database and verification foundations before domain implementation

## Scope boundary

This ticket adds explicit SQLAlchemy session and transaction ownership, Alembic with a reversible
baseline, PostgreSQL integration-test patterns, a stable API error envelope, and independent backend
CI checks. Production domain tables, authentication, and frontend cutover remain out of scope.

## Implementation order

1. Define and test session/transaction ownership.
2. Configure Alembic and verify upgrade, downgrade, and re-upgrade against PostgreSQL.
3. Define the common safe API error envelope.
4. Add independent backend CI checks and document the complete verification path.

This order establishes resource ownership before migrations depend on it and keeps each failure
boundary independently testable.

## Session and transaction boundary

- FastAPI lifespan creates one application-scoped `sessionmaker` bound to the existing lazy engine.
- `database_transaction()` creates one short-lived session for one unit of work.
- The context manager owns the transaction: it commits after successful caller completion, rolls
  back when caller work or commit fails, re-raises the original exception, and always closes the
  session.
- Callers must not commit, roll back, or close the yielded session. Later service functions will
  express database operations while this boundary retains transaction ownership.
- `autoflush=False` avoids query-triggered writes at surprising points. Explicit `flush()` remains
  available when a service needs database-generated values before commit.
- `expire_on_commit=False` keeps already-loaded values usable after commit without an implicit
  refresh, which is useful when mapping results to response models after the unit of work ends.

### Verification - 2026-09-01

- Unit tests verify factory options and the exact success, caller-failure, and commit-failure paths.
- The FastAPI lifespan test verifies that the application stores the factory created from its own
  engine and still disposes the engine during shutdown.
- `uv run pytest tests/unit -q`: 23 passed with the existing upstream `TestClient` warning.
- `RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest -q`: all 25 existing tests passed against the
  Compose PostgreSQL service with the same warning.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed; ten files were already formatted.
- The later integration slice now supplements these controlled tests with real PostgreSQL
  commit/rollback verification.

## Alembic baseline and PostgreSQL migration pattern

- Alembic is a direct API runtime/deployment dependency and lives inside the independently runnable
  `apps/api/` package.
- `migrations/env.py` loads the existing validated settings and creates and disposes the engine
  through the same secret-safe application functions. The URL is not committed to `alembic.ini`.
- Revision `20260901_0001` is an empty, reversible baseline. Domain tables remain out of scope.
- The migration integration fixture creates a uniquely named temporary PostgreSQL database. It does
  not mutate the persistent development database and removes only its own database after each test.
- The test begins with zero tables, upgrades to `head`, downgrades to `base`, and upgrades to `head`
  again. The only table is Alembic's version table, proving the baseline does not introduce domain
  schema.

## PostgreSQL transaction integration pattern

- Unit substitutes prove exact session cleanup calls on success, caller failure, and commit failure.
- A real-PostgreSQL integration test creates an isolated probe table, commits one unit of work,
  raises during a second unit of work, and verifies that only the committed value remains.
- Integration execution requires `RUN_POSTGRES_INTEGRATION_TESTS=1` and a reachable PostgreSQL
  server. There is no SQLite dependency or fallback path.

## Stable API error envelope

- Failures use `{ "error": { "code", "message", "retryable", "request_id", "details"? } }`.
- A server-generated UUID is returned in both `error.request_id` and `X-Request-ID`. Successful
  responses also receive the header for future log correlation.
- Application errors explicitly select their public code, fallback message, retryability, safe
  details, and headers. Framework 404/405 errors and request validation errors are translated into
  the same envelope.
- Validation translation returns only safe field paths, field codes, and fallback messages. It
  omits the rejected value and validation context.
- Unexpected exceptions always return `internal_error`; tests inject a fake credential-bearing
  connection failure and prove its exception type, host, and secret are absent from the response.

## Independent CI boundaries

- `.github/workflows/ci.yml` defines independent `frontend` and `backend` jobs with no dependency
  between them.
- The frontend job preserves the currently viable locked production build.
- The backend job synchronizes `uv.lock`, runs Ruff lint and format checks, and runs the full pytest
  suite against an explicit `postgres:17-alpine` service.
- The existing GitHub Pages deployment workflow remains separate and unchanged.
- Existing frontend `npm run check` and `npm run lint` debt is not hidden: local verification still
  fails with the previously documented Svelte/type issues and broad pre-existing formatting drift.
  Fixing unrelated frontend code remains outside Issue #7.

## Acceptance criteria

- [x] A clean PostgreSQL database upgrades from zero to the latest migration.
- [x] The development migration downgrades and upgrades again without manual repair.
- [x] Integration tests require PostgreSQL and never silently substitute SQLite.
- [x] Database sessions close on success, caller failure, and commit failure.
- [x] CI definitions run frontend and backend checks independently.
- [x] Error responses omit stack traces, credentials, SQL, and internal connection details.
- [x] Verification commands and actual results are recorded below and in the weekly log.

## Final local verification - 2026-09-01

- Compose `postgres:17-alpine`: healthy through OrbStack.
- Development CLI cycle: `alembic upgrade head -> current -> downgrade -1 -> upgrade head ->
  current` passed and ended at `20260901_0001 (head)`.
- Isolated migration test: one passed against a freshly created temporary PostgreSQL database.
- `RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest -q`: 32 passed with one existing upstream FastAPI
  `TestClient` compatibility warning.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed; 18 files already formatted.
- `uv lock --check`: passed; 39 packages resolved from the committed lock.
- `git diff --check`: passed.
- `.github/workflows/ci.yml`: parsed successfully as YAML; remote GitHub Actions execution is not
  claimed until the branch is pushed.
- `npm run build`: passed with existing route, unused-CSS, accessibility, and reactivity warnings.
- `npm run check`: failed with the known 6 errors and 6 warnings in existing frontend files.
- `npm run lint`: failed on pre-existing repository-wide Prettier drift in 28 files.

## Learning checkpoint

Completed on 2026-09-01. Joseph explained that `database_transaction()` owns commit, rollback, and
session cleanup; a caller exception rolls back the transaction so the inserted row does not persist;
and `close()` belongs in `finally` so cleanup occurs after success or failure. He also explained that
SQLite cannot fully verify PostgreSQL behavior because the databases implement different features
and semantics. Concrete examples include PostgreSQL types and constraints, transactional DDL,
locking and concurrency, isolation behavior, SQL dialect differences, and the Psycopg driver path.

## Next step

Review the final diff, then commit and publish Issue #7 before starting the production domain schema
in the next ticket.
