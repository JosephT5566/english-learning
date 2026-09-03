# Issue #8 - Multilingual Domain Schema

- Date: 2026-09-02
- Status: First users/decks slice implemented and verified locally
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

- Revision `20260902_0002` adds `users` and `learning_decks` after the empty Issue #7 baseline.
- PostgreSQL enforces user identity, required deck ownership, supported languages, title/version/time
  checks, paired per-owner creation replay data, and restricted owner deletion.
- English and Japanese deck fixtures use the same table.
- A temporary database and the development database both passed upgrade, baseline downgrade, and
  re-upgrade. The full local backend suite passes 40 tests with one existing upstream warning.
- Cards, tags, review tables, the ER diagram, full multilingual fixtures, and query-plan inspection
  remain unimplemented.

## Next action

Implement confirmed `learning_cards` and its composite owned deck relationship as the next bounded
migration/test slice.
