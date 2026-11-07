# Architecture Memory

Last updated: 2026-11-04

## Stack

- SvelteKit 2 with Svelte 5.
- Vite 7.
- TypeScript with strict mode.
- Tailwind CSS v4 through `@tailwindcss/vite`.
- Static adapter (`@sveltejs/adapter-static`) configured for static hosting/GitHub Pages-style base paths.
- Google Identity Services for sign-in.
- Legacy Google Apps Script/Sheet modules remain in the repository for rollback evidence, but normal
  review and deck/card management reads no longer import or call them.
- Independently runnable FastAPI/PostgreSQL API under `apps/api/`; review plus English/Japanese
  management reads and writes now use it exclusively.

## Source Map

- `src/routes/+layout.svelte`: imports global CSS and wraps route content.
- `src/routes/+page.svelte`: home/sign-in/start page.
- `src/routes/review/+page.svelte`: guest/private session controller; `OwnedReview.svelte` fetches due cards from FastAPI and passes them to
  the existing card UI.
- `src/routes/decks/+page.svelte`: shared language-aware deck list with active/archive filtering.
- `src/routes/decks/[deckId]/+page.svelte`: owned deck detail and card list.
- `src/routes/cards/[cardId]/+page.svelte`: owned card detail with language-relevant fields.
- `src/routes/search/+page.svelte`: authenticated multilingual keyword search plus an explicit
  English-only semantic mode with coverage and retry states; card navigation remains base-path aware.
- `src/routes/Header.svelte`: base-path-aware primary navigation used by the shared layout.
- `src/lib/auth.ts`: Google Identity Services initialization, token storage, token validation, profile lookup, sign-out.
- `src/lib/api/client.ts`: authenticated FastAPI transport, bearer-header handling, response
  validation, and typed errors.
- `src/lib/api/generated.ts`: checked-in TypeScript generated from FastAPI's checked-in OpenAPI
  document.
- `src/lib/api/contracts.ts`: generated schema aliases plus handwritten runtime boundary guards and
  the custom error-envelope types that OpenAPI does not yet describe.
- `src/lib/api/sheet.ts`: legacy Apps Script wrapper; no review runtime module imports it after
  cutover.
- `src/lib/management/`: language/query parsing and management read-error presentation policy.
- `src/lib/management/pending.ts`: account-scoped, 24-hour exact deck/card creation recovery.
- `src/lib/management/mutations.ts`: mutation failure and optimistic-conflict presentation policy.
- `src/lib/api/mock.ts`: local mock word data.
- `src/lib/stores/auth.ts`: sign-in store.
- `src/lib/review/pending.ts`: account-scoped, 24-hour exact-command/idempotency-key recovery.
- `src/lib/review/interaction.ts`: presentation-independent flip-before-answer guard.
- `src/lib/stores/review.ts`: legacy Sheet-oriented review store, no longer used by the review route.
- `src/lib/types.ts`: shared app data contracts.
- `src/lib/utils.ts`: spaced-repetition intervals and ease-factor calculation.
- `src/lib/components/SwipeCards.svelte`: main review card interaction.
- `src/lib/components/ui/`: repository-owned Sheet, Alert Dialog, and Button components generated
  from the shadcn-svelte registry. They use Bits UI underneath and are configured by
  `components.json`.
- `src/lib/components/Drawer.svelte` and `ConfirmDialog.svelte`: task-specific management wrappers
  over the shared shadcn-svelte components, retaining local styling and feature-facing APIs.
- `src/lib/components/DeckForm.svelte`, `CardForm.svelte`, and `MutationNotice.svelte`: shared
  management mutation forms and failure presentation.
- `src/lib/components/AsyncButton.svelte`, `Modal.svelte`, `QuestionCard.svelte`, `QWordToMeaning.svelte`: reusable or older UI pieces.
- `src/app.css`: global CSS, Tailwind import, and base layout styling.
- `apps/api/app/main.py`: FastAPI application factory, lifespan boundary, and router composition.
- `apps/api/app/serve.py`: production process entrypoint with platform-port validation and bounded
  graceful shutdown.
- `apps/api/app/config.py`: typed, secret-safe environment configuration loaded during lifespan.
- `apps/api/app/cors.py`: exact-origin browser policy initialized from validated lifespan settings.
- `apps/api/app/database.py`: lazy SQLAlchemy engine construction, application-scoped session factory,
  explicit transaction ownership, readiness queries, and pool disposal.
- `apps/api/app/errors.py`: stable safe API error models and application/framework exception handlers.
- `apps/api/app/request_context.py`: per-request UUID generation and bounded JSON completion
  events for HTTP requests and committed/replayed review submissions.
- `apps/api/app/health.py`: database-independent liveness and database-aware readiness contracts.
- `apps/api/app/auth.py`: Google ID-token verification, backend verified-email allowlisting, stable
  subject to internal-user mapping, and the reusable authenticated-user dependency.
- `apps/api/app/reads.py`: authenticated owner-scoped deck/card/due-review routes, response models,
  normalized multilingual card substring filtering, stable tuple ordering, and safe database-failure
  translation.
- `apps/api/app/writes.py`: server-owned deck/card create, optimistic edit, and archive operations.
- `apps/api/app/reviews.py`: authenticated atomic review submissions, scheduling transitions,
  idempotent replay, and deterministic row-lock concurrency control.
- `apps/api/app/genai_consent.py`: authenticated `GET`, `PUT`, and `DELETE`
  `/v1/me/genai-consent` routes and reusable fresh consent checks. Only the authenticated
  owner is addressable. Responses contain nullable `genai_consent_at`; PUT retains an existing
  grant time. DELETE clears consent and deletes every owned embedding in one transaction.
  Semantic search returns `403 genai_consent_required` before coverage or provider work when
  consent is absent. Its shared user-row lock lasts through the request transaction.
  Card embedding claim and final-result transactions acquire the same shared user-row lock
  before card locks. Withdrawal's user update serializes with both. Provider document calls
  stay outside transactions; a running call cannot restore deleted claims, even after regrant.
  Backfill scans only consented owners and processing rechecks consent independently.
  Revision `20261105_0007` adds nullable `users.genai_consent_at` with no default or inferred
  grants and drops it on downgrade. The inline consent prompt in
  `src/routes/search/+page.svelte` names card text and search queries as content sent to
  Google Vertex AI. Semantic search is blocked until consent is granted. Withdrawal requires
  a second inline confirmation and warns that it deletes existing embeddings and cannot recall
  content already sent. A `403 genai_consent_required` returns the page to the consent prompt.

  Known limit: `process_card` checks consent in the claim transaction
  ([embeddings.py:179](../apps/api/app/embeddings.py#L179)); its shared user-row lock is released
  when that transaction ends. The provider call runs outside any transaction
  ([embeddings.py:260](../apps/api/app/embeddings.py#L260)). Withdrawal between claim commit and
  provider call start can therefore still send that one card's text to the provider. The final
  write recheck ([embeddings.py:268](../apps/api/app/embeddings.py#L268)) prevents storing the
  result. The maintainer accepted this limit and rejected holding a database lock across a
  network call.

- `apps/api/app/semantic_search.py`: bounded query validation and owner-scoped index coverage before
  one Vertex query embedding and exact pgvector ranking. Zero current embeddings skip both provider
  and ranking work after deck and provider-configuration checks. Coverage and ranking apply
  owner/archive/language/deck/model/state/hash SQL predicates.
- `apps/api/app/imports.py`: bounded CSV reading, validation, canonicalization, hashing, dry-run
  audit persistence, and private in-memory confirmed-import candidates.
- `apps/api/app/import_events.py`: bounded local import-command outcome events without source
  content, identities, hashes, or file paths.
- `apps/api/app/confirmed_imports.py`: approved-snapshot verification, atomic confirmed import,
  exact replay, post-commit reconciliation, safe reports, and the local operator CLI.
- `apps/api/app/semantic_text.py`: versioned NFC canonical card text and SHA-256 semantic hash.
- `apps/api/app/embeddings.py`: an application-lifespan-owned lazy Vertex embedding provider,
  vector validation, and owner/hash/model-guarded derived-data transactions after confirmed card
  commits. One lock protects ADC discovery, credential refresh, token snapshots, and auth transport
  shutdown. Fresh credentials serve both document and query calls; near-expired or expired tokens
  refresh before use. Discovery and refresh failures remain retryable. Prediction calls use
  independent `requests.post` operations with the existing eight-second timeout outside the lock.
  Startup and health checks do not discover credentials or contact Vertex.
- `apps/api/app/embedding_backfill.py`: explicit owner-bounded, keyset-paged retry and backfill CLI.
  Each invocation owns and closes one lazy embedding provider. Dry runs never discover credentials
  or call the provider. Application shutdown closes its provider's auth transport independently of
  database disposal.
- `apps/api/openapi.json`: committed deterministic API schema used for frontend type generation and
  contract-drift checks.
- `apps/api/scripts/export_openapi.py`: deterministic OpenAPI export from the FastAPI application.
- `apps/api/Dockerfile`: locked two-stage API build with a UID/GID `10001:10001` runtime and no
  development dependencies or `uv` binary in the final image.
- `apps/api/scripts/verify_container.sh`: disposable container check for effective identity,
  liveness, SIGTERM handling, and a clean exit.
- `apps/api/app/pagination.py`: versioned opaque cursor encoding, strict parsing, and normalized
  query-shape binding.
- `apps/api/migrations/`: Alembic environment and reversible migration history; the empty baseline
  is followed by the first production domain revision for users, decks, confirmed cards, tags,
  current review state, and review history.
  Revision `20260920_0006` enables pgvector, adds the nullable card semantic hash for existing
  rows, and stores versioned 512-dimensional derived vectors separately from confirmed cards.
- `apps/api/tests/unit/`: API configuration, lifecycle, probe, and HTTP contract tests.
- `apps/api/tests/integration/`: opt-in real PostgreSQL readiness, migration lifecycle, transaction,
  domain-constraint, fixture, and representative query-plan tests.
- `apps/api/tests/fixtures/multilingual_learning_domain.sql`: deterministic synthetic English and
  Japanese data spanning the complete Issue #8 schema for isolated PostgreSQL tests.
- `compose.yaml`: verified local `postgres:17-alpine` service with persistent development volume and
  health check, run through OrbStack's Docker-compatible engine.
- `.github/workflows/ci.yml`: independent frontend and PostgreSQL-backed backend verification jobs.
- `.github/workflows/ai-agent.yml`: checked-in Codex workflow. The automatic `issues` labeled
  trigger is disabled. `ai-ready` currently only means an issue is approved for an agent to read
  and implement. It does not automatically trigger this workflow. Manual `workflow_dispatch`
  remains, and the file still prepares disposable full-stack test dependencies, guards workflow
  and HEAD changes, and requires candidate verification before draft PR publication. See
  [`development.md`](development.md#automated-issue-verification).
- `.github/workflows/publish-api-image.yml`: protected manual WIF workflow that builds and publishes
  an immutable commit-tagged API image through an Artifact-Registry-only identity.
- `.github/workflows/migrate-production.yml`: protected manual OIDC workflow that serializes Neon
  upgrades through the Secret Manager-backed Cloud Run migration job and verifies every Alembic head.
- `.github/workflows/deploy-api-candidate.yml`: protected manual WIF workflow that deploys the same
  immutable commit-tagged image as a verified zero-traffic Cloud Run candidate; Cloud Run assigns a
  fresh revision name per deployment attempt so a failed attempt can be retried without rebuilding.
- `.github/workflows/smoke-api-candidate.yml`: protected manual WIF workflow that resolves the tagged
  zero-traffic candidate and runs authenticated smoke checks with a supplied short-lived Google ID token.
- `deploy/cloud-run/release.sh`: clean-commit Cloud Build, single-task migration, and tagged
  zero-traffic Cloud Run candidate release boundary.
- `deploy/cloud-run/smoke.sh`: public health, authenticated owned-read, and explicitly opted-in
  idempotent review-write smoke checks for a candidate revision.
- `deploy/cloud-run/release.env.example`: non-secret Cloud Run/Neon resource-name and public runtime
  configuration contract. Database URLs remain version-pinned Secret Manager values.
- `doc/training/issues/issue-26/github-gcp-neon-maintenance.zh-TW.md`: centralized GitHub variable,
  WIF, IAM identity, Secret Manager, and Neon role relationship map for production maintenance.

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
11. The outer CORS middleware permits only configured HTTP(S) frontend origins, the product's
    `GET`/`POST`/`PATCH`/`DELETE` methods, and its bearer/content/idempotency headers. It exposes `X-Request-ID` for
    browser-visible support diagnostics without enabling credentialed cookies.
12. The production container starts `app.serve` directly as PID 1. Uvicorn owns SIGTERM handling,
    stops accepting work, completes FastAPI lifespan cleanup within its bounded drain window, and
    exits. Schema migrations use the same image but run as a separate pre-deploy command; web
    startup never mutates the schema.
13. Production uses Cloud Run in `asia-southeast1` and Neon PostgreSQL in AWS Singapore. Neon is the
    only writable source of truth; there is no runtime provider switch, dual write, or replica.
14. The Cloud Run web identity receives only the pooled runtime database secret. A separate job
    identity receives only the direct migration secret. Both use the standard `DATABASE_URL`
    setting, with explicit production TLS validation.
15. A release builds one commit-tagged image, runs a single zero-retry Alembic job, then creates a
    tagged candidate revision with zero traffic. Health, owner scope, and one controlled idempotent
    write must pass before explicit traffic promotion. Rollback moves traffic only to a
    schema-compatible application revision and never automatically downgrades PostgreSQL.
16. GitHub Actions never connects directly to Neon. Three protected manual workflows use Workload
    Identity Federation to publish an immutable commit-tagged image, update and execute the Cloud
    Run migration job, and deploy a zero-traffic candidate. Separate Cloud Run migration and API
    identities read only their matching version-pinned database secrets. A second migration-job
    execution runs `alembic current --check-heads`; data restore, authenticated candidate smoke,
    promotion, and traffic rollback remain separate operations.

The English review frontend and English/Japanese management read pages now target this FastAPI
service. Normal review and management navigation makes no Apps Script call. Review and management
writes have no fallback or dual-write path.

## Backend Read Flow

1. Every product route under `/v1` verifies a Google bearer token for signature, issuer, configured
   audience, expiry, and verified-email status. Google `sub` resolves a generated internal user ID;
   email remains mutable profile data.
2. Request validation rejects unsupported languages, invalid resource IDs, unsupported filters,
   and malformed or query-incompatible cursors before running the list query.
3. Every SQL statement scopes by the resolved owner. Explicit deck, card, and tag lookups return the
   same not-found result for missing and cross-owner resources.
4. Deck lists seek after `(updated_at, id)` in descending order. Card lists use the validated
   `sort=updated_at|created_at` (default `updated_at`) with descending `(date, id)` ordering.
   Due reviews seek after
   `(next_review_at, card_id)` in ascending order and retain one server `as_of` time in the cursor.
5. Queries fetch `limit + 1`, return only `limit`, and emit a next cursor only when another record
   exists. Empty collections return `items: []` and `next_cursor: null`.
6. SQLAlchemy failures become retryable `503 database_unavailable` errors through the common safe
   envelope; internal database details are never serialized.

## Backend Write And Authorization Flow

1. The reusable current-user dependency verifies the bearer token and upserts `users` by unique
   `google_subject` in the request transaction.
2. Reads and mutations combine client-addressable resource IDs with the server-derived internal
   owner ID. Missing and cross-owner details both return the same non-disclosing `404`.
3. Deck and card creates bind ownership from authenticated context. Extra request fields are
   forbidden, so a body-supplied owner ID or email is rejected before SQL.
4. Edits use an owner predicate plus the last-seen version and increment the version atomically;
   stale owned writes return `409 version_conflict`.
5. Deletes archive rather than physically removing decks or cards. Card creation also creates the
   required initial review state in the same transaction.
6. Deck/card creates require a UUID idempotency key. Versioned normalized validated request content is hashed
   and stored with the resource under a partial owner/key unique index. Exact retries return that
   resource; different content under the key returns `409 idempotency_key_reused`.
7. Single-card create and semantic edits explicitly commit confirmed content before scheduling
   the existing hash-guarded embedding operation as a best-effort in-process background task.
   ASGI sends the final response body before that task runs. Note-only edits skip embedding work;
   unchanged semantic content skips the provider when its current embedding is already ready.
   Missing or failed derived data remains recoverable through explicit backfill, including when
   the process stops after confirmation and before the task finishes.

## Backend Review Write Flow

1. `POST /v1/reviews` requires the authenticated owner and a UUID `Idempotency-Key`; one to ten
   unique items carry only card ID, decision, and expected state version.
2. The API hashes the canonical validated item sequence and inserts an owned batch under the
   database unique key. A matching conflict replays stored events; different content returns a
   conflict.
3. A new batch locks every owned card, deck, and current-state row in sorted card-ID order. It then
   verifies active status and optimistic versions for the complete request before writing an event.
4. The backend uses one UTC review instant and `srs-v1` to derive every transition, inserts immutable
   before/after events in request order, and updates current states with previous-version predicates.
5. The request transaction commits the batch, all events, and all states together. Any exception or
   item failure rolls the complete request back.

English and Japanese travel through the same routes, response models, ownership checks, tables, and
management components. The review UI currently requests English while retaining the shared
language-aware API contract.

## Initial Domain Schema

The complete implemented relationship view is documented in the
[Issue #8 entity-relationship diagram](training/issues/issue-8/erd.md). The local PostgreSQL planner
evidence is recorded in the [Issue #8 query-plan report](training/issues/issue-8/query-plans.md).

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
  deck-list ordering and is selected for the representative query.
- `tags` uses normalized per-owner identity through unique `(owner_id, normalized_name)` and exposes
  unique `(id, owner_id)` for owned associations.
- `learning_card_tags` uses `(card_id, tag_id)` as its primary key and validates the repeated owner
  through composite foreign keys to both parent rows. Tag deletion cascades only to associations;
  physical card deletion is restricted while an association remains.
- `(tag_id, card_id)` supports filtering cards by tag because the association primary key begins
  with `card_id`; PostgreSQL selects it for the representative reverse traversal.
- `review_states` uses `card_id` as its primary key, directly enforcing at most one current row per
  card. Its composite `(card_id, owner_id)` foreign key rejects cross-owner state.
- Review scheduling fields are required without database defaults, so the backend writes
  the initial stage, ease, interval, next-review time, and version explicitly. Checks enforce stage
  1-5, ease 1.30-2.50, nonnegative intervals, positive versions, and next review not before a present
  last review.
- `(owner_id, next_review_at, card_id)` supports stable owner-scoped due retrieval and is selected
  for the representative due query even with archived-card/deck joins.
- `review_batches` owns the client idempotency key through unique `(owner_id, idempotency_key)` and
  stores one backend review time, algorithm version, request hash, and bounded item count. Unique
  `(id, owner_id)` supports owned event relationships.
- `review_events` retains required before/after scheduling snapshots. Composite batch/card foreign
  keys reject both forms of cross-owner history; local checks enforce decision/quality mapping,
  scheduling ranges, version progression, and timestamp relationships.
- Review-event indexes support owner history, card history, and batch response reconstruction. Their
  definitions and representative PostgreSQL planner use are tested.
- A local one-time CSV dry-run CLI feeds a pure bounded validator, verifies an existing target deck
  through `(deck_id, owner_id)`, and persists only `import_runs` plus `import_items`. Canonical
  snapshot/content hashes and validator version make unchanged replay deterministic. Diagnostic
  JSON contains safe codes and field names rather than raw legacy learning content. This path has no
  HTTP route and cannot write cards, tags, review state, batches, or events.
- A separate confirmed-import CLI rereads the private CSV and locks the approved dry run and target
  deck before comparing all metadata, snapshot hashes, source identities, content hashes, and row
  outcomes. A single transaction creates cards in the existing deck, reuses or creates normalized
  owned tags, creates associations and deterministic fresh review states, persists source-to-card
  mappings, and records the completed apply. Unique owner/namespace and dry-run constraints make
  exact and concurrent replay return one committed result without new mutations.
- Reconciliation runs only after the apply commits. It verifies approved/applied counts, ownership,
  deck membership, canonical content hashes, tags, associations, archived state, fresh scheduling,
  deterministic content-free samples, and the absence of review history for imported cards. Its
  passed or failed result is persisted as counts, hashes, booleans, row numbers, and safe codes, so
  retry can recover after a post-commit CLI interruption without retaining duplicate card content.
- Event-count agreement with a batch, consistency with current state, atomic state/event writes,
  request-hash replay handling, and the no-mutation application contract are enforced by the review
  service transaction and its PostgreSQL integration tests.
- The checked-in bilingual fixture uses one owner with English and Japanese decks/cards, shared
  reusable tags, current states, and one two-card review batch. It is test evidence, not a production
  seed or import path.
- Authenticated `/v1` routes read and write these tables. Review and deck/card management are
  integrated; final production cutover verification remains pending.
- Query-plan evidence comes from a deterministic local dataset with 40,000 cards, states, tag links,
  and events. It verifies planner selection, not production latency, throughput, or future planner
  behavior.

## API Error Contract

Failures use `{ "error": { "code", "message", "retryable", "request_id", "details"? } }`.
Machine-readable `code` values are the client contract; messages are human-readable fallbacks.
`request_id` also appears in `X-Request-ID`. Validation details contain only safe field paths,
field-level codes, and fallback messages. The readiness endpoint retains its purpose-specific health
contract rather than masquerading dependency unavailability as an application exception.

The API also emits one JSON `http_request_completed` event for each request
that reaches its request middleware. It joins the browser-visible server
`request_id` to a matched route template, status, duration, bounded outcome,
and optional stable error code. It excludes request values and user identity.
The web process disables Uvicorn access logging of raw URLs. CORS preflights
are answered by outer middleware and are not included in this event stream.
Cloud Run platform request logs remain a separate privacy and retention audit
boundary; deployed JSON ingestion and lookup are pending Issue #27 verification.

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

1. `/review` selects `OwnedReview.svelte` for an authenticated subject. That component asks the typed client for up to ten English due cards.
2. The client sends `GET /v1/reviews/due` with the current ID token only in `Authorization` and
   validates the successful page contract before returning it.
3. The page shuffles the due cards and `SwipeCards.svelte` retains the flip/swipe presentation.
4. Each answered back face emits only `card_id`, `decision`, and the due response's
   `review_state.version`; no scheduling value is calculated in the browser.
5. The first submit creates and persists one account-scoped body/key pair. The client sends that
   exact body to `POST /v1/reviews` with `Idempotency-Key`.
6. Network, authentication, retryable provider/database, and ambiguous response failures do not
   produce success. Eligible manual retries reuse the persisted body/key pair.
7. A conflict retires the old command and refetches due state; a validated `ReviewResult` clears it
   and produces the completed UI.

## Management Read Flow

1. `/decks` treats a missing `language` query as English and replaces the URL with
   `?language=en`; unsupported values show a validation state without making an API request.
2. English and Japanese tabs reuse the same route, client methods, domain contracts, and list
   components. Active/archive filtering is expressed through the API `status` query.
3. The client sends bearer-authenticated deck/card list and detail requests to `/v1`, then validates
   each successful JSON boundary before displaying it.
4. Deck and card IDs remain owner-scoped on the backend. A missing or cross-owner detail produces
   the same non-disclosing not-found UI.
5. Japanese cards show reading and romanization when present; English cards show pronunciation.
   Both languages share meaning, definition, example, relation, tag, note, and review-state fields.
6. Loading, empty, authentication, not-found, retryable, server, and malformed-response states are
   distinct. A failed or unclear read never renders stale data as a successful response.

## OpenAPI Type Flow

1. FastAPI's application schema is exported deterministically to `apps/api/openapi.json`.
2. `openapi-typescript` generates `src/lib/api/generated.ts`; both artifacts are committed.
3. `src/lib/api/contracts.ts` selects the product types and retains runtime guards because generated
   TypeScript alone cannot validate untrusted network JSON.
4. Frontend CI regenerates both artifacts and fails on a diff, so a backend contract change cannot
   silently leave the checked-in frontend types stale.

## Management Mutation Flow

1. Deck create/edit uses a compact drawer. Card create/edit shares `CardDialog.svelte`, a
   centered Bits UI dialog up to 60rem wide on desktop and full-screen at 640px or narrower.
   Its header stays visible while the body scrolls; the existing mobile single-column form remains.
   Language-specific fields remain conditional within the shared form.
2. Before create, the browser stores one exact body/UUID key for the current Google subject. An
   unclear, retryable, or authentication result keeps and locks that command; an exact manual retry
   sends the same pair. Confirmation or definite rejection clears it.
3. Edits submit the last-read resource version. A `409 version_conflict` keeps the user's values and
   only discards them after the explicit latest-state reload action.
4. Archives require confirmation. If the response is unclear, the page reads the resource again and
   only navigates to Archived after observing `archived_at`; otherwise it shows an unconfirmed state.

## JSON Card Authoring

- The add-card drawer defaults to Manual and offers a JSON tab with a copyable prompt derived from
  the owned deck's target and explanation languages. Users generate JSON in their own AI tool;
  the application does not call an AI generation provider.
- Pasted input is a content-only object with a `cards` array. Deck IDs, ownership, languages, and
  review scheduling are excluded from card entries. The browser enforces a 100,000-byte input
  bound and sends the object to `POST /v1/decks/{deck_id}/card-drafts/validate`.
- The input runs local Ajv JSON Schema validation 350 ms after typing or pasting, without an
  API call. Invalid content disables preview and shows card/field errors. Constrained strings are
  trimmed before validation to match Pydantic; enums and dates are left unchanged. Calendar dates
  use `ajv-formats`. Preview and edited selections are also checked synchronously before requests;
  uncertain save commands still replay unchanged.
- `npm run api:generate` exports `src/lib/api/card-drafts.schema.json` directly from the Pydantic
  draft model. The model's JSON Schema annotations publish its existing example and part-of-speech
  dependencies. CI checks this artifact alongside OpenAPI and generated TypeScript to catch drift.
- This authenticated, owner-scoped, active-deck endpoint reuses Pydantic `CardFields`, forbids
  extra fields, requires 1-20 cards, limits valid request bodies to 100,000 bytes, and returns
  normalized drafts. It creates no cards or review states. Invalid fields use the existing safe
  validation envelope, including card indices.
- Users edit, deselect, and explicitly confirm drafts. The complete selected set is checked and
  normalized synchronously against the local schema after edits, without another remote validation
  request. The normalized typed fields and keys are persisted before one `POST /v1/decks/{deck_id}/cards/bulk` request. Its Pydantic
  envelope contains 1-20 `{idempotency_key, fields}` entries and is bounded to 100,000 bytes.
  The bulk endpoint still validates every card with Pydantic `CardFields`.
  Deck context stays in the route. All new cards, fresh review states, and semantic hashes commit
  in one transaction; any rejection rolls back every new card in the selection.
- Bulk and single-card creation share the same per-card idempotency keys and normalized request
  hashes. Keys must be distinct within a selection. The response returns key/card pairs in input
  order. An owned deck row lock serializes creation against archival; sorted keys prevent overlapping
  batches from acquiring unique-key conflicts in different orders. Exact existing-card replay is
  allowed after archival, but new cards are rejected. Existing single-card clients remain supported.
- The browser persists the entire account-scoped selected content/keys before sending the request.
  Uncertain commands have no automatic expiry, lock the selection against editing, and replay
  unchanged after reload. Previously confirmed cards are skipped, including older individual-save
  queues. A definite rejection permits correction; keys stay stable until a draft is edited.
  Storage failure prevents starting the write. Bulk response guards require matching keys, deck,
  count, and distinct card IDs before marking any entry confirmed.
- Bulk embeddings run as best-effort in-process background tasks after the confirmed response,
  using the existing hash-guarded embedding operation. They do not hold the card transaction or
  delay confirmation; process interruption and provider failure use the existing explicit backfill.

## Auth Flow

- The auth store models initializing, signed-out, guest and authenticated sessions. Root layout
  hydrates credentials before routing. Valid Google credentials take priority over a guest choice.
- `enterGuestSession()` stores an absolute deadline 30 minutes after explicit selection in
  tab-scoped `sessionStorage`. Hydration, focus and the existing one-second watcher check it;
  reload and activity never renew it. Expired, legacy or malformed markers are removed.
  Storage failure keeps the user on home with a recoverable message. This is UI state only.
- Guest expiry transitions to signed-out, unmounts guest review (aborting requests), and returns
  home with base-aware navigation. Valid authentication takes priority. Primary navigation is
  hidden while initializing or signed-out, retaining header space and the account avatar.
- The account avatar opens an accessible sign-in/sign-out menu. Shared Google sign-in UI accepts
  the existing client-ID/verified-email/whitelist contract. Successful login clears the guest choice.
- `getTokenIfValid()` rejects missing or near-expired tokens, clears stale credentials, and marks
  the auth session signed-out. Cross-tab credential changes synchronize the current session.
- API `401` signs out only when the request token is still the current token. A delayed old-token
  `401` cannot remove a newer account's credentials. Current-token sign-out does not navigate or
  remove a pending review. Explicit menu sign-out
  additionally removes the guest choice and returns home. Same-subject login can retry an exact
  pending command; another subject retires it before private review is initialized.
- `/review` owns fresh-entry protection. Once private review starts, signed-out state preserves
  its controller for reauthentication. Subject changes remount it; stale requests cannot update
  the new account's UI or clear its pending command. Backend identity/ownership remain authoritative.

## Static Hosting Notes

- `svelte.config.js` uses `adapter-static` with `fallback: '404.html'`.
- `paths.base` is empty during dev and reads `process.env.BASE_PATH` otherwise.
- Use `$app/paths.resolve()` for internal URLs.
- `PUBLIC_API_BASE_URL` is the external API base and is not prefixed with the static frontend's
  `paths.base`; a trailing slash is normalized by the client.
- GitHub Pages deployment validates that the public API value is a configured HTTPS base URL before
  building. Neither CI nor deployment supplies an Apps Script variable.
- `src/lib/api/sheet.ts` is retained as rollback evidence, but it has no ambient endpoint. Any use
  now requires a caller to inject an Apps Script endpoint explicitly; no normal runtime module does.
- FastAPI's `CORS_ALLOWED_ORIGINS` is an explicit JSON array of frontend origins. Local defaults
  cover `localhost:5173` and `127.0.0.1:5173`; production must provide its real static origin.

## Static guest review boundary

`/review` hosts separate `GuestReview.svelte` and `OwnedReview.svelte` controllers.
Authenticated identity always selects owned review. Guests explicitly choose entry on home;
the tab-scoped 30-minute deadline survives reload, while answers and card pools do not.
Login, expiry and navigation unmount the guest controller and abort pending reads.

Guest downloads the base-aware same-origin `/guest/cards.json` once per mounted controller,
with credentials omitted, redirects rejected, a 15-second timeout and a 512 KiB streaming cap.
The generated snapshot schema rejects extra fields and non-English content. Duplicate IDs
also fail validation. The pool has at most 50 cards; rounds shuffle a copy and take at most ten.
Practice again samples in memory without a network request. Errors require explicit retry.
There is no backend fallback, automatic retry, persisted answer, or scheduling logic.

The shared presentation keeps flip-before-answer, grading, swipes and keyboard controls.
Only owned cards supply private context and review-state versions for authenticated submissions.
Guest interaction does not read or mutate private pending submissions or completion markers.
The anonymous API, source buckets and API-specific cooldowns are retired in the final release.

### Static guest publication exporter (2026-10-23)

`GET /v1/internal/guest-cards/export` is separate from browser authentication. It verifies
Google's signature/issuer/expiry and a dedicated export audience, exact service-account
subject, exact email and `email_verified=true` before database checkout. It never resolves
or upserts an application user. All four `GUEST_EXPORT_*` identity/deck settings must be
configured together; otherwise export is disabled or startup rejects partial settings.
The content-only projection is shared in `app/public_content.py`. A read-only transaction,
statement timeout and one nonblocking export permit bound the database work. The response
contains `schema_version=1`, `generated_at`, and up to 50 distinct active English cards,
with a 512 KiB encoded size limit. Missing/wrong-language decks fail; archived decks and
empty active decks export an intentional empty pool.

Pages can publish the empty static seed while the existing backend remains available, then
remove the anonymous route with the final protected-export backend after the static cutover.
Supporting backend commit `34c7560` retains the anonymous route and is optional when real cards
must be exported before the first static publication. Pages itself does not depend on that release.
`.github/workflows/export-guest-cards.yml` is manual-only and restricts both jobs to trusted main.
Its protected `guest-cards-export` job uses dedicated WIF impersonation with read-only contents
and ID-token permissions. It uploads only validated JSON. A separate proposal job has contents
and PR write permissions, no Google credentials or ID-token permission, and consumes only that
same-run artifact. It creates or updates `automation/guest-cards-snapshot` into main, limiting
committed changes to `static/guest/cards.json`. It never merges or deploys.

Approved public snapshots are tracked in Git, starting with an intentional empty envelope.
`.github/workflows/deploy.yml` independently validates that committed JSON, builds the frontend,
and publishes through the protected `github-pages` deployment. It uses no export API or Google
credentials. Both publication workflows require manual dispatch, with separate concurrency groups.
CI validates the source snapshot before building. Browser fixtures replace only ignored build
output after compilation, preserving the tracked source. The local validator and browser/export
transports share the generated strict schema, duplicate-ID check and 512 KiB streaming limit.
Live WIF, Actions PR creation and deployment are not verified by repository tests.

## Transaction-local row level security (2026-11-05)

Migration `20261105_0008` enables fail-closed RLS on all 11 owner-bearing tables.
The owner policy uses `owner_id = NULLIF(current_setting('app.user_id', true), '')::bigint`
for both visibility and writes. Missing, empty, or unknown owner context exposes no rows.
Existing application owner predicates remain required. `users` stays outside RLS so authentication
can resolve the internal owner before accessing private tables.

`database.bind_owner` validates a positive integer and stores it in the short-lived session's
`info`. The SQLAlchemy `Session.after_begin` listener parameterizes
`SELECT set_config('app.user_id', :owner_id, true)` on every transaction, including after a
mid-request commit or rollback. Binding after authentication's first query also applies it to the
active transaction. An identity cannot change within one session. Request sessions bind in
`auth.current_user`; `database_transaction(owner_id=...)` binds embedding claim/final-write
transactions and backfill scans. Consent locks and document-provider calls outside transactions
retain their existing boundaries.

Guest export opens a separate unowned session, executes `SET TRANSACTION READ ONLY` first,
then `database.bind_public_deck` sets only `app.public_deck_id` to the configured UUID.
The two public SELECT policies expose only that deck and its cards; they grant no writes and no
access to the other nine tables. Owner and public identities cannot coexist in an app session.
All identity settings are transaction-local (`true`); pooled physical connections retain neither
identity after commit/rollback. Local PostgreSQL pool reuse is tested. Neon pooled transaction
mode, production pooling behavior and per-transaction latency remain unverified.

RLS is not forced: table owners and superusers/BYPASSRLS roles intentionally bypass it for
migration and maintenance. Runtime must use a non-owner role with neither elevated flag.
Operator report (2026-11-05), not programmatically verified: production runtime uses
`app_runtime_limited`, whose `rolsuper` and `rolbypassrls` are false; all 11 tables are owned by
`neondb_owner`. No production connection was inspected by this implementation.

The old `imports.py` and `confirmed_imports.py` tools are considered disabled under runtime RLS;
they do not bind an owner and cannot access the protected import tables. Their historical tests
use explicit owner maintenance sessions. `import_items` lacks `owner_id` and remains a known RLS
gap; its logical ownership is through `import_runs`. Removing retired tools/tables is separate work.

For this migration, override the ordinary migrate-before-app release sequence above:

1. Deploy and verify the app revision that binds `app.user_id` while the previous schema is still
   active. Ensure every serving runtime revision supports transaction identity before migration.
2. Apply migration 0008, then verify authenticated reads/writes, embedding, backfill and export
   with the restricted runtime role before completing rollout.
3. Before rolling back to an app without identity binding, first disable RLS on all 11 tables
   (`ALTER TABLE ... DISABLE ROW LEVEL SECURITY`) or explicitly downgrade 0008 using the migration
   role. Only then roll back application traffic. An ordinary application-only rollback is unsafe.

These are operator instructions, not an executed rollout. Existing release workflows/scripts were
not changed and still require a separately reviewed operational sequence for this exception.
See [Issue #75 verification](issues/issue-75-verification.md) for local evidence and limits.

## Stateless card extraction (2026-11-05)

`app/extraction.py` registers `POST /v1/decks/{deck_id}/card-drafts/extract` alongside the
unchanged draft validation/bulk creation routes. It shares the authenticated RLS-bound session,
reads only the owned active deck's languages, then calls `require_genai_consent`. It explicitly
commits this short transaction before invoking the app-scoped generation provider. No connection
or consent lock spans model latency; a later consent withdrawal cannot recall in-flight data.
There is no draft storage or generated-card write, so there is no derived persistence to reconcile.

`app/generation.py` owns a general generation Protocol, lazy ADC REST adapter, bounded error codes,
request/response contract functions and schema conversion. Structured JSON is an optional request
capability, leaving future tool calling to #70. Extraction uses the existing `CardDrafts` schema,
projects it to an explicit provider subset and strictly validates returned JSON with the complete
server model. Material, instruction and existing drafts stay in a JSON data message; fixed prompt
rules are separate. Prompt alignment tests compare frontend/server key rules. No frontend flow,
auth contract, migration, scheduling or bulk-create behavior changes.

Vertex request/response/schema compatibility is unverified; tests use handwritten and scripted
responses only. Missing explicit model/project configuration fails closed with 503. Structured
completion logs contain identifiers, adjustment, timing, tokens and result code only. The eight
AI-drafted synthetic evaluation cases remain unreviewed. See
[Issue #72 verification](issues/issue-72-verification.md) for acceptance evidence and limits.

## Stateless readonly assistant (2026-11-05)

`app/assistant/routes.py` adds the authenticated, consent-gated non-streaming
`POST /v1/assistant/messages` contract. It validates text-only user/assistant history and
configured message/character limits before checking consent. No conversation storage,
write tools or migrations are added. The browser UI is deferred pending design selection;
only generated API types change under `src/`.

`app/assistant/loop.py` runs at most three model calls through #72's generation Protocol.
`GenerationRequest` now optionally carries multi-turn contents, fixed function declarations
and explicit tool disabling. `GenerationResult` preserves complete validated model parts,
including opaque thoughtSignature, plus parsed function calls. Extraction still rejects
unsolicited function calls. Unknown/mixed media parts and malformed calls fail closed;
existing malformed-body error classification and generation location routing remain intact.
The final call sends `NONE`. Parsed calls normalize omitted arguments to an empty object
and echo a supplied call ID in the matching tool response. Signed parts are replayed intact.
The synthetic live evaluation exercised this protocol on Gemini 3.5 Flash-Lite. The server
blocked a tool call the model still proposed on its final step.
See the [dated evaluation](training/issues/70/README.md#live-result-on-2026-11-07).

`app/assistant/tools.py` owns the fixed registry and strict argument models. Unknown names,
extra owner/user fields and invalid arguments never reach tools. Owner identity comes from
the request session. Shared `semantic_search.search_cards` retains the old HTTP query logic;
its assistant-only transaction-release option also reapplies readonly SQL settings before
ranking. `reads.get_due_cards` retains pagination and filter behavior. Statistics reuses
`reads.DUE_CONDITION` rather than duplicating due rules. Tools use a common request-time
snapshot, explicit owner predicates and transaction-local RLS binding.

The existing auth transaction completes before starting the assistant budget. An orchestration
worker creates and exclusively owns a separate session, binds the same authenticated owner,
and closes it itself even after the caller times out. One absolute deadline covers initial
and repeated consent, pool waits, tool SQL and provider waits. SQL gets the remaining statement
timeout before consent and tool reads. Auth/validation remain framework preconditions. Consent
work commits before generation; tools open short readonly transactions and roll them back. Assistant embedding latency also runs without a database transaction.
Every new transaction uses the existing after_begin identity binding. Provider-only worker
threads bound waits, cannot access sessions or execute tools, and may finish after a timeout;
remote cancellation is not guaranteed. Consent is checked again before each generated turn
and before query embedding. Already-transmitted data cannot be recalled after withdrawal.
Per-step structured logs contain only correlation, bounded state, timing and nullable usage.

[Issue #70 verification](issues/issue-70-verification.md) maps backend acceptance to local
checks. [Evaluation assets](training/issues/70/README.md) use a synthetic tool sandbox in both
modes; replay is provisional and true Vertex mode requires explicit flag/environment opt-in.
No live model, production connection, streaming or Neon pool behavior was verified.
