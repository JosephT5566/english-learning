# Development Memory

Last updated: 2026-10-22

## Instruction Ownership

Maintain each instruction in its owning source and link to it from task entry points:

| Concern                                                                                               | Owning source                                                                       |
| ----------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| Repository-wide product constraints, trust boundaries, task routing, and change-to-check requirements | [`AGENTS.md`](../AGENTS.md)                                                         |
| Current product behavior and recorded deployment status                                               | [`project-memory.md`](project-memory.md)                                            |
| Source layout, data flow, and integration boundaries                                                  | [`architecture.md`](architecture.md)                                                |
| Durable technical decisions and known follow-up areas                                                 | [`decisions.md`](decisions.md)                                                      |
| Setup, environment variables, command usage, and CI behavior                                          | This file; [`apps/api/README.md`](../apps/api/README.md) for API command details    |
| Training context loading, coaching modes, and task closure                                            | [`full-stack-training-coach`](../.agents/skills/full-stack-training-coach/SKILL.md) |
| Active training milestone, evidence limits, and next action                                           | [`training/project-memory.md`](training/project-memory.md)                          |
| Detailed verification evidence and historical checkpoints                                             | Linked training issue artifacts and relevant weekly-log excerpts                    |

Root instructions apply across tasks. The training skill is loaded for training, coaching,
roadmap, milestone, retrospective, or project-evidence work; ordinary coding does not require
that workflow. Keep its detailed closure procedure in the skill rather than duplicating it
in root instructions.

Add a directory-local `AGENTS.md` when a source subtree needs additional conventions. Create a
skill when a recurring task needs a reusable method and observed agent failures justify that
guidance. Do not create skills merely to categorize frontend/backend files or list commands.
Enforce mechanically checkable requirements through scripts and CI. When authoring or changing
a skill, use baseline and guided scenarios as required by `superpowers:writing-skills`.

## Commands

### Frontend

- Install dependencies: `npm install`
- Start dev server: `npm run dev`
- Build static output: `npm run build`
- Preview build: `npm run preview`
- Type/Svelte validation: `npm run check`
- Frontend contract/component tests: `npm run test:frontend`
- Critical local browser tests: `npm run test:browser`
- Export FastAPI OpenAPI, card-draft JSON Schema, and frontend TypeScript: `npm run api:generate`
- Regenerate and fail if committed API artifacts drift: `npm run api:check`
- Format all files: `npm run format`
- Lint and formatting check: `npm run lint`
- Check changed-file formatting and ESLint: `npm run lint:changed -- <base-ref>` (defaults to `HEAD`,
  includes staged/unstaged changes and untracked files).

### API

Run API commands from `apps/api/`. See [`apps/api/README.md`](../apps/api/README.md) for the
canonical verified command reference.

- Synchronize locked dependencies: `uv sync --locked`
- Start development server: `uv run uvicorn app.main:create_app --factory --reload`
- Run unit tests: `uv run pytest tests/unit -q`
- Run PostgreSQL integration tests when a local database is available:
  `RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest tests/integration -q`
- Upgrade the development database: `uv run alembic upgrade head`
- Inspect the current migration: `uv run alembic current`
- Revert the latest development migration: `uv run alembic downgrade -1`
- Lint: `uv run ruff check .`
- Check formatting: `uv run ruff format --check .`
- Inspect eligible embedding work without a provider call:
  `uv run python -m app.embedding_backfill --owner-id OWNER_ID --limit 100 --dry-run`
- After setting `VERTEX_PROJECT_ID` and (if needed) `VERTEX_LOCATION`, run one bounded owner
  page: `uv run python -m app.embedding_backfill --owner-id OWNER_ID --limit 100`.
  Pass the returned `next_cursor` to `--cursor` to continue. When it becomes null, restart
  without a cursor after retry delays; `--retry-exhausted` explicitly revisits exhausted rows.
  One invocation processes at most 500 cards or 30 minutes. Only safe outcome counts and a
  resume cursor are printed. Never run against private cards until the deployment provider
  identity and data-handling gate in Issue #38 is approved.
- Build the locked non-root API image from the repository root:
  `docker build --tag english-learning-api:local apps/api`
- Verify its user, liveness, and graceful shutdown from the repository root:
  `bash apps/api/scripts/verify_container.sh english-learning-api:local`

Start the local PostgreSQL 17 plus pgvector 0.8.6 service from the repository root with
`docker compose up -d --wait postgres`. Inspect it with `docker compose ps` and stop it with
`docker compose stop postgres`.

Migration downgrades are exercised for local development and recovery verification. A production
deployment must use a separately reviewed forward/backward-compatible rollout and rollback plan.
PostgreSQL integration tests are explicitly opt-in and never fall back to SQLite.
The API image contains Alembic, but the web process never runs migrations implicitly. Deployment
must run `alembic upgrade head` once as an explicit pre-deploy job and stop before shifting traffic
if that command fails.

## Environment Variables

The app reads these public SvelteKit env vars:

- `PUBLIC_API_BASE_URL`: FastAPI origin/base URL used by review and deck/card management. It is
  independent of the static frontend's `paths.base`; omit the trailing slash (a trailing slash is
  normalized).
- `PUBLIC_GOOGLE_AUTH_CLIENT_ID`: Google Identity Services OAuth client ID.
- `PUBLIC_EMAIL_WHITE_LIST`: comma-separated allowed Google account emails.
- The production API also receives this list as `GOOGLE_ALLOWED_EMAILS` and rejects verified Google
  accounts outside it before creating an internal user. The browser-side check is only a UX precheck.

Because these are `PUBLIC_` vars, they are bundled into browser code. Do not store secrets in them.
Copy `.env.example` to an ignored `.env` for local frontend development and replace its placeholders.

Production static builds may also need:

- `BASE_PATH`: base path for GitHub Pages-style deployments, consumed by `svelte.config.js`.

The deployment workflow rejects a missing public variable and requires `PUBLIC_API_BASE_URL` to be
an HTTPS URL without credentials, a query, or a fragment. Google Apps Script is no longer a frontend
build variable. The unused legacy wrapper remains source evidence only and requires callers to
inject an endpoint explicitly; normal runtime code does not import it.

The API accepts these server-side variables:

- `APP_ENV`: `local`, `test`, or `production`; defaults to `local`.
- `LOG_LEVEL`: supported Python log level; defaults to `INFO`.
- `DATABASE_URL`: secret SQLAlchemy URL using the `postgresql+psycopg` driver. The local default is
  disposable and rejected in production.
- `DATABASE_CONNECT_TIMEOUT_SECONDS`: integer from 1 through 10; defaults to `2`.
- `GOOGLE_OAUTH_CLIENT_ID`: server-side audience used to verify Google ID tokens. It must match the
  frontend's Google web client ID.
- `GOOGLE_ALLOWED_EMAILS`: comma-separated allowlist enforced after Google verifies the token email;
  empty is allowed locally and production requires an explicit list.
- `VERTEX_PROJECT_ID`: optional Google Cloud project ID. When absent, provider-backed embedding work
  is disabled and semantic search reports that it is not configured.
- `VERTEX_LOCATION`: Vertex AI region for embedding requests; defaults to `us-central1`.
- `CORS_ALLOWED_ORIGINS`: JSON array of exact browser origins, for example
  `["http://localhost:5173","http://127.0.0.1:5173"]`. Wildcards, paths, credentials, duplicates,
  and an empty list are rejected; production must set an explicit value.

These API values are server-side and must never use the SvelteKit `PUBLIC_` prefix. A local
`apps/api/.env` is optional and ignored by Git; `.env.example` contains only disposable defaults.

## Production Candidate Release

Issue #26 targets Cloud Run in `asia-southeast1` with Neon PostgreSQL in AWS Singapore. Use
`deploy/cloud-run/release.env.example` for nonsecret release configuration and follow
`doc/training/issues/issue-26/runbook.md` for provisioning, migration, candidate smoke checks,
promotion, and rollback. Database URLs belong only in their separate, version-pinned Secret
Manager secrets; do not add them to the release environment file.

Use `doc/training/issues/issue-26/github-gcp-neon-maintenance.zh-TW.md` when changing GitHub
Environment Variables, WIF, service accounts, IAM bindings, Secret Manager resources, or Neon
roles. It maps each identity and variable to the publish, migration, and candidate workflows.

The release script runs migrations through a single-task Cloud Run job, then creates a tagged
candidate revision with zero production traffic. The smoke script checks `/health/ready` before
promotion because Cloud Run supports startup and liveness probes but has no readiness-probe deploy
setting.

Three protected manual workflows publish the immutable commit-tagged image, migrate production, and
deploy a zero-traffic candidate. They share a concurrency group and must use the same selected ref.
They require OIDC-based Google authentication and a protected `production` GitHub environment. The
GitHub runner never receives `DATABASE_URL`; the migration job and API revision read separate direct
and pooled Neon URLs from Secret Manager through their own runtime identities.

## Validation Expectations

Use the change-to-check table in [`AGENTS.md`](../AGENTS.md#verification) for required local checks.
CI runs frontend type, contract/component, browser, and static-build checks plus Ruff,
PostgreSQL-backed backend tests, and container verification. Regenerate API artifacts with
`npm run api:generate` when models change; `npm run api:check` enforces committed contract consistency.

CI runs `npm run lint:changed` against the PR base commit or the commit before a push, with full Git
history available. The command checks current file contents, including staged, unstaged, and
untracked changes locally; deleted files are skipped. Prettier checks supported file types and
ESLint checks files covered by its configuration. Generated OpenAPI, TypeScript, and card-draft JSON
Schema artifacts retain generator formatting and are verified separately by `api:check`.

Repository-wide `npm run lint` currently fails on existing formatting drift and ESLint errors.
Clean that baseline in a separate task before making the full command a CI gate. Changed files
must pass their checks now; unrelated baseline failures do not exempt newly changed files.

## Automated Issue Verification

The `AI Agent` workflow runs on an `ai-ready` issue label or a manual issue-number dispatch. It
checks out the default branch and prepares Node 22, Python 3.12, locked npm/uv dependencies,
Chrome, and disposable PostgreSQL 17 with pgvector. Public frontend values are placeholders;
backend configuration uses test mode and local database credentials, with no production provider
configuration. Browser/system dependencies are installed before Codex removes sudo access.

Codex follows `AGENTS.md` and leaves changes for the workflow. It must not modify workflows or Git
HEAD, publish, or deploy. The workflow guards those outputs, then creates a local candidate commit
so `api:check` compares generated artifacts with the proposed version rather than the starting
commit. It refreshes locked candidate dependencies and requires changed-file lint, contract drift,
frontend types/tests/subpath build/browser flows, backend Ruff and full PostgreSQL tests, and API
container verification. The verified commit and working tree must remain unchanged before push.

Only a passing candidate is pushed and opened as a draft PR with a verification summary and run
link. Failure or cancellation is reported in the Actions summary; an empty diff creates no PR and
makes no completion claim. The job is bounded to 60 minutes, with 30 minutes for Codex itself.
The workflow does not automatically retry failed verification or declare acceptance criteria met.

Draft PRs require human acceptance review. PR workflows started by `GITHUB_TOKEN` may await a
maintainer's approval; approve those checks in GitHub before merging. See
[GitHub's workflow-triggering rules](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).
Changing the workflow requires local verification first; do not trigger an API-backed agent run
merely to validate YAML or shell syntax.

## Style Notes

- Svelte files in this repo may use Svelte 5 runes (`$state`, `$derived`, `$effect`, `$props`).
- Use existing `$lib/...` aliases.
- Tailwind utility classes are the dominant styling approach, with component-local CSS for interaction-heavy UI.
- Keep route navigation base-path aware with `$app/paths.resolve()`.
- Icons use `@iconify/svelte`.
- The codebase currently has some Chinese comments. Preserve them when they clarify existing behavior and match the nearby style for new comments.

## Known Local Setup Assumptions

- Google Identity Services must be loaded in `src/app.html` for `window.google.accounts.id` to exist.
- The legacy Sheet wrapper still documents the Apps Script `{ ok, result/error }` shape, but it has
  no ambient endpoint configuration and is not part of normal review or management navigation.
- Auth state is currently initialized from local token helpers only where components call them; verify sign-in persistence when changing auth flow.

## Guest review development and release gate

The shared entry is `/review`. Choose Continue as guest on home to set a tab-scoped guest choice;
the stored absolute deadline expires 30 minutes after selection, or when the tab session ends.
Reload starts another temporary batch without renewing the deadline. The session watcher checks
expiry on hydration, focus and its one-second interval, clears guest review and returns home.
Signed-out and initializing sessions hide primary navigation while retaining the account avatar.
Legacy `1` and malformed markers are removed without granting another guest session. Authenticated users
always use private review. `/review/guest` is a base-aware redirect, not an opt-in. Guest content
comes only from the FastAPI public read endpoint.
No frontend environment variable or URL parameter chooses a deck. Server-only
`PUBLIC_REVIEW_DECK_IDS` is a JSON UUID array and defaults to `[]`. A missing configured deck
matches nothing. Both active decks and active cards are required on every fetch. Selected deck
content becomes publicly readable, including future active-card additions and edits. Published
fields and excluded private metadata are listed in [architecture.md](architecture.md#anonymous-guest-review-boundary).

Optional API admission settings default to six requests/minute and burst two per source,
sixty/minute and burst ten globally per process, one in-flight public query and a 2000ms
transaction-local statement timeout. The bounded source map retains at most 4096 source keys
and expires idle fully refilled entries after 600 seconds. See the API README for environment
validation and startup configuration. Private endpoints and OPTIONS do not consume public
allowances. Public 429 and busy 503 responses expose integer Retry-After seconds. The guest
browser counts down, then requires manual retry; network errors also offer manual recovery.
The existing single-instance cap does not establish a global quota or hard billing limit.

Run the guest spec with `npm run test:browser -- tests/browser/guest-review-flow.spec.ts`.
The fixture build uses synthetic public Google settings, a mock API and disposable browser
storage. It never configures real published decks. For static subpath verification, run
`BASE_PATH=/guest-check npm run test:browser -- tests/browser/guest-review-flow.spec.ts`.
The guest spec derives paths from the configured base and exercises home/direct entry,
refetch/cooldown, tab lifetime, legacy redirects and protected-route redirects at that base. Private review regressions remain
`tests/browser/review-flow.spec.ts`, `review-layout.spec.ts` and `management-read-flow.spec.ts`.

Keep the allowlist empty until an operator inspects the publishable content and proves trusted
client-source handling on the actual deployed forwarding chain. A deployed disposable smoke
must show forged prefixes cannot mint limiter identities and real distinct sources are handled
as intended. Do not expand proxy trust to satisfy a local fixture. This work does not authorize
production configuration, cloud-resource changes, migrations, traffic promotion or deployment.
