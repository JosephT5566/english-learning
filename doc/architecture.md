# Architecture Memory

Last updated: 2026-09-01

## Stack

- SvelteKit 2 with Svelte 5.
- Vite 7.
- TypeScript with strict mode.
- Tailwind CSS v4 through `@tailwindcss/vite`.
- Static adapter (`@sveltejs/adapter-static`) configured for static hosting/GitHub Pages-style base paths.
- Google Identity Services for sign-in.
- Google Apps Script endpoint as the Google Sheet API facade.
- Independently runnable FastAPI foundation under `apps/api/`; it is not yet used by the frontend.

## Source Map

- `src/routes/+layout.svelte`: imports global CSS and wraps route content.
- `src/routes/+page.svelte`: home/sign-in/start page.
- `src/routes/review/+page.svelte`: review page; fetches sheet words and passes them to card UI.
- `src/routes/Header.svelte`: currently unused/commented in layout.
- `src/lib/auth.ts`: Google Identity Services initialization, token storage, token validation, profile lookup, sign-out.
- `src/lib/api/sheet.ts`: Apps Script API wrapper for fetching word lists and posting review updates.
- `src/lib/api/mock.ts`: local mock word data.
- `src/lib/stores/auth.ts`: sign-in store.
- `src/lib/stores/review.ts`: review word list, current index, and pending sheet update fields.
- `src/lib/types.ts`: shared app data contracts.
- `src/lib/utils.ts`: spaced-repetition intervals and ease-factor calculation.
- `src/lib/components/SwipeCards.svelte`: main review card interaction.
- `src/lib/components/AsyncButton.svelte`, `Modal.svelte`, `QuestionCard.svelte`, `QWordToMeaning.svelte`: reusable or older UI pieces.
- `src/app.css`: global CSS, Tailwind import, and base layout styling.
- `apps/api/app/main.py`: FastAPI application factory, lifespan boundary, and router composition.
- `apps/api/app/config.py`: typed, secret-safe environment configuration loaded during lifespan.
- `apps/api/app/database.py`: lazy SQLAlchemy engine construction, application-scoped session factory,
  explicit transaction ownership, readiness queries, and pool disposal.
- `apps/api/app/health.py`: database-independent liveness and database-aware readiness contracts.
- `apps/api/tests/unit/`: API configuration, lifecycle, probe, and HTTP contract tests.
- `apps/api/tests/integration/`: opt-in real PostgreSQL readiness tests.
- `compose.yaml`: verified local `postgres:17-alpine` service with persistent development volume and
  health check, run through OrbStack's Docker-compatible engine.

## Backend Foundation Flow

1. Uvicorn imports `app.main` and calls `create_app()` through its factory mode.
2. FastAPI lifespan calls `load_settings()` during startup; configuration is not read at module
   import or application construction time.
3. Invalid configuration stops startup through a sanitized `ConfigurationError` without exposing
   raw values or database credentials.
4. Valid settings construct a lazy SQLAlchemy engine without opening a connection; settings and the
   engine are stored in application state.
5. Lifespan shutdown disposes the engine pool in a `finally` block.
6. Lifespan creates one session factory from the engine. Each future unit of work will create a
   short-lived session that commits on success, rolls back on failure, and always closes.
7. `GET /health/live` remains independent of PostgreSQL connectivity.
8. `GET /health/ready` performs a fresh `SELECT 1` probe and returns a safe `503` when PostgreSQL is
   unavailable, allowing recovery without an API restart.

The frontend still uses Google Apps Script at runtime. No frontend request currently targets this
FastAPI service.

## Data Contracts

`WordItem` is the core sheet-backed model. Important fields:

- `id`: sheet row/item identifier used for updates.
- `content`: English word or phrase.
- `chineseExplain`: Chinese meaning.
- `lessonDate`: date displayed on cards.
- `type`, `tags`, `note`: card chips/labels.
- `phonics`, `engExplain`, `example`, `synonyms`, `antonyms`, `supplementary`: optional learning details.
- `reviewStage`, `easeFactor`, `intervalDays`, `lastReview`, `nextReview`: spaced-repetition fields.

Apps Script responses use:

- `{ ok: true, result: T }`
- `{ ok: false, error?: string }`

Review update payload shape is:

```ts
{
  op: 'updateRows',
  id_token: string,
  fields: Record<string, {
    reviewStage: number;
    lastReview: Date;
    nextReview: Date;
    easeFactor: number;
  }>
}
```

## Data Flow

1. `src/routes/review/+page.svelte` calls `getWordListFromSheet()`.
2. `getWordListFromSheet()` fetches `PUBLIC_APP_SCRIPT_URL?action=getList&count=10`.
3. The page shuffles the returned `WordItem[]` and stores it in `wordList`.
4. `SwipeCards.svelte` renders and manages card interactions locally.
5. Each completed card calls `setNewField()` with the updated stage/ease factor.
6. `setNewField()` calculates `lastReview`, `nextReview`, `reviewStage`, and `easeFactor` into `newFields`.
7. `Submit Results` calls `updateReviewToSheet($newFields)`.
8. `updateReviewToSheet()` validates the Google ID token and posts updates to Apps Script.

## Auth Flow

- `src/routes/+page.svelte` initializes Google Identity Services on mount if the user is not signed in.
- `initGsiOnce()` configures the client ID and whitelist from public env vars.
- On successful credential callback, `auth.ts` decodes the JWT, validates verified/whitelisted email, stores token and expiration, and sets `isSignedIn`.
- `getTokenIfValid()` rejects missing or near-expired tokens using a safety buffer and skew allowance.

## Static Hosting Notes

- `svelte.config.js` uses `adapter-static` with `fallback: '404.html'`.
- `paths.base` is empty during dev and reads `process.env.BASE_PATH` otherwise.
- Use `$app/paths.resolve()` for internal URLs.
