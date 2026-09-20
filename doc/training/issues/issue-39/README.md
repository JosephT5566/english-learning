# Issue #39 - retryable confirmed-card embeddings

Status: repository implementation and local verification passed on 2026-09-20; no production migration,
provider permission change, or private-card embedding has been performed by Codex.

## Boundary

- Canonical text v1 is defined in `apps/api/app/semantic_text.py`. The exact text is NFC-normalized,
  trimmed, fixed-order labeled lines; the SHA-256 hash includes the `canonical-v1` prefix. The
  active model key is `vertex-ai/gemini-embedding-001/512/retrieval-v1/canonical-v1`.
- Migration `20260920_0006` installs pgvector if available, adds a nullable card semantic hash
  for pre-existing rows, and creates a separate owned/versioned `card_embeddings` table with a
  `vector(512)` column. The migration performs no provider calls or card-content backfill.
- Card create and edit update the semantic hash within the card transaction. The confirmed card
  commits before one bounded provider call. Review-only and unchanged semantic edits do not call
  the provider. Confirmed CSV import also writes the hash in its existing atomic transaction and
  leaves embedding to explicit backfill.
- The provider result is accepted only for the same owner, current canonical hash, model key, and
  claim token. It cannot overwrite a later attempt or a changed card. Archive and deck archive
  suppress new embedding work. Future retrieval must filter both archive flags, owner, model,
  `ready` state, and matching hash before ranking.
- The operator CLI scans one owner by UUID keyset, pages by at most 100, caps one run at 500 cards
  and 30 minutes, and prints safe outcome counts and a resume cursor. Retry delays are 1, 4, and
  16 minutes with bounded jitter. At three failed attempts a row is exhausted until an explicit
  `--retry-exhausted` run. A stranded `pending` claim becomes eligible after two minutes.

## Local verification

`RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest tests -q --tb=short` passed 285 tests with
one existing Starlette `TestClient` deprecation warning. The suite includes the Alembic clean
upgrade, downgrade to baseline/base, and re-upgrade cycle against disposable local PostgreSQL
with pgvector installed. `uv run ruff check .`, `uv run ruff format --check .`,
`uv lock --check`, and `git diff --check` passed. The sanitized rehearsal used a disposable
PostgreSQL database and a fake provider: one run reported `provider_timeout: 1`, a later due
retry reported `ready: 1`, and the card remained confirmed. No card text or vector entered the
report. The candidate workflow YAML parsed with Ruby's standard YAML reader. No real provider
call or private-card backfill was made.

The new PostgreSQL tests cover failed provider calls, repair, stale results, concurrent old/new
calls, owner/archive rejection, cursor resume, and the Alembic upgrade/downgrade cycle. Unit tests
cover canonical normalization, vector validation, and synthetic Vertex request/error contracts.

## Operator-controlled deployment gates

Codex has not run gcloud or Neon commands. Before a production migration or provider enablement,
the operator must verify on a disposable Neon branch:

1. The migration connection really uses the intended DDL role; it can create the `vector`
   extension and table. The runtime role lacks database/schema CREATE, but has SELECT/INSERT/UPDATE
   on the new table and UPDATE on `learning_cards.semantic_content_hash`. Check actual grants after
   migration, including the migration owner's default privileges.
2. The Cloud Run service identity has the intended Vertex AI prediction permission in the chosen
   project/location. Test only synthetic text first, checking model ID, 512 finite nonzero values,
   no truncation, safe timeout/error mapping, and observed regional latency.
3. Confirm that sending private card text to Vertex is approved under the #38 data-handling
   decision. Set the protected deployment variables `VERTEX_PROJECT_ID` and optionally
   `VERTEX_LOCATION` only after this gate; until then candidate deployments omit both and make
   no runtime provider calls.
4. Run the migration workflow and candidate checks through the existing protected release path.
   On a disposable branch, rehearse `upgrade head`, `downgrade -1`, and `upgrade head`, then run
   a sanitized backfill dry run and a bounded provider retry. The production release must not run
   an automatic provider backfill during migration.

Useful read-only SQL on the isolated branch (no secret values):

```sql
SELECT current_user,
       has_database_privilege(current_user, current_database(), 'CREATE') AS can_create_database,
       has_schema_privilege(current_user, 'public', 'CREATE') AS can_create_public;
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
SELECT has_table_privilege('app_runtime_limited', 'public.card_embeddings',
                           'SELECT,INSERT,UPDATE') AS runtime_embedding_dml;
SELECT has_column_privilege('app_runtime_limited', 'public.learning_cards',
                            'semantic_content_hash', 'UPDATE') AS runtime_hash_update;
```

## Five-minute explanation

The confirmed card is the source of truth; its semantic hash is committed with its content.
An embedding is a rebuildable projection. The API attempts one document embedding only after
that commit, so a Vertex timeout cannot undo a card or create another review state. The separate
table tracks model version, hash, attempts, retry timing, and a claim token. Before storing a
vector, the worker locks the card and checks that its current canonical hash still equals the
hash used in the provider request. The claim token rejects a result from an earlier attempt,
including one that raced with an edit and later retry. Imported or previously confirmed cards
are scanned with an owner-bounded keyset command; interrupted scans resume from a cursor, while
retry delays and exhausted rows require a later explicit pass. Search in #40 must apply owner,
archive, active model, ready state, and matching-hash filters before distance ranking. The vector
is useful for retrieval but never grants authority over card identity or confirmed content.
