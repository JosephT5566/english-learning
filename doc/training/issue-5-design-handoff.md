# Issue #5 Design Handoff

- Date: 2026-08-29
- Status: Design in progress; no backend implementation has started
- Ticket outcome: Produce a defensible English and Japanese learning design before backend implementation

## How to resume

Continue in interactive design-coaching mode, one substantial decision at a time. Joseph should
state the reasoning first; then challenge gaps and refine it into documented requirements. Do not
start backend scaffolding yet.

The next unanswered question is:

> If an authenticated user guesses a valid card ID owned by another user, should the API return
> `403 Forbidden` or behave as though the card does not exist with `404 Not Found`? Consider
> whether confirming that another user's card exists leaks information.

## Dependency and repository state

- Issue #4 is documented in [`current-state-flow-trace.md`](current-state-flow-trace.md).
- Its documented acceptance criteria are checked, although formal ticket closure was not verified
  during this session.
- The important migration risk inherited from #4 is that the current browser selects card IDs and
  calculates scheduling fields. The future backend must verify ownership, accept the review
  decision, calculate the transition server-side, and persist current state and history atomically.
- No backend code or schema has been created for issue #5.

## Decisions made so far

### English review behavior

- Preserve the current English flip-then-answer user experience.
- The flip requirement is a frontend interaction rule, not a backend security invariant.
- After review submission, the backend should update current review state and append immutable
  review history for each reviewed card.
- The client should submit the answer or review decision rather than calculated schedule fields.
- The backend must calculate the new schedule and write the review event and current state in one
  transaction.
- Retrying the same logical submission must not create a second review event.
- A failed transaction must not leave history and current state partially updated.

### Languages, decks, and review selection

- English and Japanese use the same backend concepts, tables, ownership rules, APIs, and review
  behavior.
- A deck is a user-owned collection of cards. The current Sheet-backed application can be treated
  as having one implicit English deck.
- A user may have multiple decks under the same language, such as `Japanese N5` and
  `Restaurant Japanese`.
- Each deck has exactly one target language.
- Each card belongs to exactly one deck and derives its target language from that deck.
- A user can start a review using one deck, several decks, or all active decks in one language.
- Mixed-language review selection has not been requested; the current design keeps a review
  selection within one target language.
- "All decks" is a query scope, not a special database deck.
- Due-card retrieval returns only active, due cards from active decks owned by the authenticated
  user.
- A successful selection with no due cards returns an empty result rather than an error.

### Japanese card content

Japanese cards use the shared card model and support:

- term or kanji;
- kana reading;
- optional romanization;
- meaning;
- part of speech;
- examples.

These requirements must not produce Japanese-specific card, review, or history tables. The exact
required/optional field constraints still need to be designed.

### Duplicate-term policy

- Duplicate terms are allowed within the same deck and across different decks.
- Joseph's reason: the same written term can have different meanings in different contexts.
- A card is identified by a stable card ID, not by its term.
- Matching terms can have independent meanings, examples, notes, review state, and history.
- Normalization may support search and duplicate warnings, but it must not impose term uniqueness.
- A possible-duplicate warning may be shown, but the user can still create the card.
- Sheet migration must not merge rows merely because their terms match.
- The accepted tradeoff is that exact accidental duplicates are possible in order to preserve
  legitimate contextual cards.

### Archiving and deletion

- User-facing deletion archives cards and decks; it does not physically erase them.
- Archived cards are excluded from normal lists and due reviews.
- Card review state and immutable review history are retained.
- Owners can list and restore archived cards.
- Repeated archive requests should be idempotent.
- A review submitted after its card or deck was archived should fail as a conflict without changing
  review state or history.
- Permanently deleting cards or decks is not part of the first version.
- Archiving a deck makes its cards unavailable for review without changing every card's individual
  archival state.
- Restoring a deck makes its active cards available again, while cards that were individually
  archived remain archived.
- The proposed representation is an `archived_at` timestamp rather than only a boolean.

### Ownership and authorization

- The first version is private and has no sharing, collaboration, or ownership transfer.
- Every deck belongs to exactly one authenticated user.
- Cards inherit ownership through their deck.
- Examples and review state inherit ownership through their card.
- Tags belong to one user and cannot be attached to another user's cards.
- Only the owner can view or modify their decks, cards, tags, review state, or review history.
- The backend derives current identity from a server-verified Google token.
- API inputs cannot choose `owner_id`, email, or another ownership identity.
- Every submitted resource ID is untrusted and every query must enforce the authenticated ownership
  boundary.
- Frontend visibility checks are user experience only; backend authorization is authoritative.

### AI scope

- AI generation will not be implemented in the first database-backed version.
- Issue #5 must still define the future conceptual boundary so the model and API do not bypass it:

  `generation request -> validated editable draft -> explicit confirmation -> learning card`

- AI output must never directly create or overwrite a confirmed learning card.
- Provider and model selection remain out of scope.

## Functional areas still to document

The initial API design is expected to cover authenticated users being able to:

- list and create decks;
- create, view, edit, list/filter, archive, and restore cards;
- add and remove tags;
- retrieve due cards using the selected review scope;
- submit review answers safely;
- view review history;
- handle empty, validation, unauthenticated, unauthorized, conflict, retryable, and server-error
  outcomes.

These are working requirements, not yet a completed API contract.

## Remaining ticket decisions

- Whether unauthorized resource lookup returns `403` or non-disclosing `404`.
- Exact supported language-code format, including explanation language.
- ID format and where IDs are generated.
- Timestamp format, timezone rules, and server/client clock authority.
- Exact Japanese field validation, including when kana reading is required.
- Deck, card, example, tag, review-state, and review-event schema details and invariants.
- Tag normalization and uniqueness behavior.
- Review scheduling compatibility versus correction of current behavior.
- Review submission granularity, idempotency, and concurrency behavior.
- List filtering, deterministic ordering, and pagination.
- Stable `/v1` endpoint request and response contracts.
- Stable error envelope and machine-readable error codes.
- Failure and recovery behavior for every important operation.
- Complete mapping or removal decision for all 21 existing Sheet fields.
- Proposed request-flow and trust-boundary diagrams.
- Detailed AI draft lifecycle, validation, stale-edit, late-result, and repeated-confirmation behavior.
- Meaningful alternatives, tradeoffs, and genuinely unresolved decisions.

## Ticket acceptance status

- [x] Direction chosen: one shared language-aware backend model, not separate language applications.
- [x] API identity and ownership must come from verified authentication, not request input.
- [x] AI output cannot directly create a confirmed card.
- [ ] Complete primary business invariants and ownership rules.
- [ ] Map every current Sheet field.
- [ ] Complete failure behavior and recovery expectations.
- [ ] Draft the `/v1` API and stable error envelope.
- [ ] Check in the schema proposal and diagrams.
- [ ] Record alternatives and unresolved decisions.
- [ ] Verify Joseph can explain the design and a credible alternative without generated notes.

## Reasoning Joseph should retain

- Decks make language-specific collections explicit without creating language-specific tables.
- A card derives language and ownership through its deck, which prevents conflicting client-selected
  values.
- Allowing duplicate terms preserves separate contextual meanings and independent learning progress.
- Archiving retains learning history and supports recovery while excluding inactive content from
  review.
- Backend ownership checks are required even when the frontend hides inaccessible resources.
- Review events and current review state must change together so history cannot disagree with the
  current schedule.

