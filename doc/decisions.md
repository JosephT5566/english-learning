# Decisions And Known Issues

Last updated: 2026-09-14

## Durable Decisions

- Use SvelteKit static adapter for deployment compatibility with static hosting and GitHub Pages.
- Keep any retained legacy Google Sheet access behind Google Apps Script instead of calling Google
  Sheets APIs directly from the browser; do not use it in normal cut-over review or management
  paths.
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
- Use keyset cursors for deck, card, and due-review collections. Bind each opaque versioned cursor
  to its endpoint, normalized filters, effective limit, and last unique sort tuple; due cursors also
  retain the first page's server `as_of` time. Reject malformed or shape-incompatible cursors rather
  than interpreting them loosely.
- Verify Google ID tokens with Google's supported Python library and one configured OAuth audience.
  Require verified email but key durable identity by Google `sub`; upsert that subject to an internal
  user and treat normalized email only as refreshable profile data.
- Require authentication for all `/v1` product operations. Authorize with resource ID plus the
  server-derived internal owner ID, mask cross-owner resources as not found, and derive create
  ownership exclusively from authenticated context.
- Use optimistic versions for deck/card edits and archive-first deletion. A stale owned edit returns
  conflict; an archive replay by the owner succeeds without another state transition.
- Treat a review submission as one owned command identified by a UUID idempotency key and canonical
  request hash. Lock all target states in sorted card-ID order, validate every item before mutation,
  calculate `srs-v1` transitions from one backend clock, and commit the batch, immutable events, and
  current states in one transaction. Replay matching content from stored events; reject conflicting
  key reuse.
- Perform the one-time Google Sheet migration from a private UTF-8 CSV snapshot through a local CLI,
  not a permanent HTTP or Google API integration. Use trimmed NFC content and case-sensitive source
  IDs, NFKC plus case-folded collection identity, canonical SHA-256 hashes, and versioned replay.
  Persist only bounded content-safe dry-run diagnostics. Start every later imported card with fresh
  backend scheduling; legacy scheduling fields are validated and explained but never authoritative.
- Treat confirmed CSV application as a distinct state transition from dry-run validation. Passing
  the exact dry-run ID is the operator approval; the importer must reproduce its complete snapshot
  and per-row hashes before writes. Allow one successful apply per owner/source namespace and one
  per dry run, map each source identity to exactly one owned card, and commit all product rows plus
  mappings in one PostgreSQL transaction. Persist post-commit reconciliation separately so a
  successful commit followed by client/report failure is recoverable through mutation-free replay.
- Cut the English review runtime directly from Google Apps Script to FastAPI/PostgreSQL with no
  fallback switch or dual writes. The browser sends its Google ID token only in the bearer header;
  FastAPI remains responsible for identity, ownership, validation, and scheduling transitions.
- Persist one exact review command and UUID idempotency key for up to 24 hours, scoped locally by
  Google subject. Retry ambiguous/authentication/retryable failures with that same pair; delete
  cross-account or malformed pending state, and refetch after any optimistic conflict.
- Roll review cutover back by redeploying the previous frontend, accepting temporary downtime and
  explicit divergence between post-cutover PostgreSQL reviews and Google Sheets. Do not attempt
  automatic reverse synchronization.
- Use one language-aware management route and component/domain boundary for English and Japanese.
  Canonicalize a missing `/decks` language to English; reject unsupported values in the browser
  without an API request. Show reading/romanization only for Japanese and pronunciation only for
  English.
- Cut management reads before management writes. Deck/card list and detail pages call only the
  authenticated FastAPI API; expose management mutation controls only after their failure,
  concurrency, and idempotency behavior is implemented and verified.
- Require a UUID idempotency key for deck/card creation and store its versioned normalized request hash on the
  created owned resource. Retain one exact account-scoped browser command for uncertain retries;
  never reuse its key with edited content.
- Preserve user input after optimistic conflicts and discard it only through an explicit latest-state
  reload. For an unclear archive response, verify `archived_at` with a read before showing success.
- Treat FastAPI OpenAPI as the compile-time frontend contract. Commit its deterministic JSON export
  and generated TypeScript, fail CI on regeneration drift, and retain handwritten runtime guards
  because network JSON remains untrusted.
- Generate common Sheet and Alert Dialog components from the shadcn-svelte registry, with Bits UI
  retained as their underlying accessibility primitive. Compose those repository-owned components
  behind task-specific Drawer and ConfirmDialog APIs, keeping product styling local while sharing
  focus trapping, keyboard dismissal, scroll locking, portals, and ARIA semantics.
- Remove `PUBLIC_APP_SCRIPT_URL` from CI and deployment rather than retaining a runtime fallback
  switch. Preserve the unused legacy wrapper and sanitized Sheet snapshot as evidence, but require
  deliberate endpoint injection for any legacy call. Fail deployment unless the FastAPI base is a
  configured HTTPS URL without credentials, a query, or a fragment.
- Package the FastAPI service as a two-stage Debian slim image with dependencies synchronized from
  `uv.lock`, a numeric non-root runtime identity, and a direct Python PID 1 entrypoint. Honor the
  platform `PORT` and bound graceful shutdown to eight seconds. Include Alembic in the image, but
  require migrations to run once as an explicit pre-deploy job instead of racing during web startup.
- Allow browser review calls only from exact configured HTTP(S) origins. Permit the review
  transport's `GET`/`POST` methods and `Authorization`, `Content-Type`, and `Idempotency-Key`
  headers; expose `X-Request-ID`, keep credentialed cookies disabled, and reject wildcard or
  implicit production origins.

## Known Follow-Up Areas

- `src/lib/utils.ts` defines `calNewEaseFactor(quality, currentEaseFactor)`, but `SwipeCards.svelte` currently calls it as `calNewEaseFactor(currentWord.easeFactor, quality)`. Verify intended parameter order before changing review scoring.
- `wordList` store is typed as `writable<WordItem[]>(undefined)`, which conflicts with strict TypeScript expectations. Consider `WordItem[] | undefined`.
- `SwipeCards.svelte` `FrontFace` type omits `tags`, but `faceFront()` returns and template reads `f.tags`. Tighten this type when touching the card UI.
- `signOut()` clears token storage but does not update the `isSignedIn` store back to false.
- `src/routes/review/+page.svelte` declares `progress` but does not render it.
- Some files have inconsistent indentation. Prefer running Prettier when editing broad areas.

## Change Log

- 2026-09-17: For Issue #27's first observability boundary, emit one bounded JSON
  completion event per routed API request using the server-generated request ID,
  matched route template, status, duration, outcome class, and stable error code.
  Disable Uvicorn access logging of raw URLs and convert unexpected endpoint
  exceptions to the existing safe error envelope inside request middleware.
  Deployed Cloud Run log parsing, platform-log privacy, alerting, and retention
  still require verification; local tests alone do not establish those claims.
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
- 2026-09-03: Added deterministic multilingual deck/card/due-review reads, query-bound keyset
  cursors, safe database failure translation, and owner/update indexes; frontend integration and
  authenticated identity remain pending.
- 2026-09-04: Replaced the temporary owner with server-verified Google identity, internal user
  mapping, authenticated owner-scoped reads, and owner-derived deck/card create, edit, and archive
  operations. Added a tested authorization matrix; review writes and frontend cutover remain pending.
- 2026-09-04: Added atomic and idempotent review submissions with deterministic pessimistic locking,
  optimistic state versions, server-derived scheduling, exact replay, conflict detection, and
  failure rollback. Frontend cutover remains pending.
- 2026-09-09: Added the one-time CSV dry-run validation boundary with owner/deck checks, deterministic
  source and content hashing, fresh-schedule diagnostics, persisted import audit records, and no
  confirmed learning-data mutations.
- 2026-09-10: Added the confirmed CSV import boundary with database-constrained source mappings,
  atomic card/tag/fresh-state creation, concurrent exact replay, safe post-commit reconciliation,
  and an operator-only local CLI. Frontend cutover remains explicitly out of scope.
- 2026-09-11: Cut the English due-review and batched review-submission frontend flow to the
  authenticated FastAPI contract with persisted exact-command retries, visible conflict recovery,
  backend-owned scheduling, and no Apps Script fallback or dual write.
- 2026-09-12: Added shared English/Japanese deck/card list and detail reads, missing-language English
  canonicalization, generated OpenAPI TypeScript with drift checks, and browser evidence that normal
  review plus management navigation makes no Apps Script request. Management writes remain pending.
- 2026-09-12: Added idempotent deck/card creation, shared create/edit/archive controls, exact pending
  command recovery, explicit stale-edit discard, archive reconciliation, and management CORS methods.
- 2026-09-12: Replaced hand-built management overlays with shadcn-svelte Sheet and Alert Dialog
  components backed by Bits UI. Task-specific Drawer and ConfirmDialog wrappers preserve the
  existing visual design while adding consistent modal focus, keyboard, portal, scroll-lock, and
  semantic behavior.
- 2026-09-12: Removed Apps Script from frontend build/deployment configuration, made the preserved
  legacy wrapper explicitly injected, and added a deployment gate for the production FastAPI base
  URL. Live production verification remains dependent on an actual deployed API and CORS origin.
- 2026-09-12: Added the provider-neutral Issue #26 API container and automated runtime smoke check.
  Provider, encrypted PostgreSQL, secret storage, and the real release pipeline remain undecided.
- 2026-09-13: Selected Cloud Run `asia-southeast1` plus Neon AWS Singapore for the first production
  deployment, with Neon as the sole writable source of truth and a USD 10 monthly ceiling. Rejected
  a runtime provider switch, dual write, and a continuous Cloud SQL replica. The web and migration
  identities receive distinct version-pinned pooled/runtime and direct/migration database secrets;
  production rejects PostgreSQL URLs without verified TLS or required TLS channel binding. Releases
  migrate once before a tagged zero-traffic candidate, require explicit smoke verification and
  promotion, and roll application traffic back only within schema compatibility. Independent GCS
  backup/restore proof remains Issue #27 scope.
- 2026-09-14: Kept production migration credentials out of GitHub while adding repeatable schema
  upgrades. A protected manual GitHub Actions workflow uses Workload Identity Federation to invoke
  the single-task Cloud Run migration job with an existing commit-tagged image, serializes runs,
  requires explicit confirmation, verifies `alembic current --check-heads`, and checks API database
  readiness through the runtime role. Direct GitHub-to-Neon access, service-account keys, data
  restore, automatic downgrade, application deployment, and traffic promotion were rejected from
  this workflow. Artifact Registry `asia-east1` is configured independently from Cloud Run
  `asia-southeast1`.
