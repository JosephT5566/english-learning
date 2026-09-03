# Issue #8 Representative Query Plans

- Date: 2026-09-03
- Database: PostgreSQL 17
- Scope: Local planner evidence for the indexes introduced by revision `20260902_0002`

## Method

`apps/api/tests/integration/test_query_plans.py` creates a fresh database through the same
`migrated_database_engine` fixture used by the constraint tests. It inserts a deterministic dataset,
runs `ANALYZE`, and executes each named read with
`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`.

The dataset contains:

- 100 users
- 2,000 decks, including both languages and archived rows
- 40,000 cards, including archived rows
- 100 tags and 40,000 card/tag associations
- 40,000 current review states with distributed due dates
- 4,000 ten-item review batches and 40,000 review events; the selected card has 10 history rows

The test recursively inspects each JSON plan and requires PostgreSQL to select the deliberate index
without disabling sequential scans or other planner strategies. It does not assert costs, execution
times, buffer counts, or the complete node tree because those details vary with hardware and
PostgreSQL statistics.

## Observed mapping

| Named access pattern | Query shape | Index selected |
| --- | --- | --- |
| Active cards in one deck | deck equality, active partial predicate, newest stable order, limit | `ix_learning_cards_active_deck_created_id` |
| One owner's decks by language | owner/language equality and active archive predicate | `ix_learning_decks_owner_language_archive` |
| Cards attached to one tag | tag equality and card-ID order, limit | `ix_learning_card_tags_tag_id_card_id` |
| Due cards for one owner | owner equality, due-time range, stable due order, card/deck archive joins, limit | `ix_review_states_owner_next_review_card` |
| One owner's review history | owner equality, newest stable order, limit | `ix_review_events_owner_reviewed_id` |
| One card's review history | card equality, newest stable order, limit | `ix_review_events_card_reviewed_id` |
| One batch response | batch equality and generated event-ID order | `ix_review_events_batch_id_id` |

## Interpretation and limits

This is stronger than checking index definitions alone: PostgreSQL executed every representative
query and chose the intended index for the tested data distribution. It also demonstrates that the
due-state index remains useful when the query joins cards and decks to exclude archived content.

It is not a benchmark or a production performance claim. Real cardinalities, skew, cache state,
PostgreSQL versions, query parameters, and table growth can change planner choices. After production
data or realistic imports exist, slow-query evidence and fresh plans should drive any new indexes.
The intentionally deferred text-search index still has no representative query or evidence.
