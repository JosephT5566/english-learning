# Architecture Memory

Last updated: 2026-09-03

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
- `apps/api/app/errors.py`: stable safe API error models and application/framework exception handlers.
- `apps/api/app/request_context.py`: per-request UUID generation for response headers, error
  correlation, and future structured logs.
- `apps/api/app/health.py`: database-independent liveness and database-aware readiness contracts.
- `apps/api/migrations/`: Alembic environment and reversible migration history; the empty baseline
  is followed by the first production domain revision for users, decks, confirmed cards, tags, and
  current review state.
- `apps/api/tests/unit/`: API configuration, lifecycle, probe, and HTTP contract tests.
- `apps/api/tests/integration/`: opt-in real PostgreSQL readiness, migration lifecycle, transaction,
  and domain-constraint tests.
- `compose.yaml`: verified local `postgres:17-alpine` service with persistent development volume and
  health check, run through OrbStack's Docker-compatible engine.
- `.github/workflows/ci.yml`: independent frontend and PostgreSQL-backed backend verification jobs.

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
9. Alembic loads the same validated settings and engine options as the API. Migration commands own
   and dispose their engine, while each revision runs in Alembic's transaction boundary.
10. HTTP middleware assigns a new request UUID. Expected, validation, framework, and unexpected
    failures return one stable envelope and never serialize internal exception details.

The frontend still uses Google Apps Script at runtime. No frontend request currently targets this
FastAPI service.

## Initial Domain Schema

- `users` uses an internal generated `BIGINT` identity. Google subject is the unique external
  identity; normalized email is required but is not an ownership key.
- `learning_decks` uses a generated UUID, requires an owner, and supports target languages `en` and
  `ja` with explanation languages `en`, `ja`, and `zh-TW`.
- Unique `(learning_decks.id, owner_id)` is available for later composite owned foreign keys. A
  user with retained decks cannot be physically deleted.
- Deck creation replay fields are paired and unique per owner when present. Deck title, version,
  timestamp ordering, and archive ordering are database constrained.
- `(owner_id, target_language, archived_at)` supports the named owner/language filtering pattern.
- `learning_cards` uses generated UUIDs and a composite `(deck_id, owner_id)` foreign key, so a
  separately valid deck and owner cannot be combined across ownership boundaries.
- Every card is confirmed content with required nonblank term and meaning. Optional reading,
  pronunciation, romanization, definition, notes, related-word arrays, and one embedded example use
  the same table for English and Japanese.
- Unique `(learning_cards.id, owner_id)` supports later owned tag and review relationships. Physical
  deck deletion is restricted while a card exists; user-facing deletion will archive cards/decks.
- The partial `(deck_id, created_at DESC, id DESC)` active-card index matches the defined stable
  deck-list ordering. Its shape is tested; query-plan effectiveness remains unmeasured.
- `tags` uses normalized per-owner identity through unique `(owner_id, normalized_name)` and exposes
  unique `(id, owner_id)` for owned associations.
- `learning_card_tags` uses `(card_id, tag_id)` as its primary key and validates the repeated owner
  through composite foreign keys to both parent rows. Tag deletion cascades only to associations;
  physical card deletion is restricted while an association remains.
- `(tag_id, card_id)` supports filtering cards by tag because the association primary key begins
  with `card_id`. Its definition is tested; query-plan effectiveness remains unmeasured.
- `review_states` uses `card_id` as its primary key, directly enforcing at most one current row per
  card. Its composite `(card_id, owner_id)` foreign key rejects cross-owner state.
- Review scheduling fields are required without database defaults, so the future backend must write
  the initial stage, ease, interval, next-review time, and version explicitly. Checks enforce stage
  1-5, ease 1.30-2.50, nonnegative intervals, positive versions, and next review not before a present
  last review.
- `(owner_id, next_review_at, card_id)` supports stable owner-scoped due retrieval. Its definition is
  tested; archived-card/deck joins and query-plan effectiveness remain future work.
- The migration is persistence-only. No API route reads or writes these tables yet.

## API Error Contract

Failures use `{ "error": { "code", "message", "retryable", "request_id", "details"? } }`.
Machine-readable `code` values are the client contract; messages are human-readable fallbacks.
`request_id` also appears in `X-Request-ID`. Validation details contain only safe field paths,
field-level codes, and fallback messages. The readiness endpoint retains its purpose-specific health
contract rather than masquerading dependency unavailability as an application exception.

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
