# Issue #6 - FastAPI and PostgreSQL Foundation

- Date started: 2026-08-31
- Status: Design in progress; no backend implementation or verification yet
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

This choice is a design decision until the project files exist and a clean install/build has been
verified.

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

## Application lifecycle

- Validate configuration and construct the database engine during the FastAPI lifespan startup.
- Do not require a successful database connection during startup; a temporary database outage is a
  readiness failure rather than a process-startup failure.
- Dispose the database engine during lifespan shutdown so pooled connections are closed cleanly.
- Malformed or unsafe configuration is different from dependency unavailability and must fail
  startup clearly.
- Readiness should recover automatically when PostgreSQL becomes available again.

## Planned verification

- Prove a clean `uv` dependency sync and independent API start/build path.
- Verify liveness returns `200` with PostgreSQL both available and unavailable.
- Verify readiness returns `200` with PostgreSQL available and `503` with the database stopped.
- Verify readiness does not leak internal connection details.
- Verify invalid configuration fails clearly without exposing a fake secret.
- Verify application shutdown disposes database resources.
- Record the actual frontend, API, database, and test commands only after they have run successfully.

## Next design decision

Scaffold the accepted boundary and verify the first independently runnable liveness endpoint before
adding PostgreSQL readiness behavior.
