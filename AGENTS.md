# Repository Instructions

This repo is a SvelteKit English review app. Before making code changes, read these memory files:

- `doc/project-memory.md` for product intent, app flow, and current behavior.
- `doc/architecture.md` for source layout, integration boundaries, and data flow.
- `doc/development.md` for commands, environment variables, and local workflow.
- `doc/decisions.md` for durable technical decisions and known follow-up areas.

## Working Rules

- Keep changes scoped to the requested behavior. Do not rework unrelated Svelte starter code unless it blocks the task.
- Prefer existing project patterns: Svelte 5 runes in newer components, Svelte stores for shared review/auth state, Tailwind utility classes for styling, and `$lib` imports.
- Treat Google Identity Services and the Google Apps Script API as external contracts. Update `doc/architecture.md` and `doc/decisions.md` when changing auth, request payloads, or sheet field names.
- Preserve static deployment compatibility. This project uses `@sveltejs/adapter-static`, `paths.base`, and `$app/paths.resolve()` for GitHub Pages-style subpaths.
- Use `npm run check` for type/Svelte validation after meaningful code changes. Use `npm run lint` when formatting or style-sensitive changes are involved.
- Do not commit secrets. Public SvelteKit env vars are still client-visible and must only contain values intended for the browser.
- If a task changes product behavior, append a dated note to `doc/decisions.md` or update the relevant memory file so future agents inherit the context.

## Project Conventions

- Source files live under `src/`; reusable UI lives in `src/lib/components`; API wrappers live in `src/lib/api`; shared state lives in `src/lib/stores`; shared app types live in `src/lib/types.ts`.
- Review cards are swipe/flip based. Current UX expects the user to flip a card before swiping or using yes/no action buttons.
- Review scheduling uses `reviewStage`, `easeFactor`, and `STAGE_INTERVALS`; keep related math centralized in `src/lib/utils.ts` and `src/lib/stores/review.ts`.
- The app mixes English UI copy and some Chinese comments/content labels. Match nearby language when editing.
- Prefer ASCII for new docs/code unless preserving existing user-facing copy that already uses non-ASCII punctuation or Chinese text.
