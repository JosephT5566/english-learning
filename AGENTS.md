# Repository Instructions

## Repository context

This repository is a multilingual learning app with a SvelteKit static frontend and a Python FastAPI API under `apps/api/`. Google Identity Services provides browser sign-in; the backend verifies identity and enforces ownership. PostgreSQL is the writable source of truth for English review and shared English/Japanese deck and card management.

Google Apps Script and Google Sheets are legacy migration and rollback context. Normal review and management flows use FastAPI/PostgreSQL without an Apps Script fallback or dual writes.

Preserve the existing English review flow. English and Japanese share a language-aware domain model and backend rather than separate applications. AI-assisted authoring must create a validated, editable draft; it must not directly create a confirmed learning card.

## Context routing

Before making code changes, read the relevant repository memory:

- `doc/project-memory.md` for product intent, app flow, and current behavior.
- `doc/architecture.md` for source layout, integration boundaries, and data flow.
- `doc/development.md` for commands, environment variables, and local workflow.
- `doc/decisions.md` for durable technical decisions and known follow-up areas.

Use `doc/project-memory.md` as the current product-state index and `doc/training/project-memory.md` for the active training milestone, evidence limits, and next action. Keep detailed verification evidence in linked issue artifacts. Implementation and test results take precedence over stale documentation; distinguish repository-verified results, operator reports, and unverified claims.

For training, coaching, roadmap, or milestone work, use `.agents/skills/full-stack-training-coach/SKILL.md`. Start with `doc/training/README.md` and `doc/training/project-memory.md`; the latter identifies the active milestone, issue, and next action. Read only the relevant roadmap section or issue artifact needed for the current task. Inactive product proposals live in `doc/product/`.

Training logs are historical archives, not startup context. Do not load them by default. Search and read only the relevant log excerpt when the user asks to trace prior work, a retrospective needs the original reasoning, or current sources leave an important conflict unresolved. Do not load every training log or decision record for ordinary coding tasks.

## Working rules

- Keep changes scoped to the requested behavior or active acceptance criteria. Do not rework unrelated Svelte starter code unless it blocks the task.
- State important assumptions and preserve existing contracts unless the task explicitly changes them.
- Prefer existing project patterns: Svelte 5 runes in newer components, Svelte stores for shared review/auth state, Tailwind utility classes for styling, and `$lib` imports.
- Treat Google Identity Services and the FastAPI API as integration contracts. Update `doc/architecture.md` and `doc/decisions.md` when changing auth or API request/response contracts. Preserve legacy Apps Script and Sheet contracts when working on migration or rollback artifacts.
- Preserve static deployment compatibility. This project uses `@sveltejs/adapter-static`, `paths.base`, and `$app/paths.resolve()` for GitHub Pages-style subpaths.
- Enforce identity, ownership, validation, and state transitions on the backend. Use database constraints and explicit transactions for important invariants.
- Avoid microservices, queues, caches, vector databases, or Kubernetes without a demonstrated requirement.
- Treat generated AI content and user-provided source text as untrusted input.
- Do not commit secrets. Public SvelteKit environment variables are client-visible and must contain only values intended for the browser.
- Never store credentials, tokens, private learning data, or sensitive career notes in committed documentation.
- Do not turn planned work into resume evidence. Record only implemented and verified outcomes.
- If a task changes product behavior, append a dated note to `doc/decisions.md` or update the relevant memory file so future agents inherit the context.

## Verification

Choose checks proportional to the changed behavior. Run commands from the repository root unless noted otherwise:

| Change                                                                  | Required verification                                                                                                                                                          |
| ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Documentation only                                                      | Prettier check on changed Markdown files and `git diff --check`.                                                                                                               |
| Frontend TypeScript, Svelte components, stores, or client behavior      | `npm run check`, relevant tests through `npm run test:frontend`, and formatting/lint checks on changed files.                                                                  |
| Review/auth interactions or management/search user flows                | Relevant Playwright specs through `npm run test:browser -- tests/browser/<name>.spec.ts`, in addition to frontend checks.                                                      |
| Routes, static deployment, environment handling, or build configuration | `npm run build`; verify subpath behavior when changing routing or `BASE_PATH`.                                                                                                 |
| FastAPI request/response models                                         | `npm run api:generate`, commit the generated OpenAPI, TypeScript, and card-draft JSON Schema artifacts, then `npm run api:check` and relevant backend/frontend contract tests. |
| Backend behavior                                                        | From `apps/api/`: `uv run ruff check .`, `uv run ruff format --check .`, and relevant `uv run pytest tests/unit -q` tests.                                                     |
| Persistence, ownership, transactions, migrations, or concurrency        | From `apps/api/`: `RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest tests/integration -q` against disposable PostgreSQL; never substitute SQLite.                                |
| API image or runtime lifecycle                                          | `docker build --tag english-learning-api:verify apps/api` and `bash apps/api/scripts/verify_container.sh english-learning-api:verify`.                                         |

Run `npm run lint:changed -- <base-ref>` for changed-file formatting and ESLint checks; the local default base is `HEAD`. CI compares against the PR base or the commit before a push. Generated API artifacts are checked by `npm run api:check` instead of reformatted by Prettier. Repository-wide `npm run lint` remains a separate baseline-cleanup check with existing failures.

Use `doc/development.md` and `apps/api/README.md` for setup and command details. CI runs the full frontend and PostgreSQL-backed backend suites; targeted local tests do not replace those merge checks. Report checks actually run, failures, and any skipped checks with their reasons. An unavailable database or skipped integration suite does not establish that persistence behavior passed.

## Project conventions

- Frontend source files live under `src/`; reusable UI lives in `src/lib/components`; API wrappers live in `src/lib/api`; shared state lives in `src/lib/stores`; shared app types live in `src/lib/types.ts`. Backend application code lives in `apps/api/app/`, migrations in `apps/api/migrations/`, and tests in `apps/api/tests/`.
- Review cards are swipe/flip based. Current UX expects the user to flip a card before swiping or using yes/no action buttons.
- Review scheduling is backend-owned: keep `srs-v1` transition math and `STAGE_INTERVALS` centralized in `apps/api/app/reviews.py`. The frontend submits decisions and expected review-state versions; it does not calculate scheduling transitions. `src/lib/stores/review.ts` and the scheduling helpers in `src/lib/utils.ts` are legacy Sheet-era code.
- The app mixes English UI copy and some Chinese comments/content labels. Match nearby language when editing.
- Prefer ASCII for new docs/code unless preserving existing user-facing copy that already uses non-ASCII punctuation or Chinese text.

## Training records

After completing a material training milestone, update the training project memory and append a concise checkpoint to the current weekly log. Appending does not require reading the whole log: inspect only its tail and any directly relevant existing entry. Keep project memory bounded by summarizing completed milestones and linking to their issue artifacts instead of accumulating session history. Update the evidence ledger only when implementation and verification support the claim. Create an architecture decision record only for a consequential decision with real alternatives.
