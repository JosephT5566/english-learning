-- Issue #41 v2 corpus-grounding preflight.
-- Every count must be greater than zero before any v2 provider-backed quality request.
-- Returns only supplied sanitized terms and aggregate counts; no owner/card IDs or other content.

WITH expected(expected_term) AS (
    VALUES
        ('communism'),
        ('severance'),
        ('brat'),
        ('hotshot'),
        ('fragrance'),
        ('diligently'),
        ('endangered'),
        ('obtain')
),
active_english_cards AS (
    SELECT c.term
    FROM learning_cards AS c
    JOIN learning_decks AS d
      ON (d.id, d.owner_id) = (c.deck_id, c.owner_id)
    WHERE c.archived_at IS NULL
      AND d.archived_at IS NULL
      AND d.target_language = 'en'
)
SELECT expected.expected_term,
       count(cards.term) AS exact_active_term_count
FROM expected
LEFT JOIN active_english_cards AS cards
  ON lower(btrim(cards.term)) = expected.expected_term
GROUP BY expected.expected_term
ORDER BY expected.expected_term;
