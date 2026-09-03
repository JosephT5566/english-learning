# English Learning API

FastAPI backend for the English Learning application. Run the commands below from `apps/api/`.

## Requirements

- Python 3.12 or newer
- `uv`

## Setup

Create or synchronize the local environment from the committed lockfile:

```bash
uv sync --locked
```

## Configuration

Local development works with safe disposable defaults. To override them, create an optional `.env`
file beside `pyproject.toml`; use `.env.example` as the field reference.

| Variable | Default | Constraint |
| --- | --- | --- |
| `APP_ENV` | `local` | `local`, `test`, or `production` |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` |
| `DATABASE_URL` | Local disposable PostgreSQL URL | Must use the `postgresql+psycopg` driver |
| `DATABASE_CONNECT_TIMEOUT_SECONDS` | `2` | Integer from 1 through 10 |

Production must explicitly override `DATABASE_URL`; the disposable local default is rejected.
Database URLs are treated as secrets and must not be printed or logged.

FastAPI creates the SQLAlchemy engine during lifespan startup and disposes its connection pool during
shutdown. Engine creation is lazy and does not require PostgreSQL to be available; database
availability is reported separately by the readiness endpoint.

## Database migrations

Start PostgreSQL before running migrations. Upgrade a clean or existing development database to the
latest checked-in revision with:

```bash
uv run alembic upgrade head
```

During development, revert the latest revision and apply it again with:

```bash
uv run alembic downgrade -1
uv run alembic upgrade head
```

Use `uv run alembic current` to inspect the applied revision. Downgrades are a development
verification and recovery tool, not an assumed production rollback strategy. The initial Issue #7
baseline is intentionally empty. Issue #8 revision `20260902_0002` begins the production domain
schema with owned users, multilingual learning decks, confirmed learning cards, and reusable
per-owner tags. It also stores one current review state per card with database-enforced ownership,
scheduling ranges, timestamp ordering, and due-review indexing. Owned review batches provide
per-user retry-key uniqueness, while review events retain complete constrained before/after
snapshots for history and response reconstruction.

## Local PostgreSQL

From the repository root, start PostgreSQL and wait for its health check:

```bash
docker compose up -d --wait postgres
```

Inspect or stop the service with:

```bash
docker compose ps
docker compose stop postgres
```

## Start the development server

```bash
uv run uvicorn app.main:create_app --factory --reload
```

The development server listens on `http://127.0.0.1:8000` by default. `--reload` is for local
development only.

## Verify liveness

With the development server running, use a second terminal:

```bash
curl -i http://127.0.0.1:8000/health/live
```

The expected response body is:

```json
{"status":"ok"}
```

Liveness reports whether the API process can handle requests. It intentionally does not query
PostgreSQL.

## Verify readiness

Readiness runs a bounded `SELECT 1` query against PostgreSQL:

```bash
curl -i http://127.0.0.1:8000/health/ready
```

Available PostgreSQL returns `200`:

```json
{"status":"ready","checks":{"database":"ok"}}
```

Unavailable PostgreSQL returns `503` without connection details:

```json
{"status":"not_ready","checks":{"database":"unavailable"}}
```

## Tests and checks

```bash
uv run pytest tests/unit -q
uv run ruff check .
uv run ruff format --check .
```

With local PostgreSQL available, run the opt-in integration tests with:

```bash
RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest tests/integration -q
```

The root Compose definition and integration suite are verified against `postgres:17-alpine` through
OrbStack. Integration tests are opt-in and fail if PostgreSQL is unavailable; they never substitute
SQLite. The migration test creates a uniquely named temporary PostgreSQL database, verifies
`upgrade -> baseline downgrade -> upgrade`, and removes that database afterward. Domain constraint
tests also run in isolated temporary databases. Production startup commands are still pending.

The cycle verifies both the head and reverted baseline at the assertions' level of detail. The
current baseline intentionally has no domain tables, so the test checks that only
`alembic_version` remains after downgrade. It does not prove complete schema equivalence for every
historical revision: if an older revision later contains tables, its expected columns, constraints,
indexes, defaults, and any important data transformations need revision-specific assertions.

### How migrated database tests work

The shared fixtures in `tests/integration/conftest.py` separate database creation from schema setup:

1. `temporary_database_url` creates a uniquely named empty PostgreSQL database.
2. `migrated_database_engine` points the test environment at that database and runs
   `alembic upgrade head`.
3. It yields a SQLAlchemy `Engine`, which is a connection factory and pool rather than a single
   long-lived connection.
4. Test helpers insert valid prerequisite rows, then tests attempt valid or invalid writes against
   the migrated schema.
5. Fixture teardown disposes the engine before the temporary database is dropped.

Pytest injects the fixture when a test declares a parameter named `migrated_database_engine`.
Function-scoped fixtures give every test case, including each parametrized case, an isolated
database. `test_migrations.py` instead requests `temporary_database_url` directly so it can begin
empty and control its own upgrade/downgrade sequence. These tests verify migration-created
PostgreSQL schema behavior at the properties they explicitly assert; a successful Alembic command
or matching `alembic_version` alone does not prove the restored schema is correct. ORM agreement,
API behavior, and production-data import are separate test boundaries.

## API error contract

API failures use this stable envelope:

```json
{
  "error": {
    "code": "validation_failed",
    "message": "The request did not pass validation.",
    "retryable": false,
    "request_id": "00000000-0000-0000-0000-000000000000"
  }
}
```

Safe code-specific `details` may also be present. Clients branch on `code`, not `message`. Every
request receives a new UUID in `X-Request-ID`; error responses repeat it in the envelope. Validation
and unexpected-error handlers do not return rejected inputs, exception text, stack traces, SQL,
credentials, or connection details.
