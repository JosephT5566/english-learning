# Decisions And Known Issues

Last updated: 2026-09-03

## Durable Decisions

- Use SvelteKit static adapter for deployment compatibility with static hosting and GitHub Pages.
- Keep Google Sheet access behind a Google Apps Script endpoint instead of calling Google Sheets APIs directly from the browser.
- Use Google Identity Services ID tokens for client sign-in and authenticated sheet updates.
- Keep review state client-side during a session, then submit batched updates at the end of the review.
- Use a five-stage spaced-repetition model with stage intervals from `STAGE_INTERVALS`.
- Keep the initial Python backend as an independently runnable `uv` project under `apps/api/`.
- Load typed server configuration during FastAPI lifespan rather than at module import. Treat the
  database URL as a secret, reject disposable defaults in production, and sanitize startup errors.
- Construct SQLAlchemy's engine lazily during FastAPI lifespan without requiring PostgreSQL at
  startup, and dispose its pool during lifespan shutdown.
- Keep liveness independent of PostgreSQL. Readiness executes a fresh bounded `SELECT 1`, reports
  only `ok` or `unavailable`, and can recover without restarting the API.
- Keep the SQLAlchemy session factory application-scoped but make each unit of work own one
  short-lived session and transaction. The boundary commits only on success, rolls back on caller or
  commit failure, and always closes the session.
- Keep Alembic inside the independently runnable API package and load its database connection through
  the same validated, secret-safe settings and engine factories as the application. Start migration
  history with an empty reversible baseline before domain tables are introduced.
- Standardize API failures as `{ error: { code, message, retryable, request_id, details? } }`. Generate
  a new server request UUID for every request, make codes the client contract, and expose only
  allowlisted validation and exception information.
- Run frontend and backend checks as independent GitHub Actions jobs. Backend CI uses PostgreSQL 17
  explicitly and runs the opt-in integration suite; SQLite substitution is not permitted.
- Use generated internal `BIGINT` identities for users and generated UUIDs for client-addressable
  decks. A deck requires one owner, uses constrained standard language codes, and exposes unique
  `(id, owner_id)` for later same-owner composite foreign keys. Retained decks restrict physical
  owner deletion; user-facing deck deletion will archive instead.
- Treat every `learning_cards` row as confirmed content with required term and meaning; incomplete
  AI output will use separate future draft tables. Cards derive language through a required owned
  deck, share nullable language-specific fields, embed one optional example, and expose unique
  `(id, owner_id)` for later owned relationships.
- Model tags as reusable per-owner resources with normalized identity. Card/tag associations repeat
  owner ID and use two composite owned foreign keys; deleting a tag cascades only to association
  rows, while cards retain archive-first deletion semantics.
- Use `review_states.card_id` as the current-state primary key and a composite owned card foreign key.
  Require scheduling values without database defaults so the backend explicitly supplies its
  calculated initial state; constrain ranges and last/next ordering in PostgreSQL. Retain state by
  restricting physical card deletion.
- Store review retry identity once on an owned batch, unique per `(owner_id, idempotency_key)`, and
  retain one event per `(batch_id, card_id)`. Events repeat constrained owner IDs and complete
  before/after scheduling values for explainable history; cross-row count/state agreement and atomic
  transitions remain explicit review-service transaction rules.

## Known Follow-Up Areas

- `src/lib/utils.ts` defines `calNewEaseFactor(quality, currentEaseFactor)`, but `SwipeCards.svelte` currently calls it as `calNewEaseFactor(currentWord.easeFactor, quality)`. Verify intended parameter order before changing review scoring.
- `wordList` store is typed as `writable<WordItem[]>(undefined)`, which conflicts with strict TypeScript expectations. Consider `WordItem[] | undefined`.
- `SwipeCards.svelte` `FrontFace` type omits `tags`, but `faceFront()` returns and template reads `f.tags`. Tighten this type when touching the card UI.
- `signOut()` clears token storage but does not update the `isSignedIn` store back to false.
- `src/routes/review/+page.svelte` declares `progress` but does not render it.
- Some files have inconsistent indentation. Prefer running Prettier when editing broad areas.

## Change Log

- 2026-08-02: Created repo memory docs and root agent instructions.
- 2026-09-01: Added the initial FastAPI liveness, readiness, typed configuration, and SQLAlchemy
  engine lifecycle boundaries; the frontend remains on Google Apps Script while backend migration
  work continues.
- 2026-09-02: Added the first production domain migration for database-constrained users and owned
  multilingual learning decks; no API route or frontend flow uses it yet.
- 2026-09-03: Extended the unshipped domain migration with confirmed English/Japanese cards,
  composite deck ownership, embedded example content, and a named active-card listing index.
- 2026-09-03: Added owned reusable tags and database-enforced same-owner card/tag associations with
  duplicate prevention and association-only tag deletion cascade.
- 2026-09-03: Added one owned current review state per card with explicit required scheduling data,
  range/time checks, restricted card deletion, and the owner/due-time index.
- 2026-09-03: Added owned idempotent review batches and retained review events with composite
  ownership, complete transition checks, deletion restriction, and named history/replay indexes.
