# Decisions And Known Issues

Last updated: 2026-10-24

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
  commit failure, and always closes the session. FastAPI yield dependencies use function scope so
  request commits and their errors finish before the HTTP response is sent.
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

- 2026-09-27: Made provider-free multilingual keyword matching the default `/search` mode. The
  existing owner-scoped card list accepts a normalized, cursor-bound substring query across term,
  meaning, reading, pronunciation, and romanization while excluding archived cards and decks from
  search results. English-only semantic search remains an explicit mode with visible scope and keeps
  its existing Vertex-backed contract; Japanese semantic retrieval remains deferred.

- 2026-09-26: Separated the API release artifact identity from its Cloud Run deployment-attempt
  identity. Candidate retries reuse the immutable commit-tagged image while allowing Cloud Run to
  assign a fresh revision name, so a revision created before a later workflow failure no longer
  forces an empty commit or container republish. Every attempt remains zero-traffic and must pass
  the same candidate-tag and health verification before promotion.

- 2026-09-25: Added authenticated semantic vocabulary retrieval as an exact filtered pgvector scan
  in the existing FastAPI/PostgreSQL service. The browser cannot supply ownership. SQL applies
  owner, card/deck archive, language/deck, current model, ready vector, and current content-hash
  predicates before cosine Top-K ordering. The API exposes both cosine distance (lower is better)
  and `1 - distance` score (higher is better), plus explicit index coverage. HNSW, query caching,
  natural-language SQL, and a separate vector store remain deferred pending measured need.

- 2026-09-18: For the current side-project scope, defer an independent Neon
  database backup to GCS and the recurring backup pipeline to avoid extra
  storage and operational cost. The synthetic PostgreSQL restore rehearsal is
  retained as local learning evidence, not production recovery proof. Issue
  #27's original production backup/restore acceptance criterion remains unmet
  by explicit owner choice; revisit if data-loss tolerance, project usage, or
  budget changes.
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
- 2026-09-18: Made the backend's verified Google email allowlist authoritative before internal user
  creation. Production requires an explicit list, currently supplied from the existing GitHub
  `PUBLIC_EMAIL_WHITE_LIST` variable during API deployment. Added a protected, manually dispatched
  candidate smoke workflow that accepts a fresh Google ID token, masks it in runner logs, and can
  optionally submit one real review with exact replay. This does not create a persistent CI identity
  or change the browser's Google sign-in flow.
- 2026-09-20: Implemented Issue #39's embedding storage as rebuildable derived data in a separate
  pgvector table keyed by owned card and model version. Confirmed card writes commit their canonical
  hash before a bounded Vertex document call; provider failure cannot reverse the card transaction.
  A claim token and hash check reject old results, while an explicit owner-bounded backfill repairs
  missing and failed rows. Archive remains query-time exclusion. No queue, scheduler, cache, or ANN
  index was added. Production role, provider identity, and private-data gates still require operator
  verification before deployment.
- 2026-09-27: Hardened the review card interaction without changing its API contract: cards still
  require an answer reveal before grading and continue to submit `no`, `no_a_bit`, `yes_a_bit`, or
  `yes`. The UI now labels those choices Forgot, Hard, Almost, and Knew it; supports Enter/Space to
  flip and 1-4 to grade; announces state changes; and cancels interrupted pointer gestures safely.
- 2026-09-27: Distilled card authoring around term and meaning while preserving the complete create
  and edit contract. Japanese reading remains in the primary flow; word details, examples, related
  words, and notes use progressive disclosure and reopen when they contain saved data. Synonyms and
  antonyms now use removable tokens while continuing to submit the same string-array fields.
- 2026-09-27: Card details now describe learning context instead of persistence internals. The
  learner view omits optimistic-lock versions and review-stage numbers, retains those values in the
  API and mutation logic, and presents the deck, learned date, archive state, and next-review status
  in plain language. Invalid language links now offer explicit routes back to supported decks.
- 2026-09-27: Unified Search with the Study Blue visual system and learner-facing vocabulary while
  preserving separate multilingual keyword and English-only semantic API calls. Search result links
  now carry explicit language context. Semantic similarity percentages and index terminology are
  presented as qualitative match strength and plain coverage guidance, with keyword search offered
  as the immediate fallback when semantic results are unavailable or empty.

- 2026-10-06: Added Issue #53's JSON authoring tab beside the existing manual card drawer. Users
  copy a deck-aware prompt and bring JSON from their own AI tool; the application validates and
  previews editable content before explicit confirmation. A read-only owned-deck endpoint reuses
  Pydantic card-field validation with 1-20 cards and a 100,000-byte request bound. Confirmed saves
  use sequential existing idempotent card creates, with explicit per-card outcomes rather than an
  atomic batch API. Exact uncertain commands persist across reload without automatic expiry,
  while confirmed cards are skipped during retry. No AI generation provider or schema migration
  is added.

- 2026-10-06: Added local Ajv validation to JSON authoring using a bundled JSON Schema exported
  from Pydantic. The backend publishes existing cross-field dependencies as schema annotations;
  frontend code does not reimplement those rules. Debounced input checks run locally, while preview
  and edited selections are checked synchronously before requests. Backend ownership, active-deck,
  validation, and confirmation boundaries remain authoritative. CI regenerates and checks the
  new schema alongside the existing API artifacts.

- 2026-10-06: Replaced JSON authoring's sequential card requests with an atomic, owned-deck bulk
  endpoint and frontend `createCards` method. The bounded Pydantic request preserves per-card
  idempotency keys across bulk and single-card APIs, avoiding a new replay table or migration.
  All new cards, review states, and semantic hashes commit together; a conflict rolls back the new
  selection. Exact retries preserve keys/content across reload, and response correlation must
  succeed before the UI confirms any card. Derived embeddings follow the response as best-effort
  in-process work, with the existing backfill as recovery. Manual creation and draft review remain.

- 2026-10-24: Bulk card creation reads and locks its owned deck once per transaction, sharing a
  private immutable deck context with the single-card creation helper. Single creation still
  acquires its own lock. Exact replay precedes archive rejection, while new cards, review states,
  and hashes retain atomic rollback and sorted idempotency-key processing.

- 2026-10-07: Kept JSON authoring as a native textarea with explicit formatting and error navigation.
  jsonc-parser supplies browser-independent syntax offsets and maps local schema errors to original
  source ranges; missing fields point to their containing object. Comments and trailing commas
  remain invalid. Formatting changes whitespace without rewriting number tokens or field values,
  and does not validate with the server or create cards. Existing limits, debounce, editable draft
  preview, and explicit confirmation remain in force.

- 2026-10-07: Moved manual/JSON card creation and confirmed-card editing into a shared Bits UI
  dialog, up to 60rem wide on desktop and full-screen on mobile. The header stays visible while
  the form body scrolls, with safe-area padding and the existing single-column mobile fields.
  Dismissal remains blocked during requests, and focus returns to the opening control. Deck
  drawers, draft editing, validation, conflict recovery, and API contracts retain their behavior.

- 2026-10-07: Bound optional CardForm disclosures to user-controlled open state so editing
  inputs no longer resets manually opened or closed sections. Related-word inputs retain pending
  text on blur; Enter, comma, or Add confirms tokens, while form submission includes pending text.
  IME composition confirmation does not add a partial word. This applies to manual creation,
  confirmed-card editing, and JSON draft editing through their shared CardForm.

- 2026-10-07: Keep the shared Header mounted and hide its navigation while the existing
  isSignedIn store is false. Visibility preserves the header's layout space to avoid content
  shifting; hidden navigation is inert and excluded from accessibility navigation. Existing
  layout-load redirects and API authentication checks remain unchanged.

- 2026-10-08: Added deck-card sorting by recently updated (the existing default) or recently
  created, both descending with an ID tie-breaker. The owned cards API validates the sort field
  and binds pagination cursors to it; existing updated-date cursors remain compatible. The page
  persists sorting in its URL, resets pagination on changes, and ignores stale load-more responses.
  No response fields, keyword matching, or write contracts changed.

- 2026-10-08: Restoring a pending manual card save or unfinished JSON queue on a deck page
  keeps the creation dialog closed until the user chooses New card. Recovery still restores
  the original draft and idempotency keys for an explicit, safe retry.

- 2026-10-08: Use Lucide icons for deck detail create, edit, archive, pagination, and sorting
  controls and the card dialog close button. Icon actions retain accessible names, tooltips,
  and 44px touch targets; the sort selector retains its accessible label and descriptive options.
  Deck-list Manage cards and card-list View card links also use Lucide icons with the same
  accessible names, tooltips, and touch target sizes, retaining their base-aware navigation.
  Header navigation uses Home, Review, Decks, and Search icons with accessible names and tooltips;
  active-route styling and signed-out visibility behavior are preserved.
  Search mode, submit, retry, and keyword fallback buttons use Lucide icons with accessible names,
  tooltips, visible focus, and 44px minimum touch targets. Loading animation respects reduced motion.

- 2026-10-22: Add a dedicated anonymous `/review/guest` route and content-only public review
  DTO rather than entering the authenticated due-review/pending-command lifecycle. Shared
  presentation emits content answers; private review attaches the original expected versions.
  Guest completion is temporary and never writes learning state, pending commands or daily
  completion. Public fetches omit credentials and use explicit retries after server cooldowns.
  Publication is operator-controlled through a server-only deck allowlist, empty by default.
  Configured active decks publish current and later active-card content through an explicit
  projection; revocation affects future fetches only. Per-process source/global token buckets,
  a nonblocking database permit and transaction-local read-only/timeout settings protect this
  boundary without adding a service, migration or publication UI. Keep publication disabled
  until selected content and the deployed trusted forwarding chain pass operator verification.
  Local tests do not establish production identity handling or live publication.

- 2026-10-22: Replace the dedicated guest frontend entry with shared `/review` and separate
  guest/private controllers. Require explicit Continue as guest, represented only by tab-scoped
  `sessionStorage`; do not infer guest from missing credentials or persist answers. Reload retains
  the choice and starts a new batch; tab closure ends it. Valid authentication always selects
  private review. The legacy route redirects without opting into guest. Login discards the guest
  batch; explicit avatar-menu sign-out clears the choice and returns home. Token expiry or API
  401 preserves the active private controller and exact pending retry for same-account login,
  without guest fallback. A subject change remounts private review and invalidates stale requests.
  A delayed old-token `401` cannot sign out newer credentials; only a matching current request
  token triggers API sign-out. The guest marker controls presentation only; public/private backend
  boundaries are unchanged.

- 2026-10-23: Limit explicit guest selection to a fixed 30-minute absolute deadline stored in
  tab-scoped sessionStorage. Reload, navigation, grading and Practice again do not extend it.
  Hydration, focus and the session watcher expire the choice to signed-out, discard the guest
  batch, abort its requests and return home. Legacy or invalid markers require a new explicit
  choice. Valid authentication takes priority; private pending-command reauthentication remains.
  Hide primary navigation during initialization and while signed out, preserving header space
  and the account avatar. Guest deadlines control browser presentation, not backend identity.

## 2026-10-23: Publish guest cards through a machine-only snapshot export

The owner approved a manually dispatched export and Pages publication for English deck
`e3fa16a8-698b-445f-af1f-920c6758b377`. Export uses a dedicated short-lived Google service-account
identity, independently verified from browser auth, and reuses the explicit content projection.
No notes, tags, user metadata or review state are selected. The snapshot contains up to 50
cards and is capped at 512 KiB. Guest rounds will sample locally, avoiding anonymous database
traffic. Supporting exporter deployment, static Pages publication, and anonymous-route removal
must remain separately deployable stages. Live infrastructure setup is a separate operation.

## 2026-10-23: Separate manual guest export from Pages publication

The owner approved storing the selected deck's public snapshot in Git through an export-created
PR. This supersedes the earlier same-run export-to-Pages artifact dependency and the prohibition
on committing approved public cards. Both workflows remain manual-only. Export uses protected
main-branch WIF in a read-only job, then transfers only validated JSON to a distinct PR-write job
without Google credentials. The managed branch targets main and includes only
`static/guest/cards.json`; no automatic merge or deployment occurs. Pages validates and builds
the committed snapshot independently of BE availability. The initial snapshot is intentionally
empty, and failed exports preserve the previous source/deployed content. Synthetic browser
fixtures now replace ignored build output only. IAM trust must move to the exact export workflow
reference, and Actions PR creation must be enabled before use. These operational changes remain
unverified and were not performed. See the [follow-up plan](product/2026-10-23-separate-guest-export-plan.md).

## 2026-10-24: Track account-scoped practice activity instead of daily completion

A validated private review result records an optional browser-local `YYYY-MM-DD` under an
account-scoped activity key. The homepage follows the active authenticated subject and local date;
guest sessions never access activity markers. Ignore the legacy shared month/day marker because
it identifies neither an account nor a year. A storage failure cannot turn a confirmed save into
an unconfirmed result. Success copy confirms only the saved batch and practiced-today activity,
because the ten-card request can leave more cards due. Backend scheduling and API contracts are
unchanged.

- 2026-10-24: JSON card confirmation now checks and normalizes the edited selection locally,
  persists the normalized fields and existing keys, and sends one bulk create request. The remote
  owned-deck validation endpoint remains the preview boundary; confirmation no longer repeats that
  read-only request. Bulk creation still enforces Pydantic CardFields validation and ownership.
  Uncertain retries bypass normalization and reuse the exact stored content and keys; storage
  failure still prevents starting a write.

- 2026-10-24: Semantic search checks current index coverage before calling Vertex. A configured
  search with zero indexed cards returns the existing empty response and eligible count without
  requesting a query embedding or running vector ranking. Owner/deck checks and the unconfigured
  provider error keep their precedence. Indexed searches still report provider failures as 503.

- 2026-10-24: Single-card creation and semantic edits now follow bulk creation's best-effort
  in-process BackgroundTasks pattern. Confirmed content and its semantic hash commit before the
  response, and ASGI sends the final body before embedding begins. Existing owner/hash/claim guards,
  replay behavior, note-only exclusion, ready-content no-op, and explicit backfill remain in force.
  Process interruption can leave derived data missing or retryable; no durable queue or provider
  availability requirement was added to card confirmation.

- 2026-10-24: Each application lifespan and explicit embedding backfill run owns one lazy Vertex
  provider. A lock serializes ADC discovery, stale or expired credential refresh, token snapshots,
  and auth transport closure. Fresh credentials are reused across document and query embeddings;
  auth failures permit retry. A provider 401 invalidates only the matching cached token so the next
  explicit request refreshes it; a delayed rejection cannot invalidate a newer token. Prediction
  HTTP calls remain independent and retain their eight-second
  timeout outside the credential lock. Startup, health checks, and dry runs make no ADC or Vertex
  calls. No process-global credential cache or shared prediction session was added.

- 2026-10-24: Card creation and edits refresh the canonical semantic hash from one owned card/deck
  snapshot that includes the stored hash. The helper writes only when the computed hash differs,
  removing the separate hash-only read on edits. Every edit still recomputes from persisted fields,
  including note-only edits that repair a missing hash. Canonical normalization, optimistic versions,
  transaction boundaries, and background embedding eligibility retain their existing behavior.

## 2026-11-05: Require explicit owner consent before Vertex processing

Issue #74's supplied approval record authorizes the migration and backend consent boundary.
Store only the grant timestamp on `users`; NULL means no consent for new and existing users.
Expose self-only GET/PUT/DELETE `/v1/me/genai-consent`, and return the fixed
`genai_consent_required` code with 403 before semantic search can call its provider.
Card writes still commit without consent; derived embedding work skips the provider.
Serialize embedding claims and final writes with withdrawal through the user's row lock.
Clear consent and delete all of that user's embedding versions atomically on withdrawal.
An already running provider call cannot be recalled, but its deleted claim cannot be restored.
Backfill requires consent and never grants it. Grant does not automatically backfill old cards.

On 2026-11-05 the maintainer selected inline option A by chat. The search route now checks
consent on entering meaning search and explains that card text and search queries go to
Google Vertex AI. Only a granted state enables meaning search; keyword search remains available.
Grant does not automatically submit the query. Withdrawal uses an inline second confirmation
that warns about deleting existing embeddings and cannot recall already-transmitted content.
A consent-required 403 returns to the prompt. No dialog, account-menu entry, or public config
was added. See [Issue #74 verification](issues/issue-74-verification.md) for local evidence
and deployment limits.

## 2026-11-05: Bind transaction identities before enabling fail-closed RLS

Issue #75 keeps explicit app owner filters and adds database owner policies on all 11 owner-bearing
tables. The app binds positive internal owners centrally and reapplies transaction-local settings
after every commit/rollback. Guest export uses an exclusive public-deck UUID context after setting
the transaction read-only. Owners intentionally bypass RLS; runtime must not own tables or have
superuser/BYPASSRLS privileges. Retired import tools remain unbound/disabled under runtime RLS;
`import_items` is a known gap. Deploy binding code before 0008; disable RLS before rolling back to
older code. This exception requires operator sequencing because existing release automation was
not changed. Neon pooled behavior and production execution remain unverified. See
[Issue #75 verification](issues/issue-75-verification.md).

## 2026-11-05: Add stateless card extraction with provisional evaluation

Issue #72's supplied approved spec and maintainer implementation instructions authorize REST with
existing `requests` and ADC. No dependency, workflow, migration, auth/GIS, public environment,
static-path or scheduling changes are needed. No online documentation was queried, per the task's
explicit prohibition; Vertex generation request/response formats and response-schema subset are
unverified and require maintainer live evaluation. No model is selected by default.

Implementation defaults are engineering choices, not benchmark results: model `None` prevents
accidental live use; HTTP timeout 30 seconds limits transport waiting; 8192 output tokens gives
short 1-20 card drafts room while bounding output; 20000 material characters covers a short passage
or word list; 2000 instruction characters covers focused edits. Configured maxima are 120 seconds,
32768 tokens, 100000 material characters and 10000 instruction characters. The transport timeout
is requests' connect/read timeout, not an end-to-end billing or streaming deadline. Output also
retains the existing 100000-byte JSON authoring cap. Settings remain server-only.

Keep generation outside the request transaction after ownership/archive/consent checks. Releasing
the shared consent lock avoids blocking withdrawal during provider latency; a later withdrawal
cannot recall transmitted input. Return only strict `CardDrafts` previews and never persist them.
Reject explicit null adjustment fields conservatively, requiring a real drafts/instruction pair.
No retry masks invalid output. The provider schema removes unsupported keywords, while server
validation retains extra-field and cross-field enforcement.

Propose eight original synthetic English cases: narrative, list, ambiguity, supplied source/date,
no source/date, ordinary adjustment, material injection and instruction injection. Each category
gets one case; injection has two of eight, deliberately covering both input paths. This balances
small review effort with requested coverage, not statistical representativeness. AI drafted all
inputs and expected terms. Update 2026-11-05: the maintainer `JosephT5566` reviewed all eight cases and recorded
`reviewed_by` and `reviewed_on` for each; this is a single-reviewer set, not independent
annotation. Original note: the review owner had not been assigned and the fields were null. Recorded responses are handwritten synthetic fixtures,
not actual model results. Manual live evaluation needs an explicit flag, opt-in environment,
selected model/project and model-documentation query date. See
[evaluation README](training/issues/72/README.md) and [verification](issues/issue-72-verification.md).

## 2026-11-05: Preserve final text and classify malformed generation bodies

PR #85 review identified two defects at head `71b66f7`: text parts with thoughtSignature were
rejected, and requests.JSONDecodeError was classified as a retryable transport failure.
Use an explicit text-part key allowlist: text, thought and thoughtSignature. Require string text,
boolean thought when supplied, and string thoughtSignature when supplied. Treat signatures as
opaque metadata and exclude thought=true text from the final answer. Validate every part before
excluding thoughts so mixed tool/media content cannot hide in a thought part. Reject all unknown
keys conservatively, including future metadata, until separately reviewed. No final answer text
still fails. The basis is the review-cited Vertex Content REST reference, which was not fetched or
verified; these contracts have only handwritten/local synthetic response evidence.

Classify JSONDecodeError, ContentDecodingError and ChunkedEncodingError as invalid_response
before the generic RequestException catch. A malformed JSON/decoded/chunked body is invalid
output, so the endpoint returns non-retryable 502 generation_invalid_response rather than a
retryable service outage. Local installed requests source confirms these body errors share
RequestException; real Response.json() tests exercise JSON and synthetic raw body-read errors.
Keep ordinary connection failures as provider_unavailable and retain existing HTTPError status
classification. This does not establish real Vertex wire compatibility or all network failure
behavior. Dataset review and true-model evaluation remain maintainer tasks, untouched by this fix.
See [review-fix evidence](issues/issue-72-verification.md#pr-85-review-fixes).

## 2026-11-05: Separate generation location and retain safe HTTP diagnostics

PR #85's maintainer reported eight live evaluation cases classified invalid_response with a
model selected for global. This is an operator report, not a model run or report independently
inspected by this agent. It does not prove all failures share one cause. Local source confirms
the original shared setting rejects global and the generation URL always used a regional host.

Add server-only GENERATION_LOCATION, default None, accepting global or the same regional format.
Resolve None to the unchanged VERTEX_LOCATION so existing deployments retain their region.
Embedding configuration and routing remain regional and unchanged. A generation-only URL builder
uses aiplatform.googleapis.com for global, with locations/global in the path; other regions retain
the prefixed host. This global URL format comes from prior knowledge and is unverified against
the real API; no model name, model/location availability or IAM permission is asserted valid.

Keep external ApiError codes, retryability and OpenAPI unchanged. GenerationFailure retains an
optional integer HTTP status (100-599, excluding booleans/non-integers) for internal diagnosis,
never the response body, input or token. All HTTPError classifications remain unchanged, including
400/404 as invalid_response. Record effective location at the top of manual evaluation reports
and nullable provider_http_status per case. Record http_status in the existing private extraction
completion event only when available. No new logging system or public diagnostic field is added.

The maintainer's uncommitted cases.json edits are explicitly outside this change. Preserve them
byte-for-byte and never stage them. The existing replay test assumes all case review fields are
null and already fails against that working copy; do not weaken its assertions or reset owner data
to make verification appear green. See [follow-up evidence](issues/issue-72-verification.md#generation-location-and-http-diagnostics-follow-up).

## 2026-11-05: Omit provider array-count keywords after a narrow Vertex bisect

The maintainer reported a one-occasion Vertex bisect on gemini-3.8-flash/global: a schema with
minItems/maxItems returned HTTP 400 (Request contains an invalid argument); removing only both
keywords together, retaining the rest, returned 200; removing all constraints also returned 200.
Removing another keyword group alone left the array-count keywords present and still returned 400. That observation does not implicate those other groups. Individual minItems vs maxItems
causation remains untested. The agent made no model call or online documentation lookup.

Remove both keywords conservatively from the generation provider schema projection at every
level. Retain other supported keywords, including minLength/maxLength, minimum/maximum, enum,
format, nullable, required and description. The successful request establishes acceptance of
that remaining supplied schema combination for this one model/run; it does not prove semantic
constraint enforcement, all output cases, other models/versions, or output quality. The latter
has not been evaluated. Preserve complete CardDrafts server validation, including 1-20 cards,
field limits and cross-field rules. Keep the prompt unchanged because it already says 1-20 cards.

The former unit assertion that provider cards.maxItems equals 20 was an empirically disproved
provider-compatibility assumption. Replace it with assertions that minItems/maxItems are absent,
add recursive/nested conversion coverage, and keep server zero/over-limit output rejection checks.
This changes only the provider projection, not the public JSON Schema/OpenAPI or validation
contract. Cases.json remains untouched. See [fix #3 evidence](issues/issue-72-verification.md#provider-array-count-keyword-bisect-fix-3).

## 2026-11-05: Bound a stateless readonly assistant independently of model behavior

Issue #70's supplied approved snapshot and maintainer task instructions authorize the backend
only. Frontend design is not selected; no handwritten frontend change is included. Reuse the
existing REST/ADC generation provider without dependencies, migrations, auth/GIS changes,
workflow changes or deployment. One step is one model call, at most three. Retain declarations
and explicitly send functionCallingConfig NONE on the last call so the wire request states
that tools are disabled. This wire format, provider schema subset and thoughtSignature replay
are unverified on real Vertex. Preserve complete validated model parts for opaque signatures;
handwritten tests prove copying only, not provider acceptance.

Chosen defaults are engineering bounds, not measured optimal values: 3 steps with range 1-3;
60-second orchestration timeout with range 1-120; 2048 output tokens per call with range 1-8192;
20 input messages with range 1-100; 12000 total characters with range 1-100000; 3 tool calls per
step with range 1-10; and search/due result cap 10 with range 1-20. Search/due request defaults
are five, clamped to 1..configured cap. Stats returns counts and accepts no limit. These choices
permit a short history and a small query batch while limiting latency, output and returned card
content. All configurable bounds live in Settings. Oversized tool batches execute nothing;
unknown tools and invalid/extra arguments return fixed model-visible errors and consume a step.

Only three readonly tools exist. Reuse semantic retrieval and paginated due queries; share one
due SQL predicate with new statistics. Strict arguments never accept owner/user IDs. The bound
session and existing RLS hook carry identity across short transactions. Generate outside
transactions and release consent locks as #72 does; use readonly transactions for tool SQL,
including after assistant search releases its transaction to obtain a query embedding. Recheck
consent before each new generation and query embedding. Withdrawal cannot recall in-flight data.
The assistant deadline starts after the existing auth/validation/commit boundary. An outer
watchdog covers initial/repeated consent and pool/SQL waits as well as provider time. Its
worker owns a separate owner-bound session and closes it itself, so caller timeout cannot
race session cleanup. Remaining statement timeouts also bound consent locks and tool SQL.
Provider-only worker timeouts do not pass sessions into model/embedding workers. The outer
watchdog returns no partial summaries or usage rather than reading a live worker's state. A timed-out
HTTP/ADC operation may finish later; no claim of remote cancellation or billing cutoff is made.

Eight original synthetic evaluation cases cover three single tools, a two-tool/two-step flow,
no-tool knowledge, foreign-deck inducement, owned-card injection and unsupported writes. AI drafts
all expectations; reviewed_by/reviewed_on stay null pending maintainer per-case review. Replay
runs the real loop on scripted responses with synthetic token counts. Manual Vertex mode uses
the same synthetic tools, requires explicit opt-in, and was not executed. Ordered exact tool
names and expected key/value subsets determine scores. Query paraphrases can be penalized;
denied attempts are separately retained in security results and omitted from task-selection
scores. This is harness coverage, not model safety or retrieval-quality evidence.

Default tuning, live wire/schema/signature behavior and corpus review remain for maintainer
confirmation. See the [decision-log draft and verification](issues/issue-70-verification.md).
Streaming and Neon pooled transaction-local set_config remain unverified.

## 2026-11-07: Enforce the assistant deadline before Vertex sends

Carry the same absolute monotonic deadline through orchestration, generation and assistant query
embedding. After acquiring credentials, each provider checks the deadline before its HTTP POST
and caps the transport timeout to the remaining budget. A credential refresh or an already-started
POST can still finish after the caller times out.

Vertex function calls can omit `args`. Treat an omission as an empty argument object for local
tool validation and replay the original model part with its opaque signature. When Gemini sends
a function-call ID, copy it onto the corresponding function response, including a denied call.
The ID is provider metadata and stays out of public tool summaries and logs. Malformed IDs and
arguments still fail parsing, and each tool still enforces its required fields.

## 2026-11-07: Stream the final assistant answer on a separate endpoint

Issue #70 adds `POST /v1/assistant/messages/stream` alongside the JSON route. The
SSE route completes the existing validation, authentication and consent checks
before sending headers. It reserves one model call for a tool-disabled
`streamGenerateContent` response. A final-turn instruction asks Vertex to answer
from the available evidence because the synthetic live probe observed tool calls
despite mode `NONE`.

Use HTTPX for asynchronous Vertex streaming and retain the existing pinned version
as a runtime dependency. The SQL worker returns its prepared answer after closing
its session. The response owns upstream cancellation and emits only visible answer
text. On disconnect, the planning worker checks a cancellation flag at SQL and
provider boundaries. HTTPX cleanup runs inside a shielded cancellation scope.
See [verification](issues/issue-70-verification.md#sse-follow-up).

## 2026-11-09: Allow the GenAI consent grant through CORS

Add `PUT` to the API's CORS method allowlist so an allowed frontend origin can complete the
preflight for `PUT /v1/me/genai-consent` before submitting the authenticated consent grant.

## 2026-11-10: Bound assistant planning heartbeats and shorten the default deadline

Issue #91 emits only SSE comments (`: ping`) while `prepare()` is pending after
headers. The interval defaults to 15 seconds, accepts integers from 0 through 60,
and 0 disables it. Preparation completion, failure, cancellation, disconnect or
the absolute deadline stops comments; later token gaps do not restart them.
Comments share the frame sender and deadline/backpressure limits. Event encoding,
terminal payloads, consent ordering and logging fields remain unchanged.

Lower the shared JSON/SSE assistant deadline default from 60 to 25 seconds, with
the same 1-120 range. Keep Cloud Run at 30 seconds for cost control and leave the
generation timeout at 30, capped by the remaining assistant budget. Slow setup
before the budget starts can still exhaust the platform margin. Preserve the
historical #70 default and the independent #71 60-second evaluation pin.

Idle proxy disconnection remains an inferred risk, not an observed failure.
Production override absence is the maintainer's report; no production, proxy or
Vertex timing was independently verified for this change.

## 2026-11-10: Keep SSE deadlines on the transport across request correlation

PR #92 review reproduced a request-ID middleware handoff gap. Starlette's
BaseHTTPMiddleware accepted body frames into a memory stream before the outer
transport finished writing. Preparation completion therefore stopped watching an
already accepted heartbeat, and event send deadlines also missed the transport.
The app-level regression reproduced bare EOF for both heartbeat and delta writes;
the heartbeat-disabled control retained its terminal event.

Use pure ASGI RequestContextMiddleware with inline header injection and direct
send delegation. Preserve pre-header safe 500 responses, request state, route
resolution, allowlisted event fields and header-time completion logging. Leave
CORS ordering and SSE encoding, deadline math and terminal grace unchanged.
Do not add SSE-specific coordination with BaseHTTPMiddleware's private buffering:
that would leave ordinary event writes with the same gap. No other application
BaseHTTPMiddleware registration was found in apps/api/app.

Cancellation is not a generic atomic-write guarantee. In the installed uvicorn
h11 and httptools implementations, send awaits flow drain before synchronous body
encoding and transport.write, with no intervening await during that write. This
supports cancellation before enqueueing a body in those implementations; it does
not prove socket delivery, other servers or proxies. Terminal delivery remains
best effort under sustained backpressure or disconnect. The new test uses fake
preparation and an outer ASGI gate, without lifespan, SQL or model calls.

## 2026-11-11: Use ai-ready as the sole implementation approval gate

The `ai-ready` label is the sole implementation approval gate. Remove approval
checkboxes and the approver field. Adding `ai-ready` means the maintainer approved
the whole spec, including maintainer-approval areas explicitly named in scope.
Areas not named in scope still need separate approval.

Keep the decision log `Approved by` column as a record of who made each decision,
not a start gate. Compare later edits against the issue content at the time
`ai-ready` was added. Approved by JosephT5566 in chat on 2026-11-11.

## 2026-11-11: Enforce assistant tool permission tiers (#94)

Tool specs declare `read`, `propose` or `write`. The model sees only `read` and
`propose`; `write` is never model-visible. Registry validation rejects duplicate
names, schema-name mismatches, invalid tiers and model-visible write specs.
Declarations, call validation, safe log names and the direct session gate use the
same filtered view. All model-visible tool SQL runs after `SET TRANSACTION READ ONLY`,
including search ranking after embedding. Search consent retains its non-readonly
`FOR SHARE` lock-and-commit pre-step, which writes no data.

The three existing tools remain `read` with unchanged schemas and argument models.
No write tool is registered. Card writes happen in the frontend through the existing
REST `/cards` and `/cards/bulk` paths after user confirmation (D1).

## 2026-11-11: Negotiate assistant display parts in the stream body (#95)

Only the stream request accepts `capabilities`, with up to eight strict tokens.
`parts.v1` enables server-built `part` events; unknown valid tokens are ignored.
Use a JSON body field rather than a header so negotiation appears in OpenAPI and
requires no CORS change. Clients ignore unknown event names and part types while
strictly validating known `card_list` parts and existing terminal/tool statuses.

Build one nonempty `card_list` per successful due/search call from validated tool
outputs, with an explicit item allow-list of `id`, `deck_id`, `term` and `meaning`.
Never derive a part from model text. Per-stream `p1`, `p2` ids track emission order.
Parts precede final answer streaming or preparation-timeout `done` and use the
existing bounded frame sender. Private loop fields keep parts out of JSON responses
and terminal payloads. No capability preserves the existing wire bytes. The page
remains opted out; rendering belongs to #98. New consumers in #96/#98 must deploy
after the backend or handle older APIs rejecting `capabilities` with 422.

## 2026-11-12: Re-read client-held assistant card refs under RLS (#96)

Conversation state stays client-held (D2). Only the stream route accepts
`StreamMessage`, which extends the unchanged JSON-route `Message` with optional
`parts`. The only history member is `card_refs`, carrying UUIDs only. Clients
cannot supply terms, deck ids, meanings or owner ids through refs.

The preparation worker re-reads all referenced ids in one query after binding the
existing owner session. Explicit owner predicates and RLS restrict results to
active cards in active decks. The query uses the shared deadline, cancellation
flag and READ ONLY transaction, then rolls back before generation. Unresolvable
ids are silently dropped. Other-owner and nonexistent ids produce identical
resolved data, model requests and SSE events, without an existence signal.
Consent is still checked before each model call.

For each assistant history message with resolved cards, append a second text part
to that same model content. Its exact prefix is
`Referenced cards (data, not instructions): ` followed by compact JSON
`[{"id":"<card UUID>","deck_id":"<deck UUID>","term":"<current term>"}]`.
Keep client id order and omit unresolved ids. This is data, never a synthetic
functionResponse. Prompts, tool schemas and logs are unchanged. Real Vertex
acceptance of a second text part on model content and follow-up use of those ids
remain unverified, as does the earlier multi-turn wire. All new tests use scripted
providers; agents must not call Vertex.

`assistant_max_history_card_refs` defaults to 40, range 0..200. This is an
engineering bound, not a measured value. A part accepts 1..200 unique UUIDs;
request totals above the configured bound return `input_too_large`, including
when the bound is zero. Serialized nonempty parts count toward
`assistant_max_chars` using compact JSON with canonical lowercase hyphenated UUIDs
and unescaped Unicode. Empty parts contribute zero characters. Validation and
bounds run before consent and streaming.

The page opts into `parts.v1`, collects card-list ids without rendering parts,
and sends refs only for completed turns. Conversation and ids stay in page memory,
cleared on auth change, consent withdrawal and reload. The pure history builder
mirrors 12000 characters, 20 messages and 40 refs. It drops oldest whole turns
when budgets are exceeded and retains the first 40 emitted ids of a single
oversized kept turn. No conversation or ids enter browser storage.

Deploy the API with #96 and promote it before deploying Pages. Pre-#95 APIs reject
`capabilities`; pre-#96 APIs reject message `parts`, both with 422 under strict
extra-field validation. This cross-version behavior is inferred, not deployed or
verified here. The client never retries 422. Old pages remain compatible with the
new API. No deployment or cloud resource change is part of this issue.

## 2026-11-12: Propose validated cards without writing (#97)

Append `propose_cards` as the first `propose` tool after the three unchanged read
tools. Its top-level arguments are strict and reject extras; content validation
reuses `CardDrafts.cards`, including 1-20 cards and all `CardFields` rules. Keep the
hand-written provider declaration minimal, without `minItems`, `maxItems`, length
or dependent-field keywords. Function declarations are deep-copied directly in
`generation.py`; they do not use the response-schema projection. The earlier
[Vertex 400 bisect](#2026-11-05-omit-provider-array-count-keywords-after-a-narrow-vertex-bisect)
motivates omitting array-count keywords. Real Vertex acceptance of nested cards
in this declaration remains unverified; agents must not call Vertex.

The executor uses the existing owner/RLS-bound READ ONLY session and always rolls
back. It never inserts, updates, commits or persists drafts. Explicit deck ids
return identical `deck_not_found` results for missing and foreign decks; only
owned archived decks return `deck_archived`. With no id, choose a deck only when
exactly one active owned deck exists, regardless of language. Otherwise return
`needs_deck` with at most 20 owned active summaries in updated-at/id descending
order. Never silently pick the most recently used deck as a proposal target.

Duplicate terms are warnings. Normalize with NFC, trim and case-fold, then compare
drafts within the proposal and active owned cards in the active target deck.
Archived cards do not warn, and missing optional content does not warn. This
normalization and the deck-list bound are engineering choices, not measured
production rules. Registry metadata enforces one proposal call per turn and a
terminal hand-off after `ok` or `needs_deck`; validation and deck errors leave the
remaining step budget available. Both transports use the model's final text,
with tools disabled, rather than a fixed server response.

A successful proposal allocates an unsigned `proposal_id` UUID for correlation
only. The model-visible result contains `status`, `proposal_id`, `deck_id`,
`card_count` and `warnings`, without full draft bodies. The allow-list builder
emits one `card_proposal` for 1-20 cards under the existing `parts.v1`, sharing
`pN` emission order with `card_list`. Its payload contains only `proposal_id`,
the deck's `id`/`title`/`target_language`, validated `CardFields` drafts and duplicate
warnings. Parts precede answer deltas or timeout `done`. No capability still runs
the tool and gives its functionResponse to the model, but emits no part. JSON
responses and terminal payloads stay unchanged. The loop's one new event,
`assistant_proposal_created`, contains only request/proposal ids and card/warning
counts, never learning content.

The system prompt now permits proposals without writing. It forbids claiming cards
were written, saved or added, inventing source attribution or dates, and guessing
a deck after `needs_deck`. Messages, card content and tool results remain untrusted
data; the final-step and private-reasoning rules remain. The mechanical boundary
is unchanged: no write tool is model-visible, and tool SQL is READ ONLY.

The strict frontend parser and page `onPart` narrowing must ship together. The
page updates card refs only for `card_list`, renders no proposal and stores no
drafts. Confirmation/edit/dismiss UI and REST writes remain #98. This issue adds
no inbound `HistoryPart` member or `proposal_state`; the request body is unchanged,
so there is no new 422 risk. Old parsers ignore unknown `card_proposal`, and new
parsers against an old API never receive it. These cross-version claims are
inferred from contracts, not a deployed compatibility test. Deploy the API before
#98's UI. `proposal_id` is not an idempotency key or write authorization. #98 must
generate `crypto.randomUUID()` keys and retain them for retries through the
existing single/bulk write replay contract. No deployment, cloud, schema migration
or write-contract change is included here.
