# Frozen retrieval regression gate

Issue #67 uses the production `semantic_search` function and migrated PostgreSQL/pgvector,
with a fake query embedding provider. `process_card` stores the frozen document embeddings in
`card_embeddings` using the production content hash and embedding lifecycle. No evaluation test
calls Vertex, gcloud, or another model API. Scoring uses the original Issue #38 `evaluate()`.
The gate is macro nDCG@5 >= 0.75, frozen in
[Issue #41](../../../../doc/training/issues/issue-41/README.md#frozen-metrics-and-gate).
Individual queries below 0.75 appear in reports but do not independently fail the gate.

## Generate the fixture before merging

The maintainer must run this from the repository root with their own gcloud identity.
Replace `<ID>` with the Google Cloud project ID:

```sh
python3 doc/training/issues/issue-38/evaluate_vertex.py --project <ID> --dump-vectors apps/api/tests/eval/fixtures/synthetic-en-v1.vectors.json
```

Inspect and commit that synthetic fixture in the same PR before merging. The command makes
10 document and 7 query embedding requests. Omitting `--dump-vectors` preserves the existing
report-only behavior. The labels and `FIXTURE_SHA256` are unchanged. A missing fixture fails,
even without `RUN_POSTGRES_INTEGRATION_TESTS=1`; it never skips or substitutes generated vectors.

The JSON schema is version 1:

| Key                | Value                                                                                                |
| ------------------ | ---------------------------------------------------------------------------------------------------- |
| `schema_version`   | Integer `1`                                                                                          |
| `model`            | `gemini-embedding-001`                                                                               |
| `dim`              | Integer `512`                                                                                        |
| `model_version`    | Production `MODEL_VERSION`, currently `vertex-ai/gemini-embedding-001/512/retrieval-v1/canonical-v1` |
| `relevance_sha256` | SHA-256 of the raw bytes of Issue #38 `relevance.json`                                               |
| `created_at`       | ISO 8601 timestamp with timezone, exported in UTC                                                    |
| `cards`            | Object keyed by all 10 label card IDs, each value a 512-number vector                                |
| `queries`          | Object keyed by all 7 exact query texts, each value a 512-number vector                              |

Vectors must be finite and nonzero. The loader rejects incompatible metadata, missing/extra
card or query keys, and a mismatched relevance SHA. Current label SHA-256 is
`a1d6e3e9a76a2705dd5fc2a869339debf46c32217a22fef35d2a7e6d632811dd`.

The exporter retains `canonical_card_text`: language, term, meaning, and example sentence.
For these exact synthetic cards, it equals production `canonical_text`, which a unit test checks.
This does not establish equivalence for production cards with additional semantic fields.
The SQL harness assigns stable UUIDs to cards for deterministic database tie-breaking.

## Run and read failures

Use disposable PostgreSQL/pgvector, never a production database or SQLite. The backend CI job
sets `APP_ENV=test`, `RUN_POSTGRES_INTEGRATION_TESTS=1`, and the local test database URL, then
runs these commands from `apps/api`:

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

The gate writes `apps/api/retrieval-eval-report/report.md` and `report.json`, including failures
before database setup. Reports include all seven queries, per-query nDCG@5, queries below
threshold, macro score versus 0.75, SHA status, errors, and the fixture generation command.
Unmeasured scores say unavailable or JSON null. Reports are ignored by Git. CI always uploads
the directory as `retrieval-eval-report` and appends the Markdown to the failed run's summary.

`test_deliberately_broken_ranking_fails_gate` reverses ideal rankings and asserts a score below
0.75. `test_postgres_control_detects_reversed_ranking` also checks the real SQL path with
orthogonal document vectors and relevance-derived query vectors generated only in pytest's
temporary directory. Those control vectors never replace the required frozen Vertex fixture.

## Evidence limits

There are only 10 cards and 7 synthetic queries. This gate catches SQL ordering, embedding
index/eligibility, and distance regressions on that set. It cannot establish broad retrieval
quality or model-quality drift. Frozen vectors cannot detect Vertex-side drift; that requires
an explicit new provider evaluation. PostgreSQL chooses the execution plan for this small set,
so a pass does not prove that an HNSW index was used or validate production-scale recall.
An approximate HNSW evaluation would need a threshold margin and separate recall evidence.

The historical 1.0 Vertex figure is operator-reported and is not reproducible from the repository
until the frozen fixture is committed. No frozen-vector baseline has been measured here.
Record that baseline only after the real fixture exists. Generated control-vector scores are
harness checks and are not a model-quality baseline. Do not change labels or lower the threshold
in response to a failed run.

## Local verification evidence

See the final implementation handoff for commands and exit codes. The new exporter CLI test was
run before implementation and failed because `--dump-vectors` was unrecognized, pytest exit 1.
A deliberate temporary change from ascending to descending cosine distance in production SQL
made the PostgreSQL control test fail with `assert 0.0 >= 0.75`, pytest exit 1. The original SQL
was restored immediately. This mutation check does not establish the missing Vertex baseline.
