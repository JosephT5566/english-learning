# Issue #8 - Multilingual Domain Schema

- Date: 2026-09-02
- Status: Design checkpoint complete; implementation not started
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

## Next action

Create the Issue #8 branch and add the first bounded migration/test slice for `users` and
`learning_decks`.
