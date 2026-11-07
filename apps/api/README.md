# English Learning API

FastAPI backend for the English Learning application. Run the commands below from `apps/api/`.

## Requirements

- Python 3.12 or newer
- `uv`

## Setup

Create or synchronize the local environment from the committed lockfile:

```bash
uv sync --locked
```

## Production container

Build the API from the repository root. The image installs only locked runtime dependencies, runs
as UID/GID `10001:10001`, and starts one Uvicorn process on the platform-provided `PORT` (default
`8080`):

```bash
docker build --tag english-learning-api:local apps/api
bash apps/api/scripts/verify_container.sh english-learning-api:local
```

The verification script starts a disposable container on a random host port, checks liveness and
the effective runtime UID/GID, sends `SIGTERM`, requires a graceful application shutdown and exit
status `0`, then removes the container.

The image includes Alembic so a release system can run migrations as a distinct reviewed job:

```bash
docker run --rm \
  --env-file /path/to/runtime-secrets.env \
  english-learning-api:local \
  alembic upgrade head
```

Do not bake environment files into the image. Do not run migrations automatically during web
process startup: concurrent revisions could race, and a failed migration must stop the release
before new application instances receive traffic.

## Configuration

Local development works with safe disposable defaults. To override them, create an optional `.env`
file beside `pyproject.toml`; use `.env.example` as the field reference.

| Variable                           | Default                         | Constraint                                                                                                      |
| ---------------------------------- | ------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `APP_ENV`                          | `local`                         | `local`, `test`, or `production`                                                                                |
| `LOG_LEVEL`                        | `INFO`                          | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`                                                              |
| `DATABASE_URL`                     | Local disposable PostgreSQL URL | Must use the `postgresql+psycopg` driver; production also requires verified TLS or required TLS channel binding |
| `DATABASE_CONNECT_TIMEOUT_SECONDS` | `2`                             | Integer from 1 through 10                                                                                       |
| `GOOGLE_OAUTH_CLIENT_ID`           | Local placeholder               | Google web OAuth client ID used as the accepted token audience                                                  |
| `GOOGLE_ALLOWED_EMAILS`            | Empty locally                   | Comma-separated verified Google email allowlist; required in production                                         |
| `VERTEX_PROJECT_ID`                | Unset                           | Google Cloud project that enables provider-backed embeddings and semantic search when configured                |
| `VERTEX_LOCATION`                  | `us-central1`                   | Vertex AI region used for embedding requests                                                                    |
| `CORS_ALLOWED_ORIGINS`             | Local Vite origins              | JSON array of exact browser origins allowed to call the API                                                     |

Production must explicitly override `DATABASE_URL`, `GOOGLE_OAUTH_CLIENT_ID`, and
`GOOGLE_ALLOWED_EMAILS`; their local defaults
are rejected.
Database URLs are treated as secrets and must not be printed or logged.
`VERTEX_PROJECT_ID` is intentionally optional: when it is absent, semantic search returns the safe
`semantic_search_not_configured` response and card writes skip provider-backed embedding work.
Local provider calls use Application Default Credentials; the effective identity must be allowed to
invoke Vertex AI in the configured project.
The web process emits one JSON `http_request_completed` line per routed request
with its server-generated `X-Request-ID`, matched route template, method,
status, duration, bounded outcome, and optional stable error code. The process
disables Uvicorn access logging so it does not echo raw request URLs. The event
does not contain headers, query values, bodies, SQL, exception text, or user
identifiers. Cloud Run platform request logs are a separate source whose fields
and retention must be checked during deployment verification.
Production accepts `sslmode=verify-ca` or `sslmode=verify-full`. For Neon clients that use
`sslmode=require`, `channel_binding=require` is also mandatory. The Cloud Run runtime injects a
pooled least-privilege URL, while the separate migration job injects a direct schema-owning URL under
the same variable name; the web process never receives the migration credential.

FastAPI creates the SQLAlchemy engine during lifespan startup and disposes its connection pool during
shutdown. Engine creation is lazy and does not require PostgreSQL to be available; database
availability is reported separately by the readiness endpoint.

## Database migrations

Start PostgreSQL before running migrations. Upgrade a clean or existing development database to the
latest checked-in revision with:

```bash
uv run alembic upgrade head
```

During development, revert the latest revision and apply it again with:

```bash
uv run alembic downgrade -1
uv run alembic upgrade head
```

Use `uv run alembic current` to inspect the applied revision. Downgrades are a development
verification and recovery tool, not an assumed production rollback strategy. The initial Issue #7
baseline is intentionally empty. Issue #8 revision `20260902_0002` begins the production domain
schema with owned users, multilingual learning decks, confirmed learning cards, and reusable
per-owner tags. It also stores one current review state per card with database-enforced ownership,
scheduling ranges, timestamp ordering, and due-review indexing. Owned review batches provide
per-user retry-key uniqueness, while review events retain complete constrained before/after
snapshots for history and response reconstruction.
Issue #9 revision `20260903_0003` adds the owner/update ordering indexes used by deck and card
management reads.
Issue #22 revision `20260909_0004` adds owner/deck-scoped dry-run audit records and bounded per-row
diagnostics. It stores hashes and safe codes, not raw legacy learning content.
Issue #23 revision `20260910_0005` adds one-time confirmed-import runs and database-constrained
source-to-card mappings. One transaction creates cards, normalized owned tags, associations, fresh
review states, mappings, and the completed apply record; reconciliation is persisted separately
after commit so an interrupted client can recover by exact replay.

The production migration and candidate-release sequence is documented in the
[Issue #26 runbook](../../doc/training/issues/issue-26/runbook.md). It uses the same locked image as
the web service, executes one zero-retry migration task before deployment, and never migrates during
web startup.

## One-time legacy CSV dry run

The ignored private Sheet export is validated through a local CLI; there is no permanent import HTTP
endpoint. The target user and matching English or Japanese deck must already exist. Keep private
reports outside the repository:

```bash
uv run python -m app.imports \
  --csv legacy-google-sheet-cutover-v1.csv \
  --source-namespace legacy-google-sheet-cutover-v1 \
  --owner-id OWNER_ID \
  --deck-id DECK_UUID \
  --target-language en \
  --snapshot-captured-at 2026-09-09T00:00:00+08:00 \
  --report /tmp/legacy-google-sheet-dry-run.json
```

The command persists only `import_runs` and `import_items`. Replaying an unchanged snapshot returns
the existing run. It never creates confirmed cards, tags, review states, batches, or events. See the
[Issue #22 artifact](../../doc/training/issues/issue-22/README.md) for mapping, normalization,
scheduling-reset, and diagnostic-safety rules.

## One-time confirmed legacy CSV import

Only apply a final dry run with zero rejected rows after reviewing its sanitized report. The command
must repeat the exact owner, existing deck, namespace, language, snapshot timestamp, and validator
version used by that dry run. Keep both operational reports outside the repository:

```bash
uv run python -m app.confirmed_imports \
  --csv legacy-google-sheet-cutover-v1.csv \
  --approved-dry-run-id DRY_RUN_UUID \
  --owner-id OWNER_ID \
  --deck-id DECK_UUID \
  --source-namespace legacy-google-sheet-cutover-v1 \
  --target-language en \
  --snapshot-captured-at 2026-09-09T00:00:00+08:00 \
  --validator-version csv-dry-run-v1 \
  --report /tmp/legacy-google-sheet-confirmed-import.json \
  --reconciliation-report /tmp/legacy-google-sheet-reconciliation.json
```

Exit code `0` means apply/replay and reconciliation passed. Validation, apply, database, or report
failures return `2`; a persisted reconciliation mismatch returns `3`. An unchanged retry after a
commit or report-writing interruption returns the existing apply without changing product rows,
then completes or reconstructs reconciliation. Never use a newer or edited CSV with an older dry
run ID. See the [Issue #23 runbook](../../doc/training/issues/issue-23/runbook.md) before operating
on the private snapshot.

## Local PostgreSQL

From the repository root, start PostgreSQL and wait for its health check:

```bash
docker compose up -d --wait postgres
```

Inspect or stop the service with:

```bash
docker compose ps
docker compose stop postgres
```

## Start the development server

```bash
uv run uvicorn app.main:create_app --factory --reload
```

The development server listens on `http://127.0.0.1:8000` by default. `--reload` is for local
development only.

## Authenticated product APIs

All `/v1` endpoints require a Google ID token in `Authorization: Bearer <token>`. The backend verifies
the token, rejects accounts outside the configured email allowlist before user creation, and derives
ownership from the stable Google subject; request bodies cannot select an owner.

```text
GET /v1/me
GET /v1/decks
POST /v1/decks
GET /v1/decks/{deck_id}
PATCH /v1/decks/{deck_id}
DELETE /v1/decks/{deck_id}
GET /v1/cards
POST /v1/cards
GET /v1/cards/{card_id}
PATCH /v1/cards/{card_id}
DELETE /v1/cards/{card_id}
GET /v1/reviews/due
POST /v1/reviews
```

The read filter and pagination examples are in
[`doc/training/issues/issue-9/api-examples.md`](../../doc/training/issues/issue-9/api-examples.md). The
implemented authorization matrix and write boundary are in
[`doc/training/issues/issue-10/README.md`](../../doc/training/issues/issue-10/README.md).
The atomic review contract, idempotency behavior, concurrency policy, and timeout recovery are in
[`doc/training/issues/issue-11/README.md`](../../doc/training/issues/issue-11/README.md).

## Verify liveness

With the development server running, use a second terminal:

```bash
curl -i http://127.0.0.1:8000/health/live
```

The expected response body is:

```json
{ "status": "ok" }
```

Liveness reports whether the API process can handle requests. It intentionally does not query
PostgreSQL.

## Verify readiness

Readiness runs a bounded `SELECT 1` query against PostgreSQL:

```bash
curl -i http://127.0.0.1:8000/health/ready
```

Available PostgreSQL returns `200`:

```json
{ "status": "ready", "checks": { "database": "ok" } }
```

Unavailable PostgreSQL returns `503` without connection details:

```json
{ "status": "not_ready", "checks": { "database": "unavailable" } }
```

## Tests and checks

```bash
uv run pytest tests/unit -q
uv run ruff check .
uv run ruff format --check .
```

With local PostgreSQL available, run the opt-in integration tests with:

```bash
RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest tests/integration -q
```

The root Compose definition and CI integration suite use
`pgvector/pgvector:0.8.6-pg17-bookworm` for PostgreSQL 17 with pgvector 0.8.6. Local Compose is
verified through OrbStack. Integration tests are opt-in and fail if PostgreSQL is unavailable;
they never substitute SQLite. The migration test creates a uniquely named temporary PostgreSQL database, verifies
`upgrade -> baseline downgrade -> upgrade`, and removes that database afterward. Domain constraint
tests also run in isolated temporary databases. Production startup commands are still pending.

The cycle verifies both the head and reverted baseline at the assertions' level of detail. The
current baseline intentionally has no domain tables, so the test checks that only
`alembic_version` remains after downgrade. It does not prove complete schema equivalence for every
historical revision: if an older revision later contains tables, its expected columns, constraints,
indexes, defaults, and any important data transformations need revision-specific assertions.

### How migrated database tests work

The shared fixtures in `tests/integration/conftest.py` separate database creation from schema setup:

1. `temporary_database_url` creates a uniquely named empty PostgreSQL database.
2. `migrated_database_engine` points the test environment at that database and runs
   `alembic upgrade head`.
3. It yields a SQLAlchemy `Engine`, which is a connection factory and pool rather than a single
   long-lived connection.
4. Test helpers insert valid prerequisite rows, then tests attempt valid or invalid writes against
   the migrated schema.
5. Fixture teardown disposes the engine before the temporary database is dropped.

Pytest injects the fixture when a test declares a parameter named `migrated_database_engine`.
Function-scoped fixtures give every test case, including each parametrized case, an isolated
database. `test_migrations.py` instead requests `temporary_database_url` directly so it can begin
empty and control its own upgrade/downgrade sequence. These tests verify migration-created
PostgreSQL schema behavior at the properties they explicitly assert; a successful Alembic command
or matching `alembic_version` alone does not prove the restored schema is correct. ORM agreement,
API behavior, and production-data import are separate test boundaries.

### Complete multilingual fixture

`tests/fixtures/multilingual_learning_domain.sql` contains deterministic synthetic English and
Japanese records spanning every Issue #8 table. `test_multilingual_domain_fixture.py` loads it into
an isolated migrated database in one transaction and verifies shared ownership, tags, current state,
and before/after review history. It is intentionally not a production seed or Google Sheets import.

### Representative query plans

Run the Issue #8 and #9 planner evidence independently with:

```bash
RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest tests/integration/test_query_plans.py -q
```

The test loads deterministic representative-volume data, runs `ANALYZE`, then executes nine
named access patterns with `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`. It asserts that PostgreSQL 17
selects each deliberate index without forcing planner settings. It does not assert timings, costs,
buffer counts, or a complete plan shape and is not a production benchmark.

## API error contract

API failures use this stable envelope:

```json
{
  "error": {
    "code": "validation_failed",
    "message": "The request did not pass validation.",
    "retryable": false,
    "request_id": "00000000-0000-0000-0000-000000000000"
  }
}
```

Safe code-specific `details` may also be present. Clients branch on `code`, not `message`. Every
request receives a new UUID in `X-Request-ID`; error responses repeat it in the envelope. Validation
and unexpected-error handlers do not return rejected inputs, exception text, stack traces, SQL,
credentials, or connection details.

## Machine-only guest publication

The final API has no anonymous `/v1/public/review-cards` route. Guests read a static Pages
snapshot. `GET /v1/internal/guest-cards/export` is only for the dedicated publication identity.
It accepts no query filters or caller-selected deck/limit. Signature, issuer, expiry, dedicated
audience, exact service-account subject/email and verified email are checked before database
checkout. It never calls `current_user` or creates users. Browser OAuth remains unchanged.

Set `GUEST_EXPORT_DECK_ID`, `GUEST_EXPORT_AUDIENCE`, `GUEST_EXPORT_SUBJECT` and
`GUEST_EXPORT_EMAIL` together. All absent disables export; partial configuration rejects startup.
The audience must be HTTPS and differ from the browser client ID. The numeric service-account
subject and `.iam.gserviceaccount.com` email identify the dedicated export account.
`GUEST_EXPORT_QUERY_TIMEOUT_MS` defaults to 2000 and is bounded to 1..10000ms.

The response has exactly `schema_version=1`, timezone-aware `generated_at`, and `items` with
0..50 distinct active English cards. Missing/wrong-language decks fail; archived decks return
empty success. The explicit projection contains ID, language, term/meaning, pronunciation,
reading/romanization, part of speech/detail, target-language definition, example/translation,
synonyms and antonyms. It never fetches notes, tags, owner metadata or review state. A read-only
transaction, statement timeout and a nonblocking process-local permit bound queries. Concurrent
export gets retryable 503 with `Retry-After: 1`. Cancellation retains the permit until synchronous
query/session cleanup finishes. The encoded response is capped at 512 KiB, never truncated.
Database/identity errors remain sanitized; responses use `Cache-Control: no-store`.

The timeout covers each SQL statement, not pool acquisition or the whole request. The permit is
per process and is not a service-wide cost cap. Authentication rejects untrusted exports, but
HTTP traffic still reaches the service. This feature does not claim DDoS protection.

See [development setup](../../doc/development.md#manual-pages-setup-operational-prerequisites-not-yet-verified)
for independent manual export/PR and Pages Actions, protected WIF trust and settings. Pages can
publish the empty seed before backend changes. After static cutover and verification, deploy
this final protected-export backend, configure WIF, and manually export/review/publish real cards.
Supporting backend commit `34c7560` is optional when real cards are needed before first static
publication. It retains anonymous compatibility for the old frontend. Restore compatible backend
support before rolling back to that frontend.
Live IAM setup, real-card export and deployment are not established by local test results.

### GenAI consent

`GET /v1/me/genai-consent` returns `{"genai_consent_at": null}` until the authenticated
user grants consent through `PUT` at the same path. The response then contains a timezone-aware
ISO timestamp. Repeated grants retain that timestamp. No route accepts another user's ID.
`DELETE` clears consent and deletes all owned `card_embeddings`, including pending and failed
attempts across all model versions, in one transaction. Confirmed cards and review state remain.

Without consent, semantic search returns `403` with `error.code = genai_consent_required`,
and card-write background embedding work skips the provider while the card write succeeds.
The owner-bounded backfill also skips unconsented users, including in dry runs. Granting consent
does not automatically enqueue old cards; the existing explicit backfill can repair coverage.
Withdrawal cannot recall content already sent to a provider. A running document embedding result
cannot recreate a deleted claim after withdrawal, even if the user subsequently grants consent.

The inline consent prompt in `src/routes/search/+page.svelte` names card text and search queries
as content sent to Google Vertex AI. Semantic search is blocked until consent is granted.
Withdrawal requires a second inline confirmation and warns that it deletes existing embeddings
and cannot recall content already sent. A `403 genai_consent_required` returns the page to the
consent prompt.

Known limit: `process_card` checks consent in the claim transaction
([embeddings.py:179](app/embeddings.py#L179)); its shared user-row lock is released when that
transaction ends. The provider call runs outside any transaction
([embeddings.py:260](app/embeddings.py#L260)). Withdrawal between claim commit and provider call
start can therefore still send that one card's text to the provider. The final write recheck
([embeddings.py:268](app/embeddings.py#L268)) prevents storing the result. The maintainer accepted
this limit and rejected holding a database lock across a network call.

## Row level security and release order

Migration `20261105_0008` enables fail-closed RLS on 11 owner-bearing tables. Without a valid
transaction-local `app.user_id`, runtime reads return zero rows and writes are rejected or affect
zero rows. Explicit application ownership filters remain in place. `users` has no RLS because
sign-in must resolve the internal ID first.

Use `app.database.bind_owner(session, owner_id)` with a positive integer. Authentication calls it
after resolving `users`; it sets the active transaction and `Session.after_begin` reapplies
parameterized `set_config('app.user_id', :owner_id, true)` on each new transaction after commit or
rollback. Background embedding uses `database_transaction(factory, owner_id=...)` for both claim
and final write, preserving consent locks and the provider call outside transactions. Backfill
uses its explicit owner for each scan and processor transaction. Do not use session-level GUCs.

Only guest export uses `bind_public_deck`: its separate session first executes
`SET TRANSACTION READ ONLY`, then sets `app.public_deck_id` to the configured deck UUID, without
setting `app.user_id`. The public policies allow SELECT only on the selected deck/cards. App
sessions reject mixed identities. Local PostgreSQL reused-connection tests verify identity cleanup;
Neon pooled transaction mode and production pooled behavior remain unverified.

`FORCE ROW LEVEL SECURITY` is intentionally not used: table owners and superusers/BYPASSRLS roles
bypass policies for migrations/maintenance. Use a non-owner runtime role without these privileges.
Operator report (2026-11-05), not programmatically verified: runtime role is `app_runtime_limited`,
`rolsuper`/`rolbypassrls` are false, and all 11 table owners are `neondb_owner`.

The historical CSV tools `imports.py` and `confirmed_imports.py` are considered disabled under
runtime RLS. They intentionally do not bind an owner; the protected import tables deny access.
The earlier import instructions describe historical owner maintenance behavior, not supported
runtime usage. `import_items` has no owner column and remains a known RLS gap through its logical
parent `import_runs`. Their removal is separate work.

Release exception for 0008 (the existing workflows/scripts do not implement this exception):

1. First deploy the identity-binding code and verify all serving revisions support it, before
   enabling RLS. Do not follow the ordinary migrate-before-app order for this migration.
2. Then apply 0008 and verify all app paths with the restricted runtime role.
3. Before rolling back to older code, disable RLS on all 11 tables with
   `ALTER TABLE ... DISABLE ROW LEVEL SECURITY`, or explicitly downgrade 0008 with the migration
   role. Only then roll back the app. Application-only rollback would leave private queries empty.

CI's ordinary integration fixtures now use restricted runtime engines for HTTP, embedding,
backfill and guest export sessions by default; owner connections still seed/inspect data and
exercise retired import maintenance. No new environment switch or workflow edit is required.
See [verification](../../doc/issues/issue-75-verification.md) for exact checks and remaining limits.

## Stateless card extraction

`POST /v1/decks/{deck_id}/card-drafts/extract` accepts `material`, with optional paired
`drafts` (1-20 `CardFields` objects) and nonblank `instruction` for adjustments. Explicit null
adjustment fields are rejected. Client-supplied languages and unknown fields are rejected.
Deck ownership/archive and GenAI consent are checked before generation; languages come only
from the deck. This endpoint returns an editable `CardDrafts` envelope plus nullable `model`
and `usage` (input/output/total tokens). It never creates cards. Confirmation still uses existing
bulk create. The frontend hand-pasted JSON workflow is unchanged.

Server-only environment settings, validated at startup:

| Setting                            | Default | Allowed range                   | Purpose                                                 |
| ---------------------------------- | ------- | ------------------------------- | ------------------------------------------------------- |
| `GENERATION_MODEL`                 | unset   | model identifier, max 128 chars | Explicit maintainer-selected Vertex model               |
| `GENERATION_LOCATION`              | unset   | global or regional location     | Generation-only override; falls back to VERTEX_LOCATION |
| `GENERATION_TIMEOUT_SECONDS`       | 30      | 1-120                           | HTTP transport timeout                                  |
| `GENERATION_MAX_OUTPUT_TOKENS`     | 8192    | 1-32768                         | Bound generated output                                  |
| `GENERATION_MATERIAL_MAX_CHARS`    | 20000   | 1-100000                        | Unicode characters after trimming outer whitespace      |
| `GENERATION_INSTRUCTION_MAX_CHARS` | 2000    | 1-10000                         | Unicode characters after trimming outer whitespace      |

Reuse `VERTEX_PROJECT_ID`. `GENERATION_LOCATION` accepts `global` or the existing regional
format; when unset, generation uses `VERTEX_LOCATION` (default `us-central1`). Embedding continues
to use only regional `VERTEX_LOCATION`, whose validation/default and routing are unchanged.
Generation global routing uses host `aiplatform.googleapis.com` and path `locations/global`;
regional generation retains the region-prefixed host. This global format is prior knowledge,
**unverified against the live API**, and does not establish model availability in any location.
Missing model or project returns stable
503 `generation_not_configured` with no provider call or ADC lookup, after the access/consent
checks. Provider construction is lazy and app-scoped. Input limit failures return 413
`input_too_large`; request shape failures return 422. Timeout returns 504
`generation_provider_timeout`; quota, availability and authentication return 503 with respective
`generation_provider_rate_limited`, `generation_provider_unavailable`, `generation_provider_auth_error`.
Bad provider envelopes/truncation return 502 `generation_invalid_response`/
`generation_truncated_output`. Invalid generated JSON/card fields return 502
`extraction_invalid_output`. Provider messages are never returned and no generation is retried.

The route commits authentication/deck/consent checks before external processing, releasing the
connection and consent lock. Withdrawal or archive after that snapshot cannot recall transmitted
material; no final data write occurs. Each request emits a `card_extraction_completed` JSON event
with request ID, bounded deck UUID, adjustment flag, duration, optional token usage and result code,
including rejected requests. HTTP provider failures additionally log a safe numeric `http_status`
when available; it is never added to the public error envelope. `GenerationFailure` retains only
that bounded status (100-599), not the provider body, token or user text. HTTP 400/404 still return
502 `generation_invalid_response`; this diagnostic does not change retryability or API codes.
Events exclude material, instructions and card content.

The response schema is derived from `CardDrafts.model_json_schema()`, with references expanded,
nullable unions converted and unsupported conditionals/extra-property restrictions omitted from
the provider schema. Strict server validation enforces these rules again. The Vertex REST format,
response parsing and schema subset are **unverified against the real API**; handwritten fixtures
only establish the intended adapter contract. No model name or IAM configuration is asserted valid.
See [evaluation instructions](../../doc/training/issues/72/README.md) and
[verification evidence](../../doc/issues/issue-72-verification.md).

## Stateless readonly learning assistant

`POST /v1/assistant/messages` accepts `{ "messages": [{ "role": "user", "content": "What is due?" }] }`.
Only plain-text `user` and `assistant` messages are accepted; extra fields and `tool` roles
return 422. Authentication precedes validation, configured input limits precede consent,
and `require_genai_consent` precedes generation. Missing consent is 403
`genai_consent_required`; missing model/project is 503 `generation_not_configured`.
The endpoint reuses #72's `GENERATION_MODEL`, generation location and generation provider.
No model is configured by default. Nothing persists conversation or tool output.

The non-streaming response contains `reply`, `tool_calls` with validated arguments, status
and duration, `stop_reason` of `completed`, `max_steps` or `timeout`, and nullable summed
`usage`. Invalid arguments are omitted from summaries. Unknown names are shown as `unknown`
to avoid reflecting hostile names. Summaries contain no tool-result/card text. The answer
can discuss the owner's card content. There are exactly three readonly tools:
`search_cards` for English semantic retrieval, `get_due_cards` for an English/Japanese first
page, and `get_review_stats` for active/due counts with optional deck/language filters.
Owners come from the authenticated session, never model arguments. Search uses the existing
embedding provider and does not treat an embedding failure as a successful empty search.

| Server-only variable          | Default | Allowed range | Reason                                  |
| ----------------------------- | ------- | ------------- | --------------------------------------- |
| `ASSISTANT_MAX_STEPS`         | 3       | 1-3           | One model call per step, bounded loop   |
| `ASSISTANT_TIMEOUT_SECONDS`   | 60      | 1-120         | Bound the orchestration wait budget     |
| `ASSISTANT_MAX_OUTPUT_TOKENS` | 2048    | 1-8192        | Short answers with bounded output       |
| `ASSISTANT_MAX_MESSAGES`      | 20      | 1-100         | Short client-supplied history           |
| `ASSISTANT_MAX_CHARS`         | 12000   | 1-100000      | Total message characters, not bytes     |
| `ASSISTANT_MAX_TOOL_CALLS`    | 3       | 1-10          | Small batches; oversized batch rejected |
| `ASSISTANT_TOOL_LIMIT`        | 10      | 1-20          | Search/due limit clamped to 1..this cap |

Search/due default to five results, clamped by the configured cap even when it is below
five. Statistics has no `limit` argument; it returns two counts. Request models also enforce
absolute 100-message and 100000-character-per-message caps. Token limits go into every
provider call; reported output counts above the limit fail with non-retryable 502
`generation_truncated_output`. Missing provider usage stays null, never an invented count.

The final step retains declarations and sends `toolConfig.functionCallingConfig.mode=NONE`.
The server blocks any tool calls from the final step. When the provider returns no final text,
the response uses a fixed fallback with `max_steps`. Provider timeouts and late results return
the fixed fallback with `timeout`. Other safe #72 provider codes retain
502/503 classification. No provider retry occurs. Each model step emits one JSON
`assistant_step` with request ID, step, allowlisted tool names, bounded status, duration and
tokens, without message text, arguments, reasoning, card data or signatures.

Authentication, request validation and completion of the existing auth transaction precede
the assistant budget. One absolute deadline then covers initial/repeated consent, pool waits,
tool SQL and provider waits. A worker exclusively owns a separate session bound to the same
authenticated owner. Caller timeout never closes a session used by a worker. A late worker
checks the shared deadline before subsequent work and closes its own session. On the outer
watchdog timeout, partial summaries/usage are unavailable and the response has an empty
`tool_calls` list and null `usage`.

Generation and assistant query embedding run outside database transactions. Each readonly
tool transaction rebinds the existing RLS identity and rolls back on completion. Due and stats
share the due predicate and a request snapshot. PostgreSQL statement timeouts bound tool SQL.
Provider workers run without database sessions. Generation and assistant query embedding
check the shared deadline after credential acquisition and before sending content. The HTTP
timeout is capped at the remaining budget. In-flight requests may finish after the deadline.
The assistant discards their results. Streaming and Neon pooled `set_config` behavior remain
unverified. See [verification](../../doc/issues/issue-70-verification.md) and the
[provisional live evaluation](../../doc/training/issues/70/README.md#live-result-on-2026-11-07).

### Stream an assistant reply

Send the same JSON request to `POST /v1/assistant/messages/stream` with the usual
authentication header. A successful response is `text/event-stream`. Each event's
`data` field contains one JSON object.

| Event   | Data                                                                       |
| ------- | -------------------------------------------------------------------------- |
| `delta` | `text` contains the next fragment of the reply. Append fragments in order. |
| `done`  | `tool_calls`, `stop_reason`, and nullable `usage`.                         |
| `error` | Stable `code`, `message`, and `retryable` fields.                          |

Authentication, validation, consent and model configuration errors are HTTP
responses before any SSE frames. A preflight deadline failure returns HTTP 504.
Once streaming starts, expect one `done` or `error` event while the connection is
open. A deadline reached after headers returns `done` with `stop_reason: "timeout"`.
Keep text already received. Close the request to stop reading. The server closes
the active upstream stream on disconnect and stops dispatching additional work.
If the client stops reading, the server closes the upstream stream at the deadline
and attempts to deliver the timeout event within a short grace period.

The SSE path reserves one model call for the tool-disabled reply. It streams
visible text directly from Vertex and can use an extra model call for simple
questions. The same overall call limit and deadline cover planning, tools and
streaming. Planning and tool execution finish before the first answer delta.
See the [SSE verification record](../../doc/issues/issue-70-verification.md#sse-follow-up).
