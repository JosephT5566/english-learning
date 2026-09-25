# Issue #40 - authenticated semantic vocabulary search

Status: complete. Implementation, local verification, production query-plan inspection, candidate
promotion, stable-URL semantic smoke, deployed frontend verification, and the bounded
retrieval-quality check passed. Updated 2026-09-26.
Updated 2026-09-26.

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

## Acceptance closeout

- Deterministic PostgreSQL tests establish ranking correctness and exclusion boundaries.
- Candidate and stable-URL smoke checks establish the deployed API contract and complete coverage.
- The deployed static search page passed an operator browser check.
- A private-content-safe human check found an expected relevant concept at rank 1 for the fixed
  recovery-after-difficulty query. Only the pass result and rank bucket are retained; this bounded
  observation is not a general retrieval-quality claim.

## Operator-reported candidate smoke

On 2026-09-26, the operator reported that zero-traffic revision
`english-learning-api-98034f911a63` passed the protected authenticated candidate smoke. The owned
read and controlled review write with exact replay passed. The explicitly enabled provider-backed
semantic request returned five results with `complete` coverage (`596/596`); request ID
`f54491aa-b291-4d7a-b142-42035b4feb67` was recorded for correlation. Curl observed 2.058828 seconds
for this one end-to-end request. This is a single operator-reported observation, not a latency
distribution, availability claim, or retrieval-quality judgment. The candidate URL is intentionally
not retained as durable evidence because revision URLs are operational endpoints rather than stable
product contracts.

## Operator-reported promotion and stable-URL smoke

On 2026-09-26, the operator promoted revision `english-learning-api-98034f911a63` to production
traffic and ran the same bounded semantic smoke through the stable Cloud Run service URL. Public
health and authenticated owned reads passed. The semantic request returned HTTP 200 with five
results, `complete` coverage (`596/596`), and request ID
`d581e030-222e-497d-9c1b-38ea4bd7b9b3`; curl observed 2.265995 seconds. The review-write opt-in was
intentionally omitted because candidate verification had already passed the controlled write and
exact replay. This is one operator-reported end-to-end observation, not a latency distribution or
retrieval-quality claim.

## Operator-reported deployed frontend verification

On 2026-09-26, the operator reported that the deployed application's search page worked correctly
against the promoted API. This closes the deployed browser-flow check without retaining query text,
card content, card IDs, or tokens. It verifies the deployed integration path, not the semantic
relevance of an expected Top-K result.

## Operator-reported bounded Top-K quality check

On 2026-09-26, the operator inspected the deployed response for the fixed
recovery-after-difficulty query and judged the check passed. An expected directly related concept
appeared at rank 1, with additional contextually related results in the Top 5. No response body,
card/deck identifier, or private card content is retained in repository evidence. This closes Issue
#40's small provider-backed quality smoke; broader quality, cost, and failure evaluation belongs to
Issue #41.

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
