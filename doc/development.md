# Development Memory

Last updated: 2026-08-02

## Commands

- Install dependencies: `npm install`
- Start dev server: `npm run dev`
- Build static output: `npm run build`
- Preview build: `npm run preview`
- Type/Svelte validation: `npm run check`
- Format all files: `npm run format`
- Lint and formatting check: `npm run lint`

## Environment Variables

The app reads these public SvelteKit env vars:

- `PUBLIC_APP_SCRIPT_URL`: Google Apps Script endpoint used by `src/lib/api/sheet.ts`.
- `PUBLIC_GOOGLE_AUTH_CLIENT_ID`: Google Identity Services OAuth client ID.
- `PUBLIC_EMAIL_WHITE_LIST`: comma-separated allowed Google account emails.

Because these are `PUBLIC_` vars, they are bundled into browser code. Do not store secrets in them.

Production static builds may also need:

- `BASE_PATH`: base path for GitHub Pages-style deployments, consumed by `svelte.config.js`.

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
