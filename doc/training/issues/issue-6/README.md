# Issue #6 - FastAPI and PostgreSQL Foundation

- Date started: 2026-08-31
- Status: Implementation and final verification complete locally
- Outcome: Establish a minimal, reproducible Python API connected to local PostgreSQL

## Scope boundary

This ticket adds the independently runnable API boundary under `apps/api/`, local PostgreSQL through
Docker Compose, typed configuration, graceful lifecycle behavior, and liveness/readiness endpoints.
Domain tables, authentication, learning-card APIs, review APIs, and production deployment remain out
of scope.

## Dependency and packaging decision

Use `uv` for Python dependency management, virtual environments, locking, and project commands.

- `apps/api/pyproject.toml` is the independently buildable Python package boundary.
- Commit `uv.lock` so contributors and CI resolve the same dependency versions.
- Keep runtime and development dependency groups separate.
- Document API commands with `uv sync` and `uv run ...`; frontend commands remain npm-based.
- Target Python 3.12 or newer, consistent with the training plan.

The project files and locked Python environment have now been created and verified locally.

### API command reference

The verified setup, development-server, liveness, test, and Ruff commands live in the
[`apps/api/README.md`](../../../../apps/api/README.md). This issue note keeps design rationale and
verification history rather than duplicating the daily command reference.

## Dependency set

Initial runtime dependencies:

- `fastapi` for the HTTP application and routing.
- `pydantic` for response models, constraints, and secret-safe values used directly by the API.
- `pydantic-settings` for typed environment configuration.
- `sqlalchemy` for the database engine, connection lifecycle, and readiness query.
- `psycopg[binary]` for the Psycopg 3 PostgreSQL driver without a separate local `libpq`
  installation requirement.
- `uvicorn[standard]` for serving the ASGI application and local reload support.

Initial development dependencies:

- `pytest` for automated tests.
- `httpx` for FastAPI `TestClient` support.
- `ruff` for Python linting and formatting.

Use the standardized `dependency-groups.dev` table managed by `uv add --dev` for development-only
dependencies. Declare direct dependencies for packages the application imports rather than relying
on their incidental installation as transitive dependencies.

Use synchronous SQLAlchemy for this milestone. Synchronous FastAPI route functions can perform the
readiness query without blocking the application's event loop, and the simpler lifecycle and test
model is sufficient for the current requirements. Async database sessions can be reconsidered only
if later requirements or measurements justify their additional complexity.

Do not add Alembic, async test plugins, coverage tooling, Testcontainers, authentication libraries,
or AI libraries in this ticket. They are either outside scope or lack a demonstrated requirement.

## Source and test layout

Use this minimal boundary:

```text
english-learning/
├── apps/
│   └── api/
│       ├── app/
│       │   ├── __init__.py
│       │   ├── main.py
│       │   ├── config.py
│       │   ├── database.py
│       │   └── health.py
│       ├── tests/
│       │   ├── unit/
│       │   │   ├── test_config.py
│       │   │   └── test_health.py
│       │   └── integration/
│       │       └── test_health_ready.py
│       ├── .env.example
│       ├── .python-version
│       ├── pyproject.toml
│       ├── README.md
│       └── uv.lock
├── compose.yaml
└── ...
```

Responsibilities:

- `main.py` owns the application factory, FastAPI lifespan, and router registration.
- `config.py` owns the typed settings model and secret-safe configuration failure boundary.
- `database.py` owns SQLAlchemy engine construction, the `SELECT 1` readiness probe, and engine
  disposal.
- `health.py` owns the liveness/readiness routes and their response models.
- Unit tests cover configuration and health behavior with controlled database substitutes.
- The integration test exercises readiness against actual PostgreSQL.
- `apps/api/README.md` documents API-specific commands; `doc/development.md` documents the combined
  frontend, API, and database workflow.
- Root `compose.yaml` owns shared local PostgreSQL infrastructure rather than placing it inside the
  Python package.

Use a `create_app()` application factory and the Uvicorn target `app.main:create_app --factory`.
Avoid constructing settings or database resources as an import side effect. This keeps startup,
lifespan, and failure behavior controllable in tests.

Do not add empty future-facing `models/`, `schemas/`, `services/`, `auth/`, or `migrations/`
directories. Add those boundaries only when an implemented feature requires them.

Extend the root `.gitignore` for Python-generated state: `.venv`, `__pycache__/`, `*.py[cod]`,
`.pytest_cache/`, and `.ruff_cache/`.

## Configuration contract

Use `pydantic-settings` for typed environment configuration. Initial settings are:

| Environment variable | Type/constraint | Safe local default | Purpose |
| --- | --- | --- | --- |
| `APP_ENV` | `local`, `test`, or `production` | `local` | Select environment-specific safeguards. |
| `LOG_LEVEL` | Supported log level | `INFO` | Set application log verbosity. |
| `DATABASE_URL` | Secret database connection string | `postgresql+psycopg://english_learning:english_learning@localhost:5432/english_learning` | Connect the API to local PostgreSQL. |
| `DATABASE_CONNECT_TIMEOUT_SECONDS` | Positive, bounded number | `2` | Bound readiness connection attempts. |

Configuration rules:

- The committed local database username and password are disposable development values, not
  production credentials.
- Production must explicitly override `DATABASE_URL`; starting production with the local default is
  a configuration error.
- A local `.env` file is optional and ignored by Git. A committed `.env.example` may contain only
  documented non-secret local values.
- Treat `DATABASE_URL` as a secret value in application representations.
- Never log the complete settings object or raw database URL.
- Invalid configuration fails startup with the setting name and a safe explanation, but without the
  supplied value, credentials, or a connection string.
- An automated test must use a recognizable fake password and prove that configuration failure
  output does not expose it.

### Configuration implementation and verification - 2026-09-01

- `app/config.py` defines frozen typed settings for the environment, log level, secret database URL,
  and a database connection timeout bounded from 1 through 10 seconds.
- Database URLs are parsed without connecting and must select the `postgresql+psycopg` driver.
- `load_settings()` translates Pydantic validation failures into `ConfigurationError` messages that
  contain safe environment-variable names but omit rejected input and exception chaining.
- Production rejects the disposable local database URL even though it remains a convenient default
  for local and test environments.
- FastAPI lifespan loads settings into `app.state.settings`. Importing the module and calling
  `create_app()` do not read configuration or create resources.
- `.env.example` documents only disposable local values. A real `.env` remains optional and ignored
  by Git.
- `uv run pytest tests/unit -q`: eleven tests passed, with the previously recorded upstream
  `TestClient`/`httpx` warning.
- `uv run ruff check .`: passed after replacing one nested test context manager with Ruff's preferred
  combined form.
- `uv run ruff format --check .`: passed after formatting `test_config.py`; seven files were already
  formatted on the final run.
- Updated the lifespan annotation from the broader `AsyncIterator[None]` to
  `AsyncGenerator[None, None]` after the editor reported the former annotation as deprecated for an
  `@asynccontextmanager` function that yields.
- Normal Uvicorn lifespan startup and shutdown succeeded, and liveness still returned `200` with
  exactly `{ "status": "ok" }`.
- Deliberately invalid production startup exited with code 3, named only `DATABASE_URL`, and did not
  expose the recognizable fake password or connection URL.

## Health endpoint contract

### `GET /health/live`

Liveness reports only whether the API process can handle requests. It does not query PostgreSQL.

```json
{
  "status": "ok"
}
```

The healthy response is `200 OK`, including while PostgreSQL is temporarily unavailable.

### `GET /health/ready`

Readiness executes a lightweight `SELECT 1` against PostgreSQL with a short bounded connection
timeout.

When PostgreSQL is available, return `200 OK`:

```json
{
  "status": "ready",
  "checks": {
    "database": "ok"
  }
}
```

When PostgreSQL is unavailable, return `503 Service Unavailable`:

```json
{
  "status": "not_ready",
  "checks": {
    "database": "unavailable"
  }
}
```

The response must not include exception text, SQL, hostnames, ports, database names, connection
URLs, or credentials. Diagnostic details may be written to server logs only after secret-safe
sanitization.

### Readiness implementation and verification - 2026-09-01

- Root `compose.yaml` defines a `postgres:17-alpine` service with disposable local credentials, a
  named data volume, published port 5432, and a `pg_isready` health check.
- `check_database_readiness()` opens a bounded SQLAlchemy connection, executes `SELECT 1`, closes the
  connection through its context manager, and maps `SQLAlchemyError` to `False` without exposing the
  exception.
- `GET /health/ready` returns only the accepted `200`/`503` response models. It performs a fresh probe
  for every request so availability can recover without restarting the API.
- Unit tests cover successful probes, failures, exact safe response envelopes, and recovery. The
  fast suite passed with nineteen tests and the existing upstream warning.
- The opt-in integration suite passed twice: available PostgreSQL returned `200`, and a real Psycopg
  attempt to an unavailable port returned the safe `503` response. These two tests ran against a
  temporary container created from an existing local `postgres:12` image.
- A process-level stop/restart exercise on one Uvicorn process produced readiness
  `200 -> 503 -> 200`; liveness remained `200` during the outage. The temporary container was then
  stopped and removed without a volume.
- `docker compose config` validated the selected Compose definition. Docker Desktop initially was
  not running; after launch, its Docker 20.10.8 and Compose v2.0.0-rc.1 stack did not complete the
  `postgres:17-alpine` registry pull. Initial available-database verification therefore used the
  temporary PostgreSQL 12 fixture described above.
- After switching the active Docker context to OrbStack, `docker compose up -d --wait postgres`
  pulled `postgres:17-alpine`, created the named volume, and reported the service healthy. The two
  integration tests passed against this exact service.
- The stop/restart exercise was repeated against the Compose PostgreSQL 17 service. On one API
  process, readiness again transitioned `200 -> 503 -> 200` while liveness remained `200`.

## First implementation slice - liveness

Implement liveness as the first independently runnable vertical slice before configuration,
PostgreSQL, or readiness behavior.

### File responsibilities

- `app/health.py` owns an `APIRouter` under `/health`, the explicit liveness response model, and the
  synchronous `GET /live` route.
- The response model constrains `status` to the literal value `ok` so the public contract is visible
  in both validation and generated API documentation.
- `app/main.py` owns `create_app()`, constructs the `FastAPI` application, and registers the health
  router.
- Do not create a module-level application instance; local startup uses
  `app.main:create_app --factory`.
- `tests/unit/test_health.py` constructs the application through `create_app()` and exercises the
  endpoint through FastAPI's `TestClient` rather than calling the route function directly.

The initial tree is intentionally smaller than the final Issue #6 layout:

```text
apps/api/
├── app/
│   ├── __init__.py
│   ├── health.py
│   └── main.py
└── tests/
    └── unit/
        └── test_health.py
```

Do not add configuration, database lifecycle, Compose, readiness, authentication, domain modules,
or premature test fixtures in this slice. Liveness must not import or query database code; a
temporary PostgreSQL outage must not turn into a process restart signal.

### Acceptance criteria

1. `uv run uvicorn app.main:create_app --factory --reload` starts the API from `apps/api/`.
2. `GET /health/live` returns `200 OK` with exactly `{ "status": "ok" }`.
3. The HTTP-level unit test verifies both the status code and exact JSON response.
4. `uv run pytest tests/unit` passes.
5. `uv run ruff check .` and `uv run ruff format --check .` pass.

### Verification results - 2026-08-31

- `uv run pytest tests/unit -q`: passed, one test.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed, four files already formatted.
- `uv run uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000`: application startup
  and graceful shutdown succeeded.
- A real `GET http://127.0.0.1:8000/health/live` request returned `200` with exactly
  `{ "status": "ok" }`.
- The first pytest run failed during collection because the console entry point did not include the
  API project root on Python's import path. Adding `pythonpath = ["."]` under
  `[tool.pytest.ini_options]` made test discovery explicit and corrected the failure.
- Pytest emitted one upstream deprecation warning from FastAPI's current `TestClient` compatibility
  layer about `httpx`. It does not fail this slice, but dependency compatibility should be revisited
  when versions are next updated.

## Application lifecycle

- Validate configuration and construct the database engine during the FastAPI lifespan startup.
- Do not require a successful database connection during startup; a temporary database outage is a
  readiness failure rather than a process-startup failure.
- Dispose the database engine during lifespan shutdown so pooled connections are closed cleanly.
- Malformed or unsafe configuration is different from dependency unavailability and must fail
  startup clearly.
- Readiness should recover automatically when PostgreSQL becomes available again.

### Database engine lifecycle implementation and verification - 2026-09-01

- `app/database.py` owns SQLAlchemy engine construction and disposal.
- Engine construction unwraps the secret URL only at the SQLAlchemy boundary, applies the configured
  Psycopg `connect_timeout`, and enables `pool_pre_ping` for later stale-connection detection.
- Creating the engine remains lazy and does not open a PostgreSQL connection.
- FastAPI lifespan stores the engine in `app.state.database_engine` and disposes it in a `finally`
  block during shutdown.
- Controlled unit substitutes verified engine options, disposal, startup ordering, state ownership,
  and shutdown ordering without contacting PostgreSQL.
- `uv run pytest tests/unit -q`: fourteen tests passed, with the existing upstream
  `TestClient`/`httpx` warning.
- `uv run ruff check .` and `uv run ruff format --check .`: passed; nine files were formatted.
- A direct port check confirmed `127.0.0.1:5432` refused connections. Uvicorn still completed
  startup, `GET /health/live` returned `200` with exactly `{ "status": "ok" }`, and shutdown
  completed cleanly.

## Planned verification

- Prove a clean `uv` dependency sync and independent API start/build path.
- Verify liveness returns `200` with PostgreSQL both available and unavailable.
- Verify readiness returns `200` with PostgreSQL available and `503` with the database stopped.
- Verify readiness does not leak internal connection details.
- Verify invalid configuration fails clearly without exposing a fake secret.
- Verify application shutdown disposes database resources.
- Record the actual frontend, API, database, and test commands only after they have run successfully.

## Final verification - 2026-09-01

- `docker compose ps`: the OrbStack-hosted `postgres:17-alpine` service reported healthy.
- `RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest -q`: all 21 unit and integration tests passed with
  one recorded upstream `TestClient` compatibility warning.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed; ten files were already formatted.
- Python application modules, classes, and functions now include conventional docstrings describing
  their contracts and lifecycle responsibilities.

## Next completion step

Commit the verified readiness/Compose slice and prepare Issue #6 for formal GitHub verification.
PostgreSQL 17 is currently running through OrbStack for local development.
