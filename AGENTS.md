# Repository Instructions

## Repository context

This repository is currently a SvelteKit English review app backed by Google Identity Services, Google Apps Script, and Google Sheets. It is evolving into a multilingual full-stack product with a Python FastAPI API and PostgreSQL.

Preserve the existing English review flow during migration. English and Japanese should share a language-aware domain model and backend rather than becoming separate applications. AI-assisted authoring must create a validated, editable draft; it must not directly create a confirmed learning card.

## Context routing

Before making code changes, read the relevant repository memory:

- `doc/project-memory.md` for product intent, app flow, and current behavior.
- `doc/architecture.md` for source layout, integration boundaries, and data flow.
- `doc/development.md` for commands, environment variables, and local workflow.
- `doc/decisions.md` for durable technical decisions and known follow-up areas.

For training, coaching, roadmap, or milestone work, use `.agents/skills/full-stack-training-coach/SKILL.md` and read `doc/training/README.md`. The current training state lives in `doc/training/project-memory.md`; inactive product proposals live in `doc/product/`.

Do not load every training log or decision record for ordinary coding tasks.

## Working rules

- Keep changes scoped to the requested behavior or active acceptance criteria. Do not rework unrelated Svelte starter code unless it blocks the task.
- State important assumptions and preserve existing contracts unless the task explicitly changes them.
- Prefer existing project patterns: Svelte 5 runes in newer components, Svelte stores for shared review/auth state, Tailwind utility classes for styling, and `$lib` imports.
- Treat Google Identity Services and the Google Apps Script API as external contracts. Update `doc/architecture.md` and `doc/decisions.md` when changing auth, request payloads, or sheet field names.
- Preserve static deployment compatibility. This project uses `@sveltejs/adapter-static`, `paths.base`, and `$app/paths.resolve()` for GitHub Pages-style subpaths.
- Enforce identity, ownership, validation, and state transitions on the backend. Use database constraints and explicit transactions for important invariants.
- Avoid microservices, queues, caches, vector databases, or Kubernetes without a demonstrated requirement.
- Treat generated AI content and user-provided source text as untrusted input.
- Do not commit secrets. Public SvelteKit environment variables are client-visible and must contain only values intended for the browser.
- Never store credentials, tokens, private learning data, or sensitive career notes in committed documentation.
- Do not turn planned work into resume evidence. Record only implemented and verified outcomes.
- If a task changes product behavior, append a dated note to `doc/decisions.md` or update the relevant memory file so future agents inherit the context.

## Verification

For the current frontend, use checks proportional to the change:

- `npm run check`
- `npm run lint`
- `npm run build`

When the backend is added, follow its checked-in project configuration and documented commands. Prefer PostgreSQL integration tests for persistence, authorization, transaction, migration, and concurrency behavior.

## Project conventions

- Source files live under `src/`; reusable UI lives in `src/lib/components`; API wrappers live in `src/lib/api`; shared state lives in `src/lib/stores`; shared app types live in `src/lib/types.ts`.
- Review cards are swipe/flip based. Current UX expects the user to flip a card before swiping or using yes/no action buttons.
- Review scheduling uses `reviewStage`, `easeFactor`, and `STAGE_INTERVALS`; keep related math centralized in `src/lib/utils.ts` and `src/lib/stores/review.ts`.
- The app mixes English UI copy and some Chinese comments/content labels. Match nearby language when editing.
- Prefer ASCII for new docs/code unless preserving existing user-facing copy that already uses non-ASCII punctuation or Chinese text.

## Training records

After completing a material training milestone, update the training project memory and current weekly log. Update the evidence ledger only when implementation and verification support the claim. Create an architecture decision record only for a consequential decision with real alternatives.
