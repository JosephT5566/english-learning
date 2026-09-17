# Semantic Vocabulary Search and Later RAG Tutor

Status: planned after Issue #27; retrieval first. Updated: 2026-09-17.

## Product goal and boundary

Let a signed-in user find their own English learning cards by meaning, such as
"words describing exhaustion at work." The first milestone returns relevant
cards, not an LLM answer. A grounded tutor is a later phase, gated on observed
retrieval quality.

Use the existing SvelteKit frontend, FastAPI API on Cloud Run, and Neon
PostgreSQL as the sole source of truth. Evaluate `pgvector` inside Neon. Do not
add a separate vector database, framework, queue, or query cache for the MVP.
The older [Sheets/Cloudflare prototype](semantic-search-proposal.md) is
historical and must not be used as the current architecture.

## Data flow

```text
card create / semantic edit / backfill
  -> canonical semantic text -> embedding provider -> stored derived vector

POST /v1/cards/semantic-search
  -> Google identity verification -> query validation -> one query embedding
  -> owned, eligible PostgreSQL cards ordered by cosine similarity -> Top-K
```

Card writes remain authoritative even when vector generation fails. Embeddings
are derived, versioned, retryable data. The lifecycle must cover normal card
create/edit, the existing import, archive, and later AI-draft confirmation.
Neither review scheduling nor owner/timestamp fields belong in embedding text.
Exact questions about due cards, counts, ownership, language, and review history
remain SQL queries. Combine SQL filters with vector ranking only when a feature
needs both.

## Decisions required before implementation

- Choose `learning_cards.embedding` or a separate `card_embeddings` table after
  considering ownership, stale vectors, model changes, and recovery.
- Select a provider/model and dimension using current low-volume cost, relevance,
  privacy, and latency observations. Keep credentials on the backend.
- Specify canonical text and the content/model hash that triggers re-embedding.
- Define a failure and bounded retry/backfill path that does not corrupt card
  creation or optimistic edits.
- Define active/archived, language, deck, and ownership predicates and the
  similarity score contract. Filters must apply before Top-K selection.
- Verify Neon extension/migration privileges; inspect data size and query plans
  before considering an HNSW index.
- Build a sanitized labeled query set and a reproducible quality metric. Use
  deterministic fake vectors for CI correctness tests and separate provider
  evaluation for semantic relevance.

## Ticket sequence

1. [#38 - retrieval design and evaluation set](https://github.com/JosephT5566/english-learning/issues/38), after #27.
2. [#39 - derived embedding storage and backfill](https://github.com/JosephT5566/english-learning/issues/39), after #38.
3. [#40 - owner-safe search API and Svelte flow](https://github.com/JosephT5566/english-learning/issues/40), after #39.
4. [#41 - retrieval quality, cost, and failure evaluation](https://github.com/JosephT5566/english-learning/issues/41), after #40.
5. [#42 - grounded tutor](https://github.com/JosephT5566/english-learning/issues/42), only after #41 records a go decision.

Issues #28-#31 are the existing AI-authoring and hardening roadmap. If their
work lands before semantic search, embedding maintenance must include their
confirmed-card path. If semantic search lands first, that path must use the same
derived-data lifecycle when implemented. These tickets do not change the active
Issue #27 acceptance boundary.
