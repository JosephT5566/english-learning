# Issue #9 Query-Plan Findings

- Database: local PostgreSQL 17 (`postgres:17-alpine`)
- Method: deterministic data generation, `ANALYZE`, then
  `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`
- Test: `apps/api/tests/integration/test_query_plans.py`

## Representative distribution

- 100 owners
- 2,000 decks
- 40,000 cards
- 40,000 review states
- 40,000 card/tag links
- 40,000 review events and 4,000 review batches

## Findings

| Access pattern | Stable order | Selected deliberate index |
| --- | --- | --- |
| Owner deck management list | `updated_at DESC, id DESC` | `ix_learning_decks_owner_updated_id` |
| Owner card management list | `updated_at DESC, id DESC` | `ix_learning_cards_owner_updated_id` |
| Card tag reverse traversal | `card_id ASC` | `ix_learning_card_tags_tag_id_card_id` |
| Owner due review | `next_review_at ASC, card_id ASC` | `ix_review_states_owner_next_review_card` |

The two management-list indexes are introduced reversibly by Alembic revision `20260903_0003`.
The tag and due indexes were created with the Issue #8 domain schema. PostgreSQL selected all four
without disabling sequential scans or forcing planner methods. The executable test also retains the
five Issue #8 access-pattern assertions for active deck cards, owner/language decks, and review
history/reconstruction.

The assertions deliberately freeze only intended index selection. They do not freeze total plan
shape, costs, execution times, or buffer counts, because those depend on PostgreSQL version,
statistics, hardware, cache warmth, and data distribution. These results justify the local access
paths but are not a production performance claim; plans should be re-inspected with representative
production distributions if latency or growth becomes material.
