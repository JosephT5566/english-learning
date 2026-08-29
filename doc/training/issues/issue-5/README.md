# Issue #5 - Multilingual Backend Design

- Date: 2026-08-29
- Status: Design complete; no backend implementation started; formal GitHub closure not verified
- Outcome: Defensible English and Japanese product, API, schema, migration, and trust-boundary design

## Start here

Issue #5 defines the database-backed MVP before FastAPI implementation. English and Japanese share
one language-aware model. The backend derives identity and ownership from verified authentication,
calculates review transitions, and commits immutable history plus current state atomically. AI output
can become only a validated editable draft until explicit confirmation.

Detailed artifacts:

- [Detailed design](design.md): decisions, invariants, MVP API contracts, Sheet mapping, and checklist
- [Schema](schema.md): tables, fields, constraints, indexes, and transaction-enforced invariants
- [Failure and recovery](failure-recovery.md): operation outcomes, retry safety, and client recovery
- [Request flows](request-flows.md): runtime trust boundaries and mutation/review sequences
- [Future AI draft lifecycle](ai-draft-lifecycle.md): safe conceptual AI authoring boundary
- [Alternatives](alternatives.md): rejected designs, accepted tradeoffs, and routed decisions

## MVP decisions

- One shared backend and schema; a card derives language and ownership through its owned deck.
- Target languages are `en` and `ja`; explanation languages are `en`, `ja`, and `zh-TW`.
- Each card has one meaning language, one optional embedded example, and embedded synonym/antonym
  arrays. Tags remain reusable user-owned resources.
- Cards/decks archive; tags and their associations can be permanently deleted.
- Cross-owner lookup returns the same non-disclosing 404 as a missing resource.
- PostgreSQL generates UUIDs for client-addressable resources and identity `BIGINT`s for internal
  records.
- PostgreSQL stores `timestamptz`; the backend clock is authoritative; review days use
  `Asia/Taipei` with a midnight boundary.
- The five-stage review model is preserved while the reversed ease-factor argument bug is corrected.
- Due retrieval returns at most 10 cards. Review submission is an atomic, idempotent batch of 1-10
  decisions protected by expected review-state versions.
- All 21 current Sheet fields have an explicit destination, derived behavior, or removal decision.
- AI integration, queues, sharing, multiple examples/explanations, per-user timezones, and a new
  scheduling algorithm are outside the database-backed MVP.

## Acceptance status

- [x] Shared language-aware backend direction
- [x] Authenticated identity and backend ownership boundary
- [x] AI draft/confirmation safety boundary
- [x] Primary business invariants and ownership rules
- [x] All 21 current Sheet fields mapped
- [x] Failure and recovery expectations
- [x] MVP `/v1` API and stable error envelope
- [x] Schema proposal and diagrams
- [x] Alternatives, tradeoffs, and unresolved decisions
- [x] Design-defense explanation without generated notes

## Verification and evidence status

- The documents passed a final cross-document consistency review and `git diff --check`.
- No backend code, Alembic migration, PostgreSQL integration test, or production outcome exists yet.
- This is training design evidence, not implementation or professional production-service evidence.
- Formal GitHub issue closure was not performed in the design session.

## Next action

Route the implementation-area choices in [alternatives.md](alternatives.md) into later ticket
acceptance criteria, verify formal GitHub status for Issues #4 and #5, and continue the next Week 0
ticket before backend scaffolding.
