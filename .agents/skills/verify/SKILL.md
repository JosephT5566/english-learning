---
name: verify
description: Run and report this repository's real verification commands. Use when checking a change locally or explaining which checks apply. Commands come from package.json and .github/workflows/ci.yml only.
---

# Verify

List and run commands that exist in `package.json` or `.github/workflows/ci.yml`. Do not invent a command, a flag, or a result. `AGENTS.md` selects which of these apply. `doc/development.md` has additional local setup; this skill does not add those commands.

## How to report

For every command, record the working directory, the exact command, the exit code, and the observed output that supports the conclusion. Name skipped checks and why. A check that did not run did not pass. Put the same facts in the pull request `驗證證據` section. When a test is new, include the red-first failure from `AGENTS.md` separately from the run after the fix.

## package.json scripts

Run these from the repository root. The `scripts` field is the source.

| Script          | Command                                                                                                                                                                     |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `dev`           | `vite dev`                                                                                                                                                                  |
| `build`         | `vite build`                                                                                                                                                                |
| `preview`       | `vite preview`                                                                                                                                                              |
| `prepare`       | `svelte-kit sync \|\| echo ''`                                                                                                                                              |
| `check`         | `svelte-kit sync && svelte-check --tsconfig ./tsconfig.json`                                                                                                                |
| `check:watch`   | `svelte-kit sync && svelte-check --tsconfig ./tsconfig.json --watch`                                                                                                        |
| `api:schema`    | `uv run --project apps/api python apps/api/scripts/export_openapi.py`                                                                                                       |
| `api:generate`  | `npm run api:schema && openapi-typescript apps/api/openapi.json -o src/lib/api/generated.ts`                                                                                |
| `api:check`     | `npm run api:generate && git diff --exit-code -- apps/api/openapi.json src/lib/api/generated.ts src/lib/api/card-drafts.schema.json src/lib/api/guest-snapshot.schema.json` |
| `test:frontend` | `node --test --experimental-strip-types tests/frontend/*.test.mjs && vitest run`                                                                                            |
| `test:browser`  | `playwright test`                                                                                                                                                           |
| `format`        | `prettier --write .`                                                                                                                                                        |
| `lint`          | `prettier --check . && eslint .`                                                                                                                                            |
| `lint:changed`  | `node scripts/lint-changed.mjs`                                                                                                                                             |

`npm run lint:changed` uses `HEAD` when no base ref is passed. CI passes a base ref, below.

`dev`, `preview`, `prepare`, `check:watch`, `format`, and `lint` are package.json scripts. The CI workflow does not run them.

## CI frontend job

`.github/workflows/ci.yml` job `frontend` runs on the repository root with Node 22 and Python 3.12. Its env sets `PUBLIC_API_BASE_URL=http://127.0.0.1:8000`, `PUBLIC_GOOGLE_AUTH_CLIENT_ID=ci-google-client-id`, and `PUBLIC_EMAIL_WHITE_LIST=ci-user@example.invalid`.

1. `npm ci`
2. `npm run lint:changed -- "$LINT_BASE"` with `LINT_BASE` set to the pull request base SHA, or `github.event.before` on a push.
3. `uv sync --locked` in `apps/api`.
4. `npm run api:check`
5. `node scripts/validate-guest-snapshot.mjs static/guest/cards.json`
6. `npm run build` with `BASE_PATH` set to `/${{ github.event.repository.name }}`
7. `npm run test:frontend`
8. `npm run check`
9. `npm run test:browser`

## CI backend job

Job `backend` sets `working-directory` to `apps/api`. Env is `APP_ENV=test`, `DATABASE_URL=postgresql+psycopg://english_learning:english_learning@localhost:5432/english_learning`, and `RUN_POSTGRES_INTEGRATION_TESTS=1`. The Postgres service image is `pgvector/pgvector:0.8.6-pg17-bookworm`.

1. `uv sync --locked`
2. `uv run ruff check .`
3. `uv run ruff format --check .`
4. `uv run pytest -q`
5. `docker build --tag english-learning-api:verify .`
6. `bash scripts/verify_container.sh english-learning-api:verify`

Run those six from `apps/api`, because that is the job working directory. The shell `docker build` and `bash scripts/verify_container.sh` paths are not the repository-root forms.

## Which change runs which

Use the `AGENTS.md` verification table to choose, and only the commands listed above:

| Change                                                           | Commands from package.json or ci.yml                                                                                                                                                                                                                            |
| ---------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Documentation only                                               | `npm run lint:changed -- <base-ref>`                                                                                                                                                                                                                            |
| Frontend types, Svelte, stores, or client behavior               | `npm run check`, `npm run test:frontend`, `npm run lint:changed -- <base-ref>`                                                                                                                                                                                  |
| Review, auth, management, or search flows                        | `npm run test:browser`, plus the frontend commands above. CI runs `npm run test:browser` with no spec path. `AGENTS.md` also shows `npm run test:browser -- tests/browser/<name>.spec.ts`; that is the same script plus a path, and `ci.yml` does not pass one. |
| Routes, static build, env, or `BASE_PATH`                        | `npm run build`. CI also sets `BASE_PATH`.                                                                                                                                                                                                                      |
| FastAPI request or response models                               | `npm run api:generate`, then `npm run api:check`, plus `npm run test:frontend` and the backend job's `uv run pytest -q`                                                                                                                                         |
| Backend behavior                                                 | From `apps/api`: `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q`                                                                                                                                                                      |
| Persistence, ownership, transactions, migrations, or concurrency | The backend job, including `RUN_POSTGRES_INTEGRATION_TESTS=1` and `uv run pytest -q` against that Postgres service                                                                                                                                              |
| API image or runtime                                             | From `apps/api`: `docker build --tag english-learning-api:verify .` and `bash scripts/verify_container.sh english-learning-api:verify`                                                                                                                          |
| Committed guest snapshot                                         | `node scripts/validate-guest-snapshot.mjs static/guest/cards.json`                                                                                                                                                                                              |

`git diff --check` is required for documentation by `AGENTS.md`. It is not a `package.json` script and not a step in `ci.yml`.

`AGENTS.md` also names, from `apps/api`, `uv run pytest tests/unit -q` and `RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest tests/integration -q`. Those paths are not `package.json` scripts and are not the `ci.yml` test step. The workflow step is `uv run pytest -q` with `RUN_POSTGRES_INTEGRATION_TESTS=1`.

Targeted local commands do not replace the CI jobs. CI's backend test command is `uv run pytest -q` with `RUN_POSTGRES_INTEGRATION_TESTS=1`, not a SQLite run.
