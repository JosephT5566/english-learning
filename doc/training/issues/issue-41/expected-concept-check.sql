-- Issue #41 sanitized expected-concept presence check.
-- Returns only checked-in query labels/terms and aggregate counts. It does not return owner IDs,
-- card IDs, card content beyond the sanitized expected term, or vectors.

WITH expected(query_label, expected_term) AS (
    VALUES
        ('q01-paraphrase-resilience', 'resilient'),
        ('q02-paraphrase-obsolete', 'obsolete'),
        ('q03-exact-meticulous', 'meticulous'),
        ('q04-exact-burnout', 'burnout'),
        ('q05-ambiguous-careful', 'meticulous'),
        ('q05-ambiguous-careful', 'frugal'),
        ('q05-ambiguous-careful', 'thrifty'),
        ('q05-ambiguous-careful', 'cautious'),
        ('q06-ambiguous-tired', 'exhausted'),
        ('q06-ambiguous-tired', 'drowsy'),
        ('q06-ambiguous-tired', 'burnout'),
        ('q07-natural-reluctance', 'reluctant'),
        ('q07-natural-reluctance', 'hesitant'),
        ('q08-natural-drowsiness', 'drowsy'),
        ('q08-natural-drowsiness', 'sleepy'),
        ('q10-near-synonym-money', 'frugal'),
        ('q10-near-synonym-money', 'thrifty')
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
SELECT expected.query_label,
       expected.expected_term,
       count(cards.term) AS exact_active_term_count
FROM expected
LEFT JOIN active_english_cards AS cards
  ON lower(btrim(cards.term)) = expected.expected_term
GROUP BY expected.query_label, expected.expected_term
ORDER BY expected.query_label, expected.expected_term;
