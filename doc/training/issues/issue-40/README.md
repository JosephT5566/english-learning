# Issue #40 - authenticated semantic vocabulary search

Status: implementation, local verification, and operator-supplied production query-plan inspection
complete; deployment/provider smoke pending. Updated 2026-09-25.

Traditional Chinese walkthrough: [learning notes](learning-notes.zh-TW.md).

## Implemented boundary

- `POST /v1/cards/semantic-search` accepts a trimmed NFC query of 2-500 characters, fixed English
  target language, optional owned deck UUID, and Top-K limit 1-20 (default 10).
- Authentication and request validation complete before the single `RETRIEVAL_QUERY` Vertex call.
  Provider failures use the shared safe envelope and return a visible 503 rather than an empty
  success.
- Exact SQL applies authenticated owner, active card/deck, language/deck, active model, ready state,
  non-null vector, and current semantic-hash predicates before cosine ordering and `LIMIT`.
  Cross-owner deck lookup is masked as 404. No raw vector is returned.
- Results expose cosine `distance` in `[0, 2]` (lower is better) and `score = 1 - distance` in
  `[-1, 1]` (higher is better), with card display fields and stable UUID tie-breaking. There is no
  relevance threshold claim.
- Coverage is `complete`, `partial`, or `empty`, with eligible/indexed counts. Missing vectors can
  therefore be distinguished from no eligible cards without pretending provider failure is empty.
- The static `/search` page uses the existing bearer-token client and generated OpenAPI types. It
  preserves the entered query across retry, and presents loading, empty/unindexed, partial,
  authentication, provider/network, and retry states. Navigation and card links use SvelteKit's
  base-path-aware routing.
- The protected candidate smoke workflow has an explicit semantic-search opt-in. It makes one fixed
  provider-backed request, validates the response contract and stable ordering, rejects raw-vector
  fields, and records only safe counts, request ID, coverage status, and one total-time observation.

## Local verification

- Complete backend suite: 289 passed against disposable PostgreSQL databases, with the existing
  TestClient deprecation warning. The local production allowlist was explicitly disabled to match
  repository test configuration; an initial run inherited the developer `.env` allowlist and was
  therefore invalid rather than a product regression.
- New real PostgreSQL/pgvector suite: 3 passed. Deterministic vectors prove ranking and exclude
  another owner, archived rows, and missing vectors; malformed/unauthenticated requests make zero
  fake-provider calls; provider timeout returns retryable 503.
- Frontend: Svelte check passed, 18 Node contract tests plus 2 Vitest component tests passed, and
  the static production build passed.
- Critical browser flow: 1 passed, covering the static `/search` route, authenticated request body,
  partial-index notice, ordered display result, score, and base API origin.

## Remaining acceptance evidence

- Run the new candidate semantic-search smoke and inspect one expected Top-K match locally; record
  observed safe latency/coverage and the boolean quality outcome only.
- Deploy through the existing candidate process, verify an authenticated search, then promote only
  after the normal release checks.

## Operator-supplied production query-plan observation

On 2026-09-25, a read-only production Neon inspection reported complete current coverage: 596/596
eligible English cards and 1/1 Japanese card. The final unfiltered exact-ranking shape used
small-table sequential scans, an in-memory hash join, owned deck index lookups, and a 27 kB top-N
heapsort over 596 English candidates. Planning took 1.354 ms and execution took 10.054 ms with zero
shared reads and no temporary I/O. The query-vector CTE and scalar InitPlans each executed once.
Earlier probes exposed a CTE-induced 1,194-row intermediate join and one 128.336 ms read-heavy run;
those were retained as query-shape/cache observations rather than treated as API latency. These are
single SQL Editor observations, not p50/p95 or Cloud Run end-to-end measurements. No HNSW index is
warranted at the observed corpus size; see the learning notes for the complete interpretation.

## Five-minute ownership proof

Google authentication maps the bearer token to an internal user ID; the request cannot supply an
owner. That ID appears in both card and deck predicates inside the ranked SQL relation. The query
also rejects archived cards/decks, the wrong language/deck, old model rows, non-ready/null vectors,
and hashes that no longer match confirmed card text before cosine distance is sorted or limited.
The vector ranks already-authorized rows but never grants access to them. Structured questions stay
on existing SQL endpoints; this endpoint embeds only a bounded meaning query and does no SQL
generation.
