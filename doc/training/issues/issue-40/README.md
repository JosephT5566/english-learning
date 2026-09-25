# Issue #40 - authenticated semantic vocabulary search

Status: implementation and local verification complete; deployment/provider smoke and final query-plan capture pending. Updated 2026-09-25.

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

- Capture `EXPLAIN (ANALYZE, BUFFERS)` for the final three-table exact query on representative small
  data, including deck-filtered and unfiltered forms. Do not add HNSW without measured need.
- Run one small provider-backed quality/latency smoke outside CI and record observed values only.
- Deploy through the existing candidate process, verify an authenticated search, then promote only
  after the normal release checks.

## Five-minute ownership proof

Google authentication maps the bearer token to an internal user ID; the request cannot supply an
owner. That ID appears in both card and deck predicates inside the ranked SQL relation. The query
also rejects archived cards/decks, the wrong language/deck, old model rows, non-ready/null vectors,
and hashes that no longer match confirmed card text before cosine distance is sorted or limited.
The vector ranks already-authorized rows but never grants access to them. Structured questions stay
on existing SQL endpoints; this endpoint embeds only a bounded meaning query and does no SQL
generation.
