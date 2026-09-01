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

## Tests and checks

```bash
uv run pytest tests/unit -q
uv run ruff check .
uv run ruff format --check .
```

Database setup, readiness verification, and production startup commands will be added only after
those paths have been implemented and verified.
