-- Issue #41 content-safe, read-only production inspection.
--
-- Run in Neon SQL Editor or another read-only PostgreSQL session. This file returns only
-- aggregate counts and EXPLAIN plans. It does not select card text, card IDs, owner IDs,
-- content hashes, or vector values.
--
-- The ranking probes use one existing current embedding as the query vector. They measure
-- PostgreSQL filtering and exact Top-K shape only; they do not measure provider latency or
-- semantic relevance. Run the plan twice if you need one labeled cold-ish and one warm
-- observation. Do not describe two observations as a latency distribution.

SELECT current_database() AS database_name,
       current_setting('server_version') AS server_version,
       (SELECT extversion FROM pg_extension WHERE extname = 'vector') AS vector_version,
       transaction_read_only
FROM current_setting('transaction_read_only') AS transaction_read_only;

-- Overall English coverage without identifying an owner.
WITH per_owner AS (
    SELECT c.owner_id,
           count(*) AS eligible_count,
           count(e.card_id) FILTER (
               WHERE e.state = 'ready'
                 AND e.embedding IS NOT NULL
                 AND e.content_hash = c.semantic_content_hash
           ) AS indexed_count
    FROM learning_cards AS c
    JOIN learning_decks AS d
      ON (d.id, d.owner_id) = (c.deck_id, c.owner_id)
    LEFT JOIN card_embeddings AS e
      ON (e.card_id, e.owner_id) = (c.id, c.owner_id)
     AND e.model_version = 'vertex-ai/gemini-embedding-001/512/retrieval-v1/canonical-v1'
    WHERE c.archived_at IS NULL
      AND d.archived_at IS NULL
      AND d.target_language = 'en'
    GROUP BY c.owner_id
)
SELECT count(*) AS owner_count,
       coalesce(sum(eligible_count), 0) AS eligible_count,
       coalesce(sum(indexed_count), 0) AS indexed_count,
       coalesce(sum(eligible_count - indexed_count), 0) AS unindexed_count,
       coalesce(min(eligible_count), 0) AS min_eligible_per_owner,
       coalesce(max(eligible_count), 0) AS max_eligible_per_owner
FROM per_owner;

-- Aggregate embedding lifecycle states for active English cards. Rows for other model
-- versions are intentionally visible only as grouped counts.
SELECT e.model_version,
       e.state,
       count(*) AS row_count,
       count(*) FILTER (WHERE e.embedding IS NULL) AS null_embedding_count,
       count(*) FILTER (
           WHERE e.content_hash <> c.semantic_content_hash
              OR c.semantic_content_hash IS NULL
       ) AS stale_hash_count
FROM card_embeddings AS e
JOIN learning_cards AS c
  ON (c.id, c.owner_id) = (e.card_id, e.owner_id)
JOIN learning_decks AS d
  ON (d.id, d.owner_id) = (c.deck_id, c.owner_id)
WHERE c.archived_at IS NULL
  AND d.archived_at IS NULL
  AND d.target_language = 'en'
GROUP BY e.model_version, e.state
ORDER BY e.model_version, e.state;

-- Coverage-query plan with the largest active English owner selected inside the statement.
-- This keeps the owner identifier out of the output while exercising the real join/filter shape.
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
WITH owner_target AS MATERIALIZED (
    SELECT c.owner_id
    FROM learning_cards AS c
    JOIN learning_decks AS d
      ON (d.id, d.owner_id) = (c.deck_id, c.owner_id)
    WHERE c.archived_at IS NULL
      AND d.archived_at IS NULL
      AND d.target_language = 'en'
    GROUP BY c.owner_id
    ORDER BY count(*) DESC, c.owner_id
    LIMIT 1
)
SELECT count(*) AS eligible_count,
       count(e.card_id) FILTER (
           WHERE e.state = 'ready'
             AND e.embedding IS NOT NULL
             AND e.content_hash = c.semantic_content_hash
       ) AS indexed_count
FROM owner_target AS target
JOIN learning_cards AS c ON c.owner_id = target.owner_id
JOIN learning_decks AS d
  ON (d.id, d.owner_id) = (c.deck_id, c.owner_id)
LEFT JOIN card_embeddings AS e
  ON (e.card_id, e.owner_id) = (c.id, c.owner_id)
 AND e.model_version = 'vertex-ai/gemini-embedding-001/512/retrieval-v1/canonical-v1'
WHERE d.owner_id = target.owner_id
  AND c.archived_at IS NULL
  AND d.archived_at IS NULL
  AND d.target_language = 'en';

-- Exact Top-5 ranking plan over the same representative owner. The probe CTE returns no
-- vector value to the client; it supplies one current stored vector only inside this statement.
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
WITH owner_target AS MATERIALIZED (
    SELECT c.owner_id
    FROM learning_cards AS c
    JOIN learning_decks AS d
      ON (d.id, d.owner_id) = (c.deck_id, c.owner_id)
    WHERE c.archived_at IS NULL
      AND d.archived_at IS NULL
      AND d.target_language = 'en'
    GROUP BY c.owner_id
    ORDER BY count(*) DESC, c.owner_id
    LIMIT 1
),
probe AS MATERIALIZED (
    SELECT e.embedding
    FROM owner_target AS target
    JOIN card_embeddings AS e ON e.owner_id = target.owner_id
    JOIN learning_cards AS c
      ON (c.id, c.owner_id) = (e.card_id, e.owner_id)
    JOIN learning_decks AS d
      ON (d.id, d.owner_id) = (c.deck_id, c.owner_id)
    WHERE c.archived_at IS NULL
      AND d.archived_at IS NULL
      AND d.target_language = 'en'
      AND e.model_version = 'vertex-ai/gemini-embedding-001/512/retrieval-v1/canonical-v1'
      AND e.state = 'ready'
      AND e.embedding IS NOT NULL
      AND e.content_hash = c.semantic_content_hash
    ORDER BY c.id
    LIMIT 1
)
SELECT c.id
FROM owner_target AS target
CROSS JOIN probe
JOIN learning_cards AS c ON c.owner_id = target.owner_id
JOIN learning_decks AS d
  ON (d.id, d.owner_id) = (c.deck_id, c.owner_id)
JOIN card_embeddings AS e
  ON (e.card_id, e.owner_id) = (c.id, c.owner_id)
WHERE d.owner_id = target.owner_id
  AND c.archived_at IS NULL
  AND d.archived_at IS NULL
  AND d.target_language = 'en'
  AND e.model_version = 'vertex-ai/gemini-embedding-001/512/retrieval-v1/canonical-v1'
  AND e.state = 'ready'
  AND e.embedding IS NOT NULL
  AND e.content_hash = c.semantic_content_hash
ORDER BY e.embedding <=> probe.embedding, c.id
LIMIT 5;

-- Preferred API-shaped latency probe. Unlike the stored-vector diagnostic above, this uses one
-- deterministic synthetic 512-dimensional constant in the same role as the API's bound query
-- vector. It sends nothing to a provider and contains no learning content. The owner_target CTE
-- remains extra inspection work; subtracting it is not valid, so report the complete plan timing.
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
WITH owner_target AS MATERIALIZED (
    SELECT c.owner_id
    FROM learning_cards AS c
    JOIN learning_decks AS d
      ON (d.id, d.owner_id) = (c.deck_id, c.owner_id)
    WHERE c.archived_at IS NULL
      AND d.archived_at IS NULL
      AND d.target_language = 'en'
    GROUP BY c.owner_id
    ORDER BY count(*) DESC, c.owner_id
    LIMIT 1
)
SELECT c.id
FROM owner_target AS target
JOIN learning_cards AS c ON c.owner_id = target.owner_id
JOIN learning_decks AS d
  ON (d.id, d.owner_id) = (c.deck_id, c.owner_id)
JOIN card_embeddings AS e
  ON (e.card_id, e.owner_id) = (c.id, c.owner_id)
WHERE d.owner_id = target.owner_id
  AND c.archived_at IS NULL
  AND d.archived_at IS NULL
  AND d.target_language = 'en'
  AND e.model_version = 'vertex-ai/gemini-embedding-001/512/retrieval-v1/canonical-v1'
  AND e.state = 'ready'
  AND e.embedding IS NOT NULL
  AND e.content_hash = c.semantic_content_hash
ORDER BY e.embedding <=> CAST(
             '[' || trim(trailing ',' FROM repeat('0.01,', 512)) || ']'
             AS vector(512)
         ),
         c.id
LIMIT 5;
