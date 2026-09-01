# Decisions And Known Issues

Last updated: 2026-09-01

## Durable Decisions

- Use SvelteKit static adapter for deployment compatibility with static hosting and GitHub Pages.
- Keep Google Sheet access behind a Google Apps Script endpoint instead of calling Google Sheets APIs directly from the browser.
- Use Google Identity Services ID tokens for client sign-in and authenticated sheet updates.
- Keep review state client-side during a session, then submit batched updates at the end of the review.
- Use a five-stage spaced-repetition model with stage intervals from `STAGE_INTERVALS`.
- Keep the initial Python backend as an independently runnable `uv` project under `apps/api/`.
- Load typed server configuration during FastAPI lifespan rather than at module import. Treat the
  database URL as a secret, reject disposable defaults in production, and sanitize startup errors.

## Known Follow-Up Areas

- `src/lib/utils.ts` defines `calNewEaseFactor(quality, currentEaseFactor)`, but `SwipeCards.svelte` currently calls it as `calNewEaseFactor(currentWord.easeFactor, quality)`. Verify intended parameter order before changing review scoring.
- `wordList` store is typed as `writable<WordItem[]>(undefined)`, which conflicts with strict TypeScript expectations. Consider `WordItem[] | undefined`.
- `SwipeCards.svelte` `FrontFace` type omits `tags`, but `faceFront()` returns and template reads `f.tags`. Tighten this type when touching the card UI.
- `signOut()` clears token storage but does not update the `isSignedIn` store back to false.
- `src/routes/review/+page.svelte` declares `progress` but does not render it.
- Some files have inconsistent indentation. Prefer running Prettier when editing broad areas.

## Change Log

- 2026-08-02: Created repo memory docs and root agent instructions.
- 2026-09-01: Added the initial FastAPI liveness and typed configuration boundaries; the frontend
  remains on Google Apps Script while backend migration work continues.
