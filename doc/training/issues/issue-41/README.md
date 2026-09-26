# Issue #41 - retrieval quality, cost, and failure evaluation

Status: complete with an **iterate** decision. Search remains useful and limited; grounded-tutor
work is not approved until retrieval adds an evidence-backed no-answer boundary and addresses the
observed ambiguous-sense failure. Updated 2026-09-27.

This issue evaluates the semantic retrieval MVP implemented through Issues #38-#40. It does not
add LLM generation, change the confirmed-card lifecycle, or authorize a grounded tutor.

## Question and decision boundary

Decide whether owner-safe English semantic retrieval is useful and reliable enough to:

- **go**: retain it as a candidate retrieval boundary for the later grounded-tutor design;
- **iterate**: keep the search feature limited while changing the canonical text, labels, or model
  and rerunning this same evaluation; or
- **stop**: avoid extending semantic retrieval because it does not add enough value over lexical
  search or has an unacceptable safety/reliability boundary.

Issue #40 is complete and supplies the authenticated API and static Svelte flow. Issue #38 supplies
the frozen `synthetic-en-v1` fixture: 10 synthetic cards, seven labeled queries, grades 2 (strong),
1 (related), and 0 (unlabeled/irrelevant). No private production learning content is committed.

## Frozen metrics and gate

These rules are recorded before inspecting the final Issue #41 results:

- `K = 5`.
- Primary relevance metric: macro nDCG@5 with gain `2^grade - 1`.
- Primary relevance gate: macro nDCG@5 >= 0.75 on the sanitized labeled set.
- Safety gate: deterministic PostgreSQL tests show zero cross-owner or archived-card/deck results.
- Supporting measures, not post-hoc gates: grade-2 Recall@5, hit@5 (at least one grade-2 result),
  eligible/indexed coverage, per-query results, and comparison with the deterministic lexical
  baseline and exact/substring search where the query makes those comparisons meaningful.
- A missing or stale embedding is a coverage failure, not a retrieval miss. A provider error is an
  availability failure and must not be reported as an empty successful search.

Passing the numeric gate alone is not a `go`. A `go` also requires the deterministic safety gate,
documented failure behavior, and observed workload/latency/cost evidence with its limitations.

The existing fixture has already been used for the narrow Issue #38 model check. It remains a
frozen regression set, not an unbiased estimate of user quality. Before adding a broader final set,
write its cards, paraphrase/ambiguous queries, relevance labels, metric, and fixture hash first;
then review and freeze them before running the provider. Never tune labels after seeing rankings.

## Evaluation layers

### 1. Deterministic correctness

Use fixed fake vectors and real PostgreSQL/pgvector. These tests belong in CI and prove system
behavior rather than provider quality:

- cosine ordering and stable UUID tie-breaking;
- authenticated owner and optional owned-deck filtering before Top-K;
- active English card/deck filtering;
- missing, non-ready, stale-hash, and inactive-model vectors are excluded;
- empty and partial coverage are reported honestly;
- invalid auth/body makes no provider call;
- provider outage returns a retryable safe 503 rather than an empty result.

### 2. Provider relevance

Run explicitly, outside deterministic CI. Vertex results and latency can vary. The runner sends
only the checked-in synthetic fixture, verifies its SHA-256, makes 10 `RETRIEVAL_DOCUMENT` and
seven `RETRIEVAL_QUERY` calls, and prints aggregate metrics, request count, token count, and latency
summaries without printing access tokens or vectors.

### 3. Deployed workload and database plan

Measure the actual small corpus without claiming production scale. Record date, API revision or
stable URL, regions, corpus size, query count, warm-up policy, repetitions, provider-call count,
coverage, end-to-end latency samples or distribution, reported tokens, price source/date, estimated
cost, whether billing was inspected, PostgreSQL plan, and limitations such as cold starts and
network variance. Keep query/card text, card IDs, owner IDs, tokens, and database URLs out of the
committed artifact.

## Operator runbook

Run commands from the repository root unless a step says otherwise. Save only sanitized aggregate
output. Do not paste credentials, bearer tokens, database URLs, query text from private cards, raw
response bodies, card IDs, owner IDs, or vectors into the issue artifact.

### A. Record the frozen fixture hash and lexical baseline

```bash
shasum -a 256 doc/training/issues/issue-38/relevance.json
python3 doc/training/issues/issue-38/evaluate.py \
  doc/training/issues/issue-38/relevance.json --baseline
```

Expected frozen SHA-256:
`a1d6e3e9a76a2705dd5fc2a869339debf46c32217a22fef35d2a7e6d632811dd`.
The historical lexical baseline is macro nDCG@5 `0.5655` and macro grade-2 Recall@5 `0.6429`;
record the actual rerun rather than copying those values as a new result.

### B. Run deterministic tests

Start the disposable PostgreSQL service, then run the focused unit and integration tests:

```bash
docker compose up -d --wait postgres
cd apps/api
uv sync --locked
uv run pytest tests/unit/test_issue_38_evaluation.py \
  tests/unit/test_issue_38_vertex_evaluation.py \
  tests/unit/test_embedding_provider.py \
  tests/unit/test_semantic_text.py \
  tests/unit/test_semantic_smoke_validator.py -q
RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest \
  tests/integration/test_card_embeddings.py \
  tests/integration/test_semantic_search.py -q --tb=short
uv run ruff check .
uv run ruff format --check .
```

The integration fixtures always create isolated databases from the checked-in disposable localhost
URL. Do not run an unqualified `alembic` command for this evaluation: a developer `apps/api/.env`
may point `DATABASE_URL` at Neon. If you separately need to migrate the disposable main database,
set the complete localhost `DATABASE_URL` explicitly in that one command and verify its host first.

Stop the disposable service from the repository root when it is no longer needed:

```bash
docker compose stop postgres
```

The focused semantic-search integration suite currently establishes owner, language, deck,
archive, missing-vector, stale-model, ordering, no-provider-call, and provider-timeout behavior.
If the complete Issue #41 failure matrix exposes a missing deterministic case, add that test before
closing the issue.

### C. Explicitly run the synthetic Vertex evaluation

This incurs exactly 17 provider requests. Confirm that the selected project is non-secret and that
the effective `gcloud` identity is authorized before running:

```bash
gcloud auth list
gcloud config get-value project
cd doc/training/issues/issue-38
python3 evaluate_vertex.py --project YOUR_GCP_PROJECT_ID --location us-central1
```

Record the sanitized JSON output and whether actual billing was inspected. The script's latency is
operator-machine-to-Vertex latency, not Cloud Run end-to-end or PostgreSQL latency.

### D. Inspect production coverage and a content-safe ranking plan

Run [`production-inspection.sql`](production-inspection.sql) using Neon SQL Editor or another
read-only production session. The script performs only `SELECT` and `EXPLAIN (ANALYZE, BUFFERS)`.
It does not return card text, IDs, owner IDs, hashes, or vector values. Capture its aggregate rows
and plan, plus the database/region and whether this was a cold or warm run.

The file includes a stored-document-vector diagnostic and a preferred API-shaped latency probe that
uses a deterministic synthetic 512-dimensional constant. Both are content-safe and exclude provider
latency. Use the final synthetic-constant plan for timing because the stored-vector CTE has a
different detoasting/materialization shape from the API's bound query-vector parameter.

### E. Deployed API workload

Use only sanitized or explicitly consenting owned cards. The checked-in
[`deployed-queries-v2.json`](deployed-queries-v2.json) freezes 10 corpus-grounded sanitized queries:
two paraphrases, two exact terms, two ambiguous terms, two natural sentences, one
no-confident-match query, and one near-synonym query. Its SHA-256 is
`4756caf33424266c5722b344124a5d226427fc065dece6e02c8746fd7e86a5a4`. It targets eight consenting
active-card terms supplied by the operator: communism, severance, brat, hotshot, fragrance,
diligently, endangered, and obtain. The runner now selects v2 by default. The original
[`deployed-queries.json`](deployed-queries.json) and its hash are retained as the invalid
synthetic-to-owned-corpus attempt documented below.

Before any v2 provider call, run [`expected-concept-check-v2.sql`](expected-concept-check-v2.sql)
in Neon. Every one of the eight aggregate exact-term counts must be greater than zero. Stop if any
count is zero; do not reinterpret or tune the fixture after viewing rankings.

Inspect the complete plan without making a request:

```bash
python3 doc/training/issues/issue-41/run_deployed_evaluation.py \
  --base-url https://YOUR-STABLE-API-HOST \
  --dry-run
```

The 30-request latency workload is already complete. Run each v2 query once for quality and keep the
content-safe report outside the repository:

```bash
python3 doc/training/issues/issue-41/run_deployed_evaluation.py \
  --base-url https://YOUR-STABLE-API-HOST \
  --repetitions 1 \
  --report /tmp/issue-41-deployed-v2-report.json
```

Optionally pass `--deck-id OWNED_DECK_UUID`. Supply `GOOGLE_ID_TOKEN` in the environment or enter
it at the hidden prompt; there is intentionally no token CLI argument. The runner shows query and
Top-5 content only in the local terminal for first-run grading, asks for `2` strong, `1` related, or
`0` irrelevant. It asks for an explicit `yes` before the 10 provider-backed requests.

The JSON report stores only query labels/types, numeric grades, strong-hit/rank judgments, safe
status/request-ID/coverage fields, latency observations, fixture hash, and aggregate p50/p95 and
observed hit@5. It rejects query, card, term, meaning, score, and distance fields before writing.
Human grading only the returned Top 5 cannot produce unbiased nDCG, so the frozen synthetic set
remains the nDCG gate and this deployed workload supplies supporting observed hit@5/failure evidence.
The runner warns and requires explicit confirmation when all five results receive grade 2 or a
planned no-confident-match query receives a strong grade.

The production provider client validates but does not retain Vertex `token_count`, so deployed
responses cannot establish observed token usage. After v2 quality evaluation, run the explicit
content-safe cost probe below. It verifies the frozen v2 hash, makes exactly 10
`RETRIEVAL_QUERY` calls, and prints only aggregate provider-reported tokens, p50/p95 latency, the
published price snapshot, and estimated cost:

```bash
python3 doc/training/issues/issue-41/measure_vertex_query_cost.py \
  --project YOUR_GCP_PROJECT_ID \
  --location us-central1
```

The 2026-09-27 price snapshot is USD `$0.15` per one million input tokens, from Google's
[Gemini Embedding GA announcement](https://developers.googleblog.com/en/gemini-embedding-available-gemini-api/).
The script marks actual billing as uninspected; its estimate must not be presented as an invoice.

For every planned query, record outside the repository while inspecting relevance:

- anonymized query label such as `q01-paraphrase`;
- repetition number and warm/cold classification;
- HTTP status, `X-Request-ID`, total time, coverage status, eligible/indexed counts;
- anonymized Top-5 labels and their preassigned relevance grades;
- observed hit/miss and a short reason for each failure.

Commit only the resulting aggregate distribution and anonymized failure analysis. A single request
is an observation, not p50/p95. The runner uses nearest-rank p50/p95 and records the sample count.
The endpoint makes one query-embedding provider call per authenticated, validated search request;
invalid authentication/body and an inaccessible deck must be verified separately as zero-call
paths through deterministic tests or safe provider-call instrumentation.

## Required failure matrix

Record an observed or deterministic result for each row before closeout:

| Case | Expected boundary |
| --- | --- |
| Empty eligible corpus | 200, empty items, `empty`, zero eligible/indexed |
| Eligible cards with no current embeddings | 200, empty items, `empty`, indexed zero |
| Partial embeddings | Only current ready vectors rank; `partial` reports honest counts |
| Semantic content edit | Old hash/vector excluded until the new embedding is ready |
| Card or deck archive | Excluded immediately at query time without re-embedding |
| Model/version mismatch | Inactive model row is never used silently |
| Provider outage/timeout | Safe 503; retryability matches the error class; never empty 200 |
| Cross-owner card/deck | No result leakage; foreign deck is masked as not found |

## SQL versus vector boundary

SQL alone answers exact structured questions: ownership, deck/language/tag membership, archive
state, card IDs, counts, due time, review state, and review history. Do not embed these filters into
natural-language query text.

Concrete hybrid example: "within my active Business English deck, find five cards semantically
related to recovering after a work setback." SQL first restricts the authenticated owner, owned
deck, English language, active rows, active model, ready vector, and matching content hash. Cosine
distance then orders only those authorized candidates and applies `LIMIT 5`. A vector ranks rows;
it never grants access to them.

## Results in progress

### Operator-reported synthetic Vertex evaluation - 2026-09-26

- Fixture: `synthetic-en-v1`; the local preflight reproduced the expected fixture SHA-256 before
  the operator run.
- Provider/model: Vertex AI `gemini-embedding-001`, 512 dimensions.
- Workload: 10 synthetic `RETRIEVAL_DOCUMENT` calls plus seven labeled synthetic
  `RETRIEVAL_QUERY` calls; 17 requests total and 314 provider-reported input tokens.
- Result: macro nDCG@5 `1.0` and macro grade-2 Recall@5 `1.0`. All seven queries individually
  reported nDCG@5 `1.0` and grade-2 Recall@5 `1.0`; the precommitted `0.75` relevance gate passed.
- Provider request latency: p50 `1354.4 ms`, p95 `3464.7 ms`, calculated by the checked-in runner
  over the 17 provider requests.
- Comparison: the locally reproduced deterministic lexical baseline was macro nDCG@5 `0.5655`
  and macro grade-2 Recall@5 `0.6429` on the same fixture.
- Evidence limit: this is operator-reported output from seven simple synthetic queries. It does not
  establish private-card relevance, ambiguity robustness, Cloud Run end-to-end latency, provider
  availability, or tutor readiness. The operator execution environment, current price source,
  estimated charge, and actual billing inspection are not yet recorded.

### Operator-reported Neon coverage - 2026-09-26

- Database reported PostgreSQL `18.6 (6569466)` and pgvector `0.8.6`.
- One owner had 596 eligible active English cards; all 596 had a current ready embedding.
- The active model/version had 596 `ready` rows, zero null embeddings, and zero stale hashes.
- The SQL session reported `transaction_read_only = off`. The supplied script contains only
  `SELECT` and `EXPLAIN`, but the session itself was not restricted to read-only mode.

The content-safe coverage plan returned one aggregate row in `2.030 ms` after `0.697 ms` planning.
It processed 596 eligible cards and performed 596 primary-key embedding lookups. All 1,866 shared
buffer accesses were hits. The helper CTE selected the largest active English owner; its deck lookup
used the owned-deck index and memoized the two distinct deck lookups. The plan is appropriate for
the observed small corpus, although PostgreSQL estimated only two owned rows where 596 were
observed, so its cross-column/selectivity estimate was inaccurate.

The first stored-vector Top-5 diagnostic returned five rows in `132.961 ms` after `2.450 ms`
planning. Exact
ranking processed 596 current authorized candidates, then used an in-memory `top-N heapsort` of
25 kB. There was no temporary-file I/O. The full plan reported 7,066 shared hits and 205 shared
reads; the reads and vector comparisons coincided with the slower observation. Owner, active
card/deck, English-language, active-model, ready/non-null, and matching-hash conditions were all
enforced before the final sort and `LIMIT`.

This probe is intentionally not the exact API statement: it additionally discovers the largest
owner and materializes one stored document vector. The probe-vector CTE itself scanned 597
embedding rows, performed 597 owned-card index lookups, and completed in about `1.347 ms`; its
buffer attribution is repeated on the materialized CTE scans and must not be interpreted as 596
provider calls. The plan makes no provider request and does not measure semantic relevance.

An immediate second operator-reported execution returned five rows in `122.666 ms` after `2.286 ms`
planning, again with 7,066 shared hits, 205 shared reads, a 25 kB Top-N sort, and no temporary I/O.
It therefore does not support the earlier tentative cold-versus-warm explanation. Both executions
used the same materialized stored-vector CTE; that vector is referenced in a CTE scan 596 times and
does not match the API's bound query-vector shape. Their timings are retained as query-shape
diagnostics, not database ranking latency.

At 596 candidates, the small exact Top-K sort still does not justify an HNSW index. The earlier
Issue #40 exact API-shaped production observation remains separate and reported `10.054 ms` with a
27 kB Top-K sort, zero shared reads, and no temporary I/O. The final synthetic-constant EXPLAIN in
`production-inspection.sql` supplied the current comparison below.

The operator-reported synthetic-constant API-shaped plan returned five rows in `130.020 ms` after
`38.884 ms` planning. It ranked 596 current authorized candidates with a 25 kB in-memory Top-N
heapsort and no temporary I/O. The plan reported 3,665 shared hits, 262 shared reads, and 55 dirtied
buffers; 34 of the reads and about `6.102 ms` execution occurred in the extra owner-discovery CTE.
The filtered embedding scan read 18 shared buffers, the 597 owned-card index lookups used 1,916 hits
and three reads, and the final vector-ranking path accounted for the remaining read-heavy work.

`dirtied` buffer accounting on this read-only statement can result from PostgreSQL page hint-bit or
buffer maintenance when pages are read; the statement contains no data mutation and this is not
evidence that learning rows changed. The SQL Editor session nevertheless reported
`transaction_read_only = off`, so the database role/session was not technically constrained to
read-only operations.

This is a valid content-safe observation of the API-shaped ranking predicates, but not a warm
latency distribution. Its high planning time and 262 shared reads are consistent with a
read-heavy/cold-compute observation. Together with the separate 10.054 ms shared-hit-only Issue #40
observation, it demonstrates environment/cache sensitivity rather than a stable latency claim.
The exact sort remains only 25 kB over 596 candidates, so neither plan supplies a measured reason
to add HNSW.

### Operator-reported deployed workload - 2026-09-27

- Fixture `issue-41-deployed-en-v1` matched the frozen SHA-256
  `aca06f29ac008b72ab39a8a4c4f4e9c2abd95053551373cae1d76741171f3141`.
- Workload: 10 query types, three repetitions each, 30 provider-backed end-to-end requests.
- Availability/coverage: 30/30 returned HTTP 200; every response reported `complete` coverage with
  596 eligible and 596 indexed cards and returned five results.
- All-request end-to-end nearest-rank latency: p50 `1789.565 ms`, p95 `2793.855 ms`.
- First-request subset (`n=10`): p50 `1814.440 ms`, p95/max `10824.294 ms`; range
  `1749.970-10824.294 ms`.
- Repeated-request subset (`n=20`): p50 `1782.699 ms`, p95 `1856.942 ms`; range
  `1713.954-2793.855 ms`.
- One first request took `10824.294 ms`, substantially above the other observations. The report
  does not isolate Cloud Run cold start, provider time, network time, or PostgreSQL time, so this is
  an end-to-end outlier rather than an attributed root cause.

The submitted human grades marked all 50 returned items as grade 2, including all five results for
the predeclared no-confident-match query. That pattern is inconsistent with the precommitted rubric
unless the owned corpus unexpectedly contains five direct database-connection-pool answers. The
reported `observed_strong_hit_at_5 = 1.0` is therefore **not accepted as quality evidence yet**.
Latency, HTTP success, and coverage observations remain valid. The runner now defines grade 2 more
strictly and requires explicit confirmation for all-strong rows or a strong no-confident-match
result. Rerun once per query (`10` requests) to recalibrate quality; do not repeat the 30-request
latency workload.

The operator reran one request per query with the stricter rubric. All 10 requests returned HTTP
200, five results, and complete 596/596 coverage; `grading_warning_count` was zero. This 10-request
regrading pass observed p50 `1789.816 ms` and p95 `1909.015 ms`, but the earlier 30-request run
remains the latency workload.

Five queries had a strong result in the Top 5: q01 paraphrase-resilience at rank 1, q02
paraphrase-obsolete at rank 5, q05 ambiguous-careful at rank 3, q07 natural-reluctance at rank 2,
and q08 natural-drowsiness at rank 1. Four positive queries had no grade-2 result: q03
exact-meticulous, q04 exact-burnout, q06 ambiguous-tired, and q10 near-synonym-money. The planned
q09 no-confident-match returned five grade-0 results.

The report's all-query observed strong hit@5 is `0.5` (5/10). Because q09 is a negative-control
query that should not have a strong result, the positive-query observed strong hit@5 is `0.5556`
(5/9). This supporting metric grades only returned results and is not an unbiased nDCG or recall
estimate. Q09 also demonstrates that the endpoint always returns Top-K neighbors without a
relevance threshold: a successful response can contain five human-irrelevant items.

Before classifying q03, q04, q06, and q10 as retrieval failures, verify that their predeclared
expected concepts exist in the active English corpus. Run
[`expected-concept-check.sql`](expected-concept-check.sql), which returns only checked-in sanitized
term labels and aggregate exact-term counts. A zero count is a fixture/corpus mismatch, not a
retrieval miss. A positive count plus no grade-2 Top-5 result is a retrieval failure suitable for
the required failure analysis.

The operator-reported concept check returned zero active exact-term cards for all 17 predeclared
expected terms across the nine positive queries. The entire deployed v1 query fixture was therefore
derived from the synthetic Issue #38 concepts rather than grounded in the actual owned corpus. Its
human grades, all-query `0.5` hit@5, positive-query `0.5556` hit@5, apparent hits, and apparent
misses are **invalid as deployed relevance evidence**. They are retained only as a documented
evaluation-design failure. The 30-request HTTP/coverage/latency observations remain valid because
they do not depend on relevance labels. The q09 negative control remains a useful observation that
an unthresholded Top-K endpoint can return five human-irrelevant neighbors.

Before another provider-backed quality run, create `issue-41-deployed-en-v2` from sanitized or
explicitly consenting cards that are verified to exist in the active English corpus. Record an
exact-term count greater than zero for every positive target, write paraphrase/ambiguity queries and
expected concepts before retrieval, freeze the fixture hash, and then run one request per query.

The v2 fixture was frozen at SHA-256
`4756caf33424266c5722b344124a5d226427fc065dece6e02c8746fd7e86a5a4`. On 2026-09-27, the operator
reported that the v2 Neon preflight found exactly one active English card for each of the eight
sanitized targets: brat, communism, diligently, endangered, fragrance, hotshot, obtain, and
severance. All positive-target counts are therefore nonzero and the v2 corpus-grounding gate passed
before retrieval. The next quality run may classify an absent grade-2 Top-5 target as a retrieval
failure rather than a fixture/corpus mismatch.

The operator-reported v2 quality run then made one request per query. All 10 requests returned HTTP
200, five results, and complete 596/596 coverage; `grading_warning_count` was zero. End-to-end p50
was `1798.878 ms` and p95 was `2146.507 ms`, consistent with the main 30-request workload's normal
range, though this 10-request run is not a separate latency distribution claim.

Eight of the nine positive queries had a grade-2 result in the Top 5, for positive-query observed
strong hit@5 `0.8889`. Seven strong targets ranked first; q05 ambiguous-severance was the only
positive miss. By category: paraphrase 2/2, exact 2/2, natural sentence 2/2, near-synonym 1/1, and
ambiguous 1/2. Q09 negative control returned five grade-0 results. The report's raw all-query hit@5
is `0.8` because the correctly negative control is included in its denominator.

This is useful supporting evidence that semantic retrieval adds value on corpus-grounded
paraphrases and natural wording, but it is not unbiased nDCG or recall: only returned Top-5 items
were graded and each positive target had one known exact-term card. The results support keeping the
search MVP. They do not yet support a grounded tutor because ambiguous severance missed, the
endpoint returns five irrelevant neighbors for the negative control, and it exposes no relevance
threshold or no-answer decision.

Three concrete evaluation/product failure cases are now recorded:

1. Deployed fixture v1 used synthetic targets absent from the owned corpus, invalidating its quality
   grades and demonstrating why corpus presence must be checked before retrieval.
2. V2 q05's ambiguous severance query did not return its verified target as grade 2 in the Top 5,
   while the employment-pay paraphrase found the same target at rank 1. Retrieval is sensitive to
   which sense/context is expressed.
3. V2 q09 returned five human-irrelevant results because the endpoint always returns nearest
   neighbors and has no evidence-backed relevance/no-answer threshold. A tutor must not treat those
   rows as grounded context merely because Top-K is nonempty.

### Operator-reported v2 query cost - 2026-09-27

The frozen v2 cost probe made exactly 10 `RETRIEVAL_QUERY` calls. Vertex reported 84 input tokens.
Operator-machine-to-Vertex latency was p50 `1280.6 ms` and p95 `1713.1 ms`. At the 2026-09-27
published price of USD `$0.15` per one million input tokens, estimated input cost was
`$0.0000126`, or `$0.00000126` per query for this workload. Actual billing was not inspected, and
this excludes stored-document/backfill embeddings, Cloud Run, Neon, and network costs. Provider
timing is separate from deployed end-to-end timing; the independent distributions cannot be
subtracted to assign a precise latency share.

### Deterministic failure matrix closeout

Focused real-PostgreSQL/pgvector tests passed `11` cases across the embedding lifecycle and search
boundary, with the existing FastAPI TestClient deprecation warning:

| Case | Verified outcome |
| --- | --- |
| Empty eligible corpus | 200, empty items, `empty`, 0/0 coverage |
| Eligible but fully unindexed | 200, empty items, `empty`, 0/1 indexed/eligible |
| Partial embeddings | Only current ready vectors ranked; `partial` reported 2/4 |
| Semantic content edit | Stale result could not overwrite new content; old hash was excluded |
| Card/deck archive | Archived card excluded; archived owned deck returned empty before provider |
| Model mismatch | Inactive-model vector was excluded from results and coverage |
| Provider timeout | Safe retryable 503, never an empty success |
| Cross-owner card/deck | Foreign card excluded; foreign deck masked as 404 before provider |

Observed provider-call behavior was one query embedding for each valid normal, empty-corpus, or
fully-unindexed search. Invalid authentication/body, foreign deck, and archived deck stopped before
the provider and made zero calls. Calling the provider for zero eligible/indexed candidates is a
small avoidable cost/reliability inefficiency to consider in the next iteration; it does not change
the authorization result.

## Decision - iterate

Keep the semantic search MVP and current `gemini-embedding-001`/canonical-v1 configuration. Do not
add HNSW: exact filtered ranking over 596 candidates used only a 25-27 kB in-memory Top-K sort with
no temporary I/O, and observed read/cache variance rather than a measured index bottleneck. Do not
change the model or canonical text based on one ambiguous-sense miss; eight of nine corpus-grounded
positive queries had a strong Top-5 result and seven ranked first.

Do not proceed to Issue #42's grounded tutor yet. First define and evaluate a no-answer/relevance
boundary using frozen positive and negative labels plus observed score distributions, including
ambiguous word senses such as severance. A tutor must reject irrelevant context rather than assume
nonempty Top-K is grounded. Also consider checking candidate coverage before paying for a query
embedding when the corpus has no eligible/current vectors. This is an **iterate** decision, not an
`ai-ready` claim, SLA, production-scale performance claim, or user-impact result.

## Final limitations

- The synthetic frozen set supplied reproducible nDCG and a lexical word-overlap baseline. The
  corpus-grounded v2 set supplied returned-item human judgments and hit@5, not unbiased nDCG,
  recall, user impact, or a product exact/substring API comparison. Exact queries retrieved both
  verified exact-term cards at rank 1; the product has no separate general substring-search API.
- Provider, Neon, deployed API, and relevance results are operator-reported. No actual billing
  inspection, availability study, SLA, or production-scale workload was performed.
- The 30-request workload included an `10824.294 ms` outlier whose layer/root cause was not
  isolated. Twenty repeated observations had p50/p95 `1782.699/1856.942 ms`.
- English-only results do not establish Japanese or cross-language quality.
