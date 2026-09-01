# Development Memory

Last updated: 2026-09-01

## Commands

### Frontend

- Install dependencies: `npm install`
- Start dev server: `npm run dev`
- Build static output: `npm run build`
- Preview build: `npm run preview`
- Type/Svelte validation: `npm run check`
- Format all files: `npm run format`
- Lint and formatting check: `npm run lint`

### API

Run API commands from `apps/api/`. See [`apps/api/README.md`](../apps/api/README.md) for the
canonical verified command reference.

- Synchronize locked dependencies: `uv sync --locked`
- Start development server: `uv run uvicorn app.main:create_app --factory --reload`
- Run unit tests: `uv run pytest tests/unit -q`
- Run PostgreSQL integration tests when a local database is available:
  `RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest tests/integration -q`
- Lint: `uv run ruff check .`
- Check formatting: `uv run ruff format --check .`

Start the verified local PostgreSQL 17 service from the repository root with
`docker compose up -d --wait postgres`. Inspect it with `docker compose ps` and stop it with
`docker compose stop postgres`.

## Environment Variables

The app reads these public SvelteKit env vars:

- `PUBLIC_APP_SCRIPT_URL`: Google Apps Script endpoint used by `src/lib/api/sheet.ts`.
- `PUBLIC_GOOGLE_AUTH_CLIENT_ID`: Google Identity Services OAuth client ID.
- `PUBLIC_EMAIL_WHITE_LIST`: comma-separated allowed Google account emails.

Because these are `PUBLIC_` vars, they are bundled into browser code. Do not store secrets in them.

Production static builds may also need:

- `BASE_PATH`: base path for GitHub Pages-style deployments, consumed by `svelte.config.js`.

The API accepts these server-side variables:

- `APP_ENV`: `local`, `test`, or `production`; defaults to `local`.
- `LOG_LEVEL`: supported Python log level; defaults to `INFO`.
- `DATABASE_URL`: secret SQLAlchemy URL using the `postgresql+psycopg` driver. The local default is
  disposable and rejected in production.
- `DATABASE_CONNECT_TIMEOUT_SECONDS`: integer from 1 through 10; defaults to `2`.

These API values are server-side and must never use the SvelteKit `PUBLIC_` prefix. A local
`apps/api/.env` is optional and ignored by Git; `.env.example` contains only disposable defaults.

## Validation Expectations

Run `npm run check` after changing TypeScript, Svelte components, stores, or API contracts. Run `npm run build` when changing routing, static deployment configuration, environment behavior, or imports that may differ between dev and production.

## Style Notes

- Svelte files in this repo may use Svelte 5 runes (`$state`, `$derived`, `$effect`, `$props`).
- Use existing `$lib/...` aliases.
- Tailwind utility classes are the dominant styling approach, with component-local CSS for interaction-heavy UI.
- Keep route navigation base-path aware with `$app/paths.resolve()`.
- Icons use `@iconify/svelte`.
- The codebase currently has some Chinese comments. Preserve them when they clarify existing behavior and match the nearby style for new comments.

## Known Local Setup Assumptions

- Google Identity Services must be loaded in `src/app.html` for `window.google.accounts.id` to exist.
- Sheet fetch/update paths depend on the Apps Script endpoint being available and returning the expected `{ ok, result/error }` shape.
- Auth state is currently initialized from local token helpers only where components call them; verify sign-in persistence when changing auth flow.
