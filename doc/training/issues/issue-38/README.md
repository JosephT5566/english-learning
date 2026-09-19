# Issue #38 - owner-safe semantic vocabulary retrieval design

Status: design and synthetic provider evaluation recorded; final-schema and deployment checks pending. 2026-09-19.
This designs retrieval only. Issues #39 and #40 implement storage and search; #41 measures
relevance and latency. The older Sheets/Cloudflare/R2 proposal is superseded.

## Invariants and trust boundaries

- Only server-verified Google identity supplies `owner_id`. Never accept an owner ID, vector,
  model name, or embedding status from the browser. A card and its deck must both belong to
  that owner and be active when returned.
- Confirmed cards remain authoritative. A provider call cannot hold open or roll back a card
  write transaction. Embeddings are untrusted, rebuildable derived data. Never send owner IDs,
  review history, credentials, or private logs to the embedding provider.
- Search queries and card text can contain hostile instructions; treat them as data. The provider
  returns numbers only, not authority to choose rows. Validate dimension, finite numbers, and
  nonzero norm before persistence or search.

## Corpus, provider, and schema choice

Use a separate `card_embeddings` table. An optional vector column on `learning_cards` would
couple its version/write path to provider failures and make a model rebuild harder to roll back.
Store `(card_id, owner_id, model_version)` as the key, a composite FK
`(card_id, owner_id) -> learning_cards(id, owner_id)`, `content_hash`, nullable
`embedding vector(512)`, `state` (`pending`, `ready`, `retryable`, `exhausted`), `embedded_at`,
and bounded `attempt_count`, `last_attempt_at`, `next_retry_at`, `last_error_code`.
The FK prevents attaching a vector to another owner's card. Require 512 dimensions and
finite, nonzero values at the application boundary. Runtime role gets only needed DML; migration
role owns DDL. Missing row or null vector means unindexed; a row whose hash differs from the current canonical
hash or whose model version is inactive is stale. Search joins only the active model and matching
hash; it must never serve an old vector for edited text. Keep old model rows during a staged
rebuild, switch the active version only after coverage/quality checks, and roll back by restoring
the old active version if its hashes still match. If not, re-embed; never silently use stale data.

Choose Google Cloud Vertex AI `gemini-embedding-001` at `outputDimensionality=512` for
the #39 implementation design, with model version
`vertex-ai/gemini-embedding-001/512/retrieval-v1/canonical-v1`. Use
`RETRIEVAL_DOCUMENT` for confirmed card text and `RETRIEVAL_QUERY` for search text;
the task pairing is part of the version contract. The model supports English and
multilingual retrieval, though this milestone searches English cards with English queries.
Japanese/cross-language retrieval requires its own labeled set. The smaller vector limits
Neon storage and comparison work. The existing Cloud Run service identity can use IAM
instead of a separate API key, after explicitly granting it the needed Vertex AI role.
Do not send private cards until the service identity, request path, and data handling
decision are verified for deployment.

OpenAI `text-embedding-3-small` at 512 dimensions remains a credible alternative:
published input price is $0.02 per 1M tokens, compared with Google's $0.15 per 1M
tokens online. OpenAI would require a separate server-side API key and its quality and
latency were not measured here. Google's operator-run synthetic relevance result passed
the proposed gate, and its IAM integration avoids a new API key; at this low volume that
is a reasonable reason to choose it despite the higher token price. This is an inference
from the reported test and deployment constraints, not a general model ranking. Google
states managed Vertex AI customer data is not used for model training without prior
permission, while some prompt logging for abuse monitoring may occur. The card text and
search query still leave Cloud Run for the provider.

The operator enabled the Agent Platform API and manually sent one synthetic
`RETRIEVAL_DOCUMENT` request to `gemini-embedding-001` with `outputDimensionality=512`.
The operator-reported response contained 512 finite, nonzero values, `token_count=10`, and
`truncated=false`. A subsequent synthetic `RETRIEVAL_QUERY` request also returned 512
finite nonzero values, `token_count=5`, and `truncated=false`. These check one response for
each task type; relevance, Cloud Run latency, and actual billing are not measured.
The operator then ran the full synthetic fixture through `evaluate_vertex.py` and reported
7/7 queries with nDCG@5 = 1.0 and grade-2 Recall@5 = 1.0; 17 requests reported 314 input
tokens. Cloud Shell-to-Vertex per-request latency was p50 1200.7 ms and p95 1296.3 ms.
At the published rate, 314 input tokens would imply about $0.000047 in model input charges;
actual billing was not inspected. These seven simple synthetic queries are a narrow quality
signal and do not establish relevance on private cards, robustness to ambiguity, or Cloud Run
end-to-end latency. No OpenAI comparison run was performed.

Canonical text v1: UTF-8 NFC, trimmed fields, fixed labels/order and newline separators:
`language`, `term`, `meaning`, `part_of_speech`, `part_of_speech_detail`, `reading`,
`pronunciation`, `romanization`, `target_language_definition`, `example_sentence`,
`example_translation`, `synonyms`, `antonyms`. Omit absent fields; preserve synonym/antonym
order and serialize each as an individually labeled line. Hash SHA-256 over the exact UTF-8
bytes prefixed by `canonical-v1\n`; keep model version in its own key column. A change to any included field or
deck target language requires a new vector. Current deck language is immutable, but future
migrations must honor this rule. Edits to `example_source`, `note`, `supplementary_note`,
`learned_on`, tags, deck title, review state, archive state, versions, IDs, ownership, and
timestamps do not re-embed. These exclusions minimize provider disclosure. Archive state is
enforced at query time, so archived cards/decks disappear immediately without provider calls.

## Lifecycle and failure recovery

After a successful create/edit commit, attempt one bounded provider call outside the transaction,
then conditionally upsert the vector only if `(card_id, owner_id, canonical hash)` still matches
the confirmed row. An optimistic edit can overtake an earlier call; the conditional upsert must
discard that result. A provider timeout, rate limit, malformed vector, or database failure after
the card commit leaves the card confirmed and the vector missing/stale. Do not retry inside the
user request. A short call timeout and clear `indexing_pending` response flag are preferable to
blocking card usability. Idempotent create replay must not duplicate provider calls when a
current vector exists. Existing confirmed CSV import creates cards in one transaction: never
call the provider inside it; include imported active cards in backfill afterward. Later AI draft
confirmation enters this same confirmed-card path; drafts are never embedded as cards.

Provide an operator-run, owner-bounded backfill/rebuild command: keyset page up to 100 confirmed
cards, select missing/stale active-model rows, at most 3 attempts per item with exponential waits
of 1, 4, and 16 minutes plus jitter, then stop and report safe error codes/counts. Cap one run at
500 cards and 30 minutes, resume by cursor; a later explicit run can revisit exhausted rows.
Avoid raw card text in logs. Do not add a queue or cache. On a model change, fill new-version
rows alongside old rows, measure coverage and relevance, switch a server config version, then
retire old rows after the rollback window.

## API and exact SQL shape

`POST /v1/cards/semantic-search` with `{query, target_language: "en", deck_id?, limit?}`.
Trim/NFC query, require 2-500 characters; default limit 10, hard cap 20. One validated query
embedding uses the same model/dimension. Return owned card summaries, `distance` (pgvector cosine
distance, lower is better), `score = 1 - distance` (cosine similarity, higher is better), and
`index_status: complete|partial|empty` based on owned eligible card coverage. No relevance
threshold claim. A provider failure returns a retryable 503 with safe code; database failure uses
the existing safe error envelope. Zero eligible or zero current vectors returns 200 with `[]` and
`empty`; partial indexing can return fewer than K. Never fall back to global vectors.

Use parameterized SQL and compute current hashes in the application/backfill or persist a
transactionally maintained canonical hash on confirmed cards; the latter is required for the
following query to reject stale rows without provider calls. The ownership and eligibility
predicates are inside the ranked relation, before `ORDER BY` and `LIMIT`:

```sql
SELECT c.id, c.deck_id, c.term, c.meaning,
       (e.embedding <=> CAST(:query_vector AS vector(512))) AS distance
FROM learning_cards AS c
JOIN learning_decks AS d
  ON d.id = c.deck_id AND d.owner_id = c.owner_id
JOIN card_embeddings AS e
  ON e.card_id = c.id AND e.owner_id = c.owner_id
WHERE c.owner_id = :authenticated_owner_id
  AND d.owner_id = :authenticated_owner_id
  AND c.archived_at IS NULL AND d.archived_at IS NULL
  AND d.target_language = :target_language
  AND (:deck_id IS NULL OR c.deck_id = :deck_id)
  AND e.model_version = :active_model_version
  AND e.state = 'ready' AND e.embedding IS NOT NULL
  AND e.content_hash = c.semantic_content_hash
ORDER BY e.embedding <=> CAST(:query_vector AS vector(512)), c.id
LIMIT :bounded_limit;
```

Resolve a supplied deck by ID plus owner first; cross-owner and missing deck are both 404,
archived deck is excluded. `target_language` is fixed to English for v1. Exact predicates such
as due time, counts, owner, deck, language, card IDs, review history, and archived status route
to existing SQL reads. Natural-language meaning queries route here. A future feature combining
e.g. one owned deck and conceptual ranking uses the SQL predicates above before vector distance;
do not embed structured filters into the query text as a substitute for authorization.

## Evaluation set and gate

Use `relevance.json`: synthetic cards, query labels, and graded relevance (2 strong,
1 related, 0 irrelevant). No private cards or model results are committed. Run the candidate
and the deterministic term/meaning word-overlap baseline, score nDCG@5 per query and macro
average; also record Recall@5 for grade-2 cards, per-query failures, token usage, and p50/p95
provider/search latency. Count missing vectors separately from retrieval misses. A rollout gate
is macro nDCG@5 >= 0.75 on the sanitized set and no owner/archived leakage in deterministic
integration tests. The operator-reported Vertex AI result clears the synthetic relevance part;
authorization tests remain Issue #40 work. Revisit the gate with
real opt-in feedback rather than treating synthetic labels as production quality.

`evaluate.py` is the offline scorer. Run `python3 evaluate.py relevance.json --baseline`
from this directory, or pass `--rankings rankings.json` where each query has an ordered
`card_ids` list. It rejects unknown or duplicate IDs and requires all seven labeled queries.
The local word-overlap baseline scored macro nDCG@5 = 0.5655 and strong Recall@5 = 0.6429
on this synthetic set (2026-09-19); this is not a provider or production result.

`evaluate_vertex.py` is an explicitly invoked provider evaluation runner. It verifies the
checked-in synthetic fixture's SHA-256, obtains a short-lived user access token from the
local `gcloud` CLI, sends exactly 10 `RETRIEVAL_DOCUMENT` and 7 `RETRIEVAL_QUERY` requests
to `gemini-embedding-001` at 512 dimensions, validates each response, and prints only
aggregate quality, token counts, and per-request latency summaries. It sends no private
card data and makes no requests when imported or tested. The operator must choose the
project and run `python3 evaluate_vertex.py --project PROJECT_ID` from this directory.
The reported latency measures the operator's machine or Cloud Shell to Vertex AI, not
Cloud Run to Vertex AI or database ranking. The operator-reported result is above;
the vectors and raw provider responses were not committed.

## Evidence and deployment gates

Repository inspection: `learning_cards` has composite deck ownership, active-card index,
optimistic edit/archive, and a separate transactional confirmed-import path. Existing local
plans in Issue #8/#9 used 40,000 synthetic cards but did **not** plan vector ranking. This
environment has no `psql`, Docker, configured database URL, or provider key. The operator
reported a Neon SQL Editor read on 2026-09-19: PostgreSQL 18.6, 597 cards (597 active), and
2 decks. The SQL Editor role was `neondb_owner`. On an isolated test branch, the operator
reported `CREATE EXTENSION IF NOT EXISTS vector` succeeded and `pg_extension` returned
`vector` version 0.8.6. These are operator-reported observations, not independently captured
connection or branch evidence. Issue #26's deployment documentation names `neondb_owner`
as the current migration database role, so the branch check verifies the documented role's
extension privilege. The live Cloud Run migration secret's current URL/role was not independently
read back. The final three-table vector `EXPLAIN`, Cloud Run latency distribution, and
real-card relevance remain **unverified**.

The operator then reported privilege results on the test branch:
`app_runtime_limited` had `CREATE` on neither `neondb` nor `public`, while `neondb_owner`
had both. This supports the intended runtime/migration separation on that branch. The
operator expects the Cloud Run migration job's secret to continue using `neondb_owner`,
but its current value was not independently inspected; no secret value was shared.

The operator subsequently supplied `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` for the
597-row synthetic `issue38_vector_probe` table on the test branch. PostgreSQL chose
`Bitmap Index Scan` on `issue38_vector_probe_owner_filter`, then `Bitmap Heap Scan`
(90 matching rows), `top-N heapsort` (25 kB), and `Limit` (10 rows). Planning time was
0.263 ms and execution time 0.434 ms; the scan used 278 shared buffer hits and one read
at the top level. No HNSW index existed in this probe. This operator-supplied single-run
plan supports exact filtered ranking at this small synthetic size; it is not the final
three-table search plan, p95 latency, or a production benchmark. Repeat with the final
schema and representative owner distribution after #39 before changing the index decision.

Do not deploy #39 until the remaining role and provider prerequisites pass. The initial
disposable-branch SQL checklist is:

```sql
SELECT current_user, has_database_privilege(current_user, current_database(), 'CREATE');
SELECT name, default_version, installed_version FROM pg_available_extensions WHERE name = 'vector';
SELECT count(*) AS cards, count(*) FILTER (WHERE archived_at IS NULL) AS active_cards FROM learning_cards;
SELECT count(*) AS decks FROM learning_decks;
BEGIN;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TEMP TABLE semantic_probe (id int, embedding vector(512));
INSERT INTO semantic_probe VALUES (1, ('[' || trim(trailing ',' FROM repeat('0.1,', 512)) || ']')::vector);
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT id FROM semantic_probe ORDER BY embedding <=> ('[' || trim(trailing ',' FROM repeat('0.1,', 512)) || ']')::vector LIMIT 5;
ROLLBACK;
```

For the actual candidate, load synthetic owned/archived rows in a disposable branch, `ANALYZE`,
then `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` the exact final query with representative owners,
deck filters, and K values. Confirm migration role can create the extension/table while runtime
role cannot change schema. Probe provider with synthetic text and verify model ID, 512 finite
values, usage, timeout/error shape, and regional latency. Retain only aggregate plans and counts.
Start with exact filtered scan. HNSW is deferred until observed owner-filtered cardinality and
p95 database latency justify it; pgvector's approximate index can lose filtered recall, so any
later index needs a separate owner-filtered recall comparison.

Sources checked 2026-09-19: [OpenAI model/pricing](https://developers.openai.com/api/docs/models/text-embedding-3-small),
[embeddings API dimensions](https://developers.openai.com/api/reference/ruby/resources/embeddings/methods/create),
[OpenAI data controls](https://platform.openai.com/docs/models/default-usage-policies-by-endpoint),
[Neon pgvector](https://neon.com/blog/optimizing-vector-search-performance-with-pgvector),
[pgvector exact/approximate filtering](https://github.com/pgvector/pgvector).
Google comparison sources: [Vertex AI embedding models](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/embeddings/get-text-embeddings),
[retrieval task types](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/embeddings/task-types),
[Google embedding pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing),
[Google data handling](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/vertex-ai-zero-data-retention).

Five-minute explanation: verify the user, embed their meaning query, rank only their active
English cards whose stored vector still matches confirmed text, and return Top-K. Card writes
commit independently. If embedding fails, the card remains usable and the bounded backfill can
repair search coverage.
