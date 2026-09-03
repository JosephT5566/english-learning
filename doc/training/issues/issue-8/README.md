# Issue #8 - Multilingual Domain Schema

- Date: 2026-09-03
- Status: Users, decks, confirmed cards, and tags implemented and verified locally
- Outcome: Represent English and Japanese learning with database-enforced integrity

## Start here

Issue #8 implements the production domain schema on top of the Issue #7 Alembic and
PostgreSQL test foundation. English and Japanese use the same owned deck, card, tag, and review
model. Language-specific content remains optional on the shared card record.

Detailed artifacts:

- [Implementation design](design.md): accepted invariants, ownership constraints, example model,
  scheduling checks, indexes, fixtures, and verification plan
- [Issue #5 schema proposal](../issue-5/schema.md): broader approved schema that Issue #8 refines
- [Issue #5 alternatives](../issue-5/alternatives.md): rejected schema alternatives and accepted
  consequences

## Current implementation boundary

- Include users, decks, cards, embedded example fields, tags, card/tag associations, review states,
  review batches, and review events.
- Exclude AI draft and Google Sheets import tables.
- Treat every `learning_cards` row as confirmed learning content. Future incomplete AI content
  belongs in separate draft tables.
- Derive indexes from named access patterns and verify important behavior against PostgreSQL.

## Verified progress

- Revision `20260902_0002` adds users, decks, confirmed cards, tags, and card/tag associations after
  the empty Issue #7 baseline.
- PostgreSQL enforces user identity, required deck ownership, supported languages, title/version/time
  checks, paired per-owner creation replay data, and restricted owner deletion.
- Confirmed cards require nonblank term/meaning and a valid owned `(deck_id, owner_id)` pair.
- Nullable language-specific fields and one embedded example support representative English and
  Japanese card fixtures through the same table.
- Card constraints cover optional field lengths, example dependencies, related-word collection
  bounds, part-of-speech values, replay data, versions, and timestamps.
- The active-card listing index shape is verified against its named access pattern; no query-plan
  effectiveness claim exists yet.
- Tags are unique by normalized name per owner but can be reused by different owners. Composite
  foreign keys reject cross-owner associations, and `(card_id, tag_id)` rejects duplicates.
- Tag deletion removes only association rows; it does not delete cards. The reverse tag-filtering
  index definition is verified. The 20-tag card limit remains a future locked transaction rule.
- A temporary database and the development database both passed upgrade, baseline downgrade, and
  re-upgrade. The full local backend suite passes 69 tests with one existing upstream warning.
- Review tables, the ER diagram, complete domain fixtures, and query-plan inspection remain
  unimplemented.

## Next action

Implement `review_states`, including one current row per card, composite ownership, scheduling
checks, timestamp relationships, and the owner/due-time index.
