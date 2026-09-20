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

### Operator-reported isolated Neon branch rehearsal

On `issue-39-embedding-migration`, the operator reported a direct `neondb_owner` connection
with revision `20260910_0005` and 597 cards / 597 review states before migration. The operator
then reported that the `upgrade head` / `downgrade -1` / `upgrade head` cycle succeeded. After
the final upgrade, read-only SQL returned `vector(512)`, 0 embedding rows, 597 cards, 0 populated
semantic hashes, and 597 review states. The operator reported `true` for each separate
`app_runtime_limited` privilege check: SELECT, INSERT, and UPDATE on `card_embeddings`, plus
UPDATE on `learning_cards.semantic_content_hash`. The operator also reported that
`alembic current --check-heads` returned `20260920_0006` after the final upgrade. No real
provider call or private-card backfill was reported in this step.
The operator then reported an owner-bounded dry run over the isolated branch:
100 eligible cards on the first page and 497 on the resumed page, with a null final cursor
and no time-limit hit. This covers the reported 597-card corpus without provider calls or
embedding writes. No card IDs or connection details are retained in this record.
The operator subsequently reran the read-only preflight using the same backfill configuration
and reported `app_runtime_limited`, revision `20260920_0006`, and unchanged 597 card / 597 review
state counts. This establishes the reported dry-run connection role, without retaining its URL.
The operator reported that the deployed Cloud Run service uses
`english-learning-api@eng-learning-470909.iam.gserviceaccount.com`. A read-only project IAM
query returned no project-level bindings for that service account, including no
`roles/aiplatform.user`. Inherited or resource-level grants were not checked; a synthetic
prediction as that identity remains unverified. No IAM change was made by Codex.
The operator then granted `roles/aiplatform.user` to that service account in Google Cloud
Console and reported a read-only project IAM query showing the role bound to the expected
service-account principal. This verifies the reported policy binding, not an actual Vertex
request from the Cloud Run identity. Codex did not change IAM.

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
                           'SELECT') AS runtime_embedding_select,
       has_table_privilege('app_runtime_limited', 'public.card_embeddings',
                           'INSERT') AS runtime_embedding_insert,
       has_table_privilege('app_runtime_limited', 'public.card_embeddings',
                           'UPDATE') AS runtime_embedding_update;
SELECT has_column_privilege('app_runtime_limited', 'public.learning_cards',
                            'semantic_content_hash', 'UPDATE') AS runtime_hash_update;
```

### Isolated Neon branch migration rehearsal

Run these commands locally from `apps/api/` with the **direct** (non-pooler) connection string
for `issue-39-embedding-migration`, using the migration role. Do not use the production URL.
Enter the URL through a silent prompt so it is not saved as a shell command:

```zsh
cd apps/api
read -rs "ISSUE39_DATABASE_URL?Paste direct issue-39 migration URL: "
echo
export DATABASE_URL="$ISSUE39_DATABASE_URL"
export APP_ENV=local
```

Alternatively, set `DATABASE_URL` and `APP_ENV=local` in the Git-ignored `apps/api/.env`
and run the commands from `apps/api/`. Shell environment variables take precedence over
`.env`, so unset any previously exported `DATABASE_URL`/`APP_ENV` before using the file.
Keep this file local and remove the branch URL after the rehearsal.

Use a `postgresql+psycopg://` URL with `sslmode=require&channel_binding=require`. Before any
write, compare the endpoint host with the branch's direct host in Neon Console and check the
current role/revision without printing the URL:

```zsh
uv run python - <<'PY'
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from app.config import load_settings

url = make_url(load_settings().database_url.get_secret_value())
assert url.drivername == "postgresql+psycopg"
assert "-pooler" not in (url.host or "")
assert url.query.get("sslmode") == "require"
assert url.query.get("channel_binding") == "require"
print("host:", url.host)
with create_engine(url).connect() as connection:
    print("identity/revision:", connection.execute(text(
        "SELECT current_user, current_database(), version_num FROM alembic_version"
    )).one())
    print("card/review counts:", connection.execute(text(
        "SELECT (SELECT count(*) FROM learning_cards), "
        "(SELECT count(*) FROM review_states)"
    )).one())
PY
```

Stop if the host does not match the isolated branch, the role is not the intended migration
role, or the revision is not `20260910_0005`. Record the two counts. The following commands
change schema **only on the database selected by `DATABASE_URL`**:

```zsh
uv run alembic upgrade head
uv run alembic current --check-heads
uv run alembic downgrade -1
uv run alembic current
uv run alembic upgrade head
uv run alembic current --check-heads
```

After the final upgrade, use Neon SQL Editor on the isolated branch to run the read-only SQL
above, plus this schema/data check:

```sql
SELECT format_type(a.atttypid, a.atttypmod) AS embedding_type
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
WHERE c.relname = 'card_embeddings' AND a.attname = 'embedding';
SELECT count(*) AS embedding_rows FROM card_embeddings;
SELECT count(*) AS cards, count(*) FILTER (WHERE semantic_content_hash IS NOT NULL)
       AS cards_with_hash FROM learning_cards;
SELECT count(*) AS review_states FROM review_states;
```

The vector type should be `vector(512)`, the embedding table should initially be empty,
and card/review counts should match the pre-migration values. Existing cards may retain null
semantic hashes until explicit backfill. Finally, remove the URL from the shell:

```zsh
unset DATABASE_URL ISSUE39_DATABASE_URL APP_ENV
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
