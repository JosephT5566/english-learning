# Issue #5 Detailed Design

- Date: 2026-08-29
- Status: Design complete; no backend implementation started; formal GitHub closure not verified
- Ticket outcome: Produce a defensible English and Japanese learning design before backend implementation

## How to resume

Continue in interactive design-coaching mode, one substantial decision at a time. Joseph should
state the reasoning first; then challenge gaps and refine it into documented requirements. Do not
start backend scaffolding yet.

The next unanswered question is:

> Which later ticket should receive each implementation-area unresolved decision before backend
> code begins?

## Dependency and repository state

- Issue #4 is documented in [`current-state-flow-trace.md`](current-state-flow-trace.md).
- Its documented acceptance criteria are checked, although formal ticket closure was not verified
  during this session.
- The important migration risk inherited from #4 is that the current browser selects card IDs and
  calculates scheduling fields. The future backend must verify ownership, accept the review
  decision, calculate the transition server-side, and persist current state and history atomically.
- No backend code or schema has been created for issue #5.
- The approved design schema is checked in as
  [`schema.md`](schema.md); no migration or backend code exists yet.

## Decisions made so far

### MVP scope filter

- The first database-backed version prioritizes the existing card-management and flip/answer review
  flow plus required ownership, validation, transaction, retry, migration, and recovery guarantees.
- Defer convenience features and abstractions without demonstrated first-version value, including
  sharing, card movement, multiple explanations, multiple examples, related-term child resources,
  review reservations, persisted review sessions, per-user timezones, and a new scheduling model.
- Future AI behavior is documented only far enough to preserve a safe draft/confirmation boundary;
  provider integration and generation are not implemented in the first database-backed version.
- MVP simplification must not weaken authentication, ownership, database integrity, atomic review
  transitions, idempotency, migration diagnostics, or recovery behavior.

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
- A review submission contains a bounded batch of card decisions rather than requiring one HTTP
  request per card. This preserves the current submit-results workflow and reduces request overhead.
- Each batch item supplies a card ID and review decision, not calculated scheduling fields.
- Duplicate card IDs within one batch are invalid because their order would otherwise affect the
  resulting state.
- A review batch is all-or-nothing. The backend validates ownership, active state, submitted
  decisions, and concurrency preconditions for every item before committing their review events and
  current-state transitions in one database transaction.
- If any item is invalid, archived, missing or not owned, stale, or otherwise conflicts, no item in
  the batch changes and no review event is appended.
- The accepted tradeoff is that one exceptional item can require the otherwise valid batch to be
  corrected and resubmitted. Normal review batches are expected to contain valid items, and the
  simpler single transaction outcome is preferred over partial-result reconciliation.
- The error identifies the failing item when doing so does not violate the non-disclosing ownership
  rule.
- A review batch contains at least one and at most 10 card decisions. Empty batches and batches with
  more than 10 items fail boundary validation before card locks or state transitions begin.

### Review batch idempotency and concurrency process

- `POST /v1/reviews` requires an `Idempotency-Key` header containing a client-generated UUID. This
  is a command identifier, not a persistent entity ID, so it is an intentional exception to the
  rule that clients do not generate entity IDs.
- The browser generates the key when the user first submits results, persists it with the pending
  request, and reuses the same key and exact body after a timeout or network failure. A genuinely
  new logical submission receives a new key.
- Each item contains `card_id`, a review `decision`, and the `expected_version` of the current review
  state. The client cannot submit resulting stages, factors, intervals, or timestamps.
- A `review_batches` row stores a PostgreSQL-generated UUID `id`, `owner_id`, the client
  `idempotency_key`, a canonical `request_hash`, authoritative `reviewed_at`, `algorithm_version`,
  `item_count`, and `created_at`.
- PostgreSQL enforces `UNIQUE (owner_id, idempotency_key)`. The same key may therefore be used by
  different users without collision, but only once for one authenticated user.
- Each immutable review event references `batch_id`. PostgreSQL also enforces one event per card in
  a batch, such as with `UNIQUE (batch_id, card_id)`.
- The request hash covers the normalized validated batch content, including card IDs, decisions,
  and expected versions. It excludes the authentication token and changing transport metadata.

The new-key process is:

1. Authenticate the user and validate request shape, uniqueness of card IDs, and batch size.
2. Begin one transaction and insert the `review_batches` row.
3. Load and lock all submitted card review states in deterministic card-ID order.
4. Verify every card's ownership, active card and deck state, decision, and `expected_version`.
5. Capture one backend-authoritative `reviewed_at` and calculate every transition.
6. Insert all immutable review events and update all current review states.
7. Commit the batch row, events, and states together, then return the committed batch result.

Retry and failure behavior is:

- Same owner, same key, and same request hash: return the original committed result without another
  transition or event.
- Same owner and key but a different request hash: return `409 Conflict` with
  `idempotency_key_reused`.
- Crash or error before commit: the batch row, events, and state updates roll back; retrying can
  execute normally.
- Commit succeeds but the response is lost: the retry finds the committed batch and reconstructs
  the original result from the batch and review events.
- Validation or state-conflict failures are not retained as completed batch rows. After correction,
  the client sends a new logical submission with a new key.
- Different keys do not identify a retry. If concurrent batches overlap, locks serialize their
  checks; the first valid transaction to commit advances the version, and a later batch with the
  old `expected_version` fails the entire batch with a stale-state conflict and writes nothing.
- `review_batches` is durable review history and is retained with its review events rather than
  expiring like a short-lived HTTP response cache.

### Due-review retrieval contract

- `GET /v1/reviews/due` requires `target_language`, accepts zero to 20 repeated `deck_id` filters,
  and uses the approved `limit` and cursor parameters. Omitting deck IDs means all active owned
  decks in the requested language.
- Explicit deck IDs must be unique, owned, active, and match the requested language. Missing or
  cross-owner decks return non-disclosing `deck_not_found`; archived scope returns
  `review_scope_inactive`; invalid combinations fail validation.
- The backend captures one authoritative `as_of` instant on the first page and binds it, the owner,
  target language, sorted deck scope, limit, and ordering into the cursor query shape.
- Eligibility requires an active owned card in an active matching deck with
  `next_review_at <= as_of`. Clients cannot supply owner, email, stage, due time, or current time.
- Results use `next_review_at ASC, card_id ASC` and return at most 10 complete review-ready cards,
  including deck summary, card content, embedded example, synonym/antonym arrays, tags, and current
  review state with its version.
- An empty selection returns `200 OK` with `items: []` and `next_cursor: null`.
- Retrieval is read-only: it creates no persisted session, reservation, or post-query lock and does
  not guarantee that versions remain current until submission.
- Staleness between retrieval and submission is handled by each item's `expected_version` and the
  atomic review conflict rules.
- Although a cursor may continue the snapshot, the client should normally fetch a fresh first page
  after a successful batch because the write changed due eligibility.
- Failure categories follow the stable envelope: 400 invalid query/cursor, 401 authentication, 404
  non-disclosing deck lookup, 409 inactive explicit scope, 422 invalid language/scope, and retryable
  503 database unavailability.

### Atomic review-submission contract

- `POST /v1/reviews` requires authentication, a UUID `Idempotency-Key`, and 1-10 unique items with
  `card_id`, `decision`, and positive `expected_version`. Unknown or server-controlled scheduling,
  identity, timestamp, and algorithm fields are rejected.
- Decisions are `no`, `no_a_bit`, `yes_a_bit`, or `yes`. Duplicate card IDs and invalid items return
  field-specific `422 validation_failed`; a missing/malformed idempotency header returns
  `400 invalid_idempotency_key`.
- The original successful command and a same-key/same-hash replay both return `200 OK` with the same
  committed body: batch ID, one authoritative `reviewed_at`, algorithm version, and items in request
  order containing decision, event ID, previous review state, and resulting review state.
- Database locks are still acquired in deterministic card-ID order; response order does not control
  lock order.
- One backend clock read supplies `reviewed_at` for every item in the batch and deterministic tests
  can inject that time.
- Same owner/key with different content returns `409 idempotency_key_reused` without disclosing the
  original body.
- Any stale owned state returns `409 stale_review_state` with safe item index, card ID, expected
  version, and current version; the whole batch rolls back. The client refetches and creates a new
  logical submission rather than blindly replacing the version on an old decision.
- An owned card or deck archived before the review locks/validates returns
  `409 review_target_inactive` with safe item context and rolls back. If review commits before a
  competing archive, that review is valid and the archive follows it.
- Missing or cross-owner cards return the same `404 card_not_found` without item index, ownership,
  state, version, or existence clues.
- Temporary transaction exhaustion returns retryable `503 review_temporarily_unavailable`, may set
  `Retry-After`, and requires the exact same key/body retry. Bounded internal retries may handle
  transient deadlock or serialization failures first.
- Every pre-commit failure leaves no completed batch, events, or state changes. A lost post-commit
  response is recovered through the committed idempotency record.
- No persisted review-session or separate batch-status API is required for the MVP.

### Review-history contract

- `GET /v1/reviews/history` returns a flat immutable event list and supports the approved `card_id`,
  `deck_id`, `target_language`, `decision`, `reviewed_from`, `reviewed_to`, and `batch_id` filters.
  Filters combine with AND.
- Time bounds are RFC 3339, with inclusive `reviewed_from` and exclusive `reviewed_to`; invalid or
  reversed ranges return field validation errors.
- Results use `reviewed_at DESC, id DESC`, default to 20, permit at most 100, and bind owner, filters,
  limit, and last sort tuple into the cursor.
- Each item uses the same transition shape as review submission: event and batch IDs, current card
  summary, decision/quality, reviewed time, algorithm version, and complete previous/resulting
  scheduling states.
- Review events store `previous_last_reviewed_at` and `resulting_last_reviewed_at` in addition to the
  previously approved state snapshots; resulting last-review time equals event `reviewed_at`. This
  closes the schema gap that would otherwise prevent exact replay reconstruction.
- Card term and archival metadata in the response are current card metadata, not historical content
  snapshots. Scheduling transitions remain immutable; full content-version history is outside MVP.
- History remains visible after card/deck archive and tag deletion.
- Supplied missing or cross-owner card, deck, or batch filters return the matching non-disclosing
  `404`; a valid owned filter with no events returns `200` and an empty collection.
- Internal owner identity, Google claims, idempotency key, request hash, and transaction metadata are
  not returned.
- CSV export, aggregates, streaks, charts, event mutation/deletion, historical content snapshots,
  cross-user access, and arbitrary sorting are outside MVP.

### Review scheduling compatibility and correction

- Preserve the recognizable five-stage model, answer qualities, and base intervals for the first
  backend version rather than introducing a new spaced-repetition algorithm during migration.
- The four current decisions remain quality `0` (no), `2` (no, a bit), `3` (yes, a bit), and `5`
  (yes). A no decision moves down one stage, a yes decision moves up one stage, and the result is
  clamped to stages 1 through 5.
- Preserve the current base interval sequence of 1, 3, 7, 14, and 30 days and the ease-factor range
  of 1.3 through 2.5. Future backend transitions calculate the interval from the corrected
  algorithm and apply the agreed Taiwan calendar-day and midnight rules.
- The current frontend contains a confirmed argument-order bug: `calNewEaseFactor()` is declared as
  `(quality, currentEaseFactor)` but `SwipeCards.svelte` calls it as
  `(currentWord.easeFactor, quality)`. The executed browser behavior therefore treats the previous
  ease factor as answer quality and the answer quality as the previous ease factor, often causing
  unintended clamping and transitions.
- The backend must call the calculation with the intended argument meanings and must not reproduce
  the reversed-argument defect for compatibility.
- Valid imported `reviewStage`, `easeFactor`, `lastReview`, and `nextReview` values are preserved as
  the initial state. Past schedules are not retroactively recalculated merely because the old
  client contained the bug.
- Invalid or out-of-range imported scheduling values require explicit migration diagnostics and a
  later repair policy; they must not be silently accepted or corrected.
- The first review submitted through the new backend transitions from the imported current state
  using the corrected server-side algorithm. Each event records enough previous and resulting state
  to explain the transition.
- Algorithm identity or version must be retained with review history so a future scheduling change
  does not silently reinterpret earlier events.
- The backend also corrects the current trust and persistence weaknesses: clients submit decisions,
  the backend clock controls time, `interval_days` stays consistent, and the event plus current state
  are written atomically with idempotency and concurrency protection.

### Languages, decks, and review selection

- English and Japanese use the same backend concepts, tables, ownership rules, APIs, and review
  behavior.
- A deck is a user-owned collection of cards. The current Sheet-backed application can be treated
  as having one implicit English deck.
- A user may have multiple decks under the same language, such as `Japanese N5` and
  `Restaurant Japanese`.
- Each deck has exactly one target language.
- Each deck also has exactly one explanation language.
- Each card belongs to exactly one deck and derives its target language from that deck.
- Each card also derives its explanation language from its deck; card creation and editing cannot
  supply conflicting language values.
- Language identifiers use BCP 47 language tags rather than UI labels.
- The first version allowlists `en` and `ja` as target languages and `en`, `ja`, and `zh-TW` as
  explanation languages. A well-formed but unsupported language tag is rejected rather than
  silently accepted.
- Target and explanation languages can be chosen while creating a deck. Changing either language
  after the deck contains cards is rejected as a conflict because existing content and validation
  rules would otherwise be mislabeled.
- A card has one structured meaning in the deck's explanation language. Multiple structured
  translations per card are outside the first version.
- A separate optional free-form card note can store supplemental context. Notes do not change the
  deck's explanation language and are not treated as a second structured translation.
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
- one optional example.

The term and meaning are required. Kana reading is optional for every Japanese card, including a
term containing kanji; the user decides whether a reading is useful for learning. Romanization,
part of speech, one example, and notes are also optional. A missing reading does not prevent card
creation or confirmation.

When a reading is provided, it is a kana pronunciation field rather than unrestricted text. The
backend trims it, normalizes its Unicode representation, requires at least one hiragana or katakana
character, and rejects kanji. Hiragana, katakana, common kana pronunciation marks, spaces, and
limited punctuation are allowed. Supplemental guidance that does not fit this contract belongs in
the card note. Romanization is separate and cannot substitute for or be stored as the kana reading.

These requirements must not produce Japanese-specific card, review, or history tables.

### Field and collection limits

- Limits apply after trimming and the field's documented Unicode normalization. They measure
  characters rather than UTF-8 bytes so multilingual content does not receive a smaller effective
  limit.
- Deck title is required and limited to 100 characters.
- Card term is required and limited to 255 characters; meaning is required and limited to 2,000.
- Optional reading and romanization are each limited to 255 characters, part of speech to 50, and
  card note to 4,000.
- Optional part-of-speech detail is limited to 100 characters.
- `synonyms` and `antonyms` are ordered card arrays with at most 20 entries each; every entry is
  trimmed, nonempty, unique within its normalized list, and limited to 255 characters.
- A card's optional example uses `example_sentence`, `example_translation`, and `example_source`.
  Sentence and translation are each limited to 1,000 characters and source to 500.
- Tag display name is required and limited to 50 characters. Its separately stored normalized key
  is limited to 100 to allow for normalization or case-fold expansion.
- Card-list search query input is limited to 200 characters.
- Required strings that are blank after normalization fail validation. Optional blank strings
  normalize to null. Surrounding whitespace is trimmed; meaningful internal whitespace and allowed
  line breaks in notes and the example are preserved.
- A card may have at most 20 attached tags.
- No arbitrary first-version cap is placed on cards per deck or decks/tags per user. Pagination and
  appropriate request rate controls protect operations without inventing unsupported product quotas.
- API validation returns field-specific `required`, `too_long`, or `too_many_items` details, while
  named PostgreSQL `char_length` checks and relationship invariants remain the final boundary.
- Tag attachment enforces the relationship count transactionally, such as by locking the parent
  card, so concurrent requests cannot exceed the cap.

### Complete Google Sheet field mapping

The importer preserves meaningful content and source evidence without treating legacy identifiers,
stale calculations, or formulas as authoritative PostgreSQL state.

| Sheet field | Database mapping or removal decision |
| --- | --- |
| `id` | Preserve as `import_items.source_record_id`; generate a new card UUID |
| `lessonDate` | Convert to nullable `learning_cards.learned_on` using its `Asia/Taipei` calendar date |
| `content` | Required `learning_cards.term` |
| `type` | Map recognized values to canonical `part_of_speech`; preserve unknown text as `other` detail with a diagnostic |
| `phonics` | Nullable shared `learning_cards.pronunciation` |
| `chineseExplain` | Required `learning_cards.meaning` for the implicit English/`zh-TW` deck |
| `engExplain` | Nullable shared `learning_cards.target_language_definition` |
| `synonyms` | Split into the ordered `learning_cards.synonyms` text array |
| `antonyms` | Split into the ordered `learning_cards.antonyms` text array |
| `tags` | Normalize into owned `tags` and `learning_card_tags` associations |
| `note` | Nullable free-form `learning_cards.note` |
| `supplementary` | Nullable shared `learning_cards.supplementary_note` |
| `example` | Nullable `learning_cards.example_sentence`; translation/source remain null for legacy rows |
| `status` | Recognized inactive/deleted values set card `archived_at`; active maps to null |
| `reviewStage` | Valid integer 1-5 maps to `review_states.review_stage` |
| `easeFactor` | Valid number 1.3-2.5 maps to `review_states.ease_factor` |
| `intervalDays` | Preserve as import evidence; derive authoritative applied interval from valid review timestamps |
| `lastReview` | Nullable `review_states.last_reviewed_at` `timestamptz` |
| `nextReview` | Valid value becomes required `review_states.next_review_at`; blank unreviewed rows initialize it to import time with a diagnostic |
| `createdDate` | Valid source time becomes `learning_cards.created_at`; fallback requires a diagnostic |
| `overdueDays` | Preserve only as import evidence; derive due state at query time and do not store it |

Mapping and validation rules are:

- Import identity uses a stable source namespace plus source record ID, with a uniqueness constraint
  and a recorded mapping to the generated card UUID. Missing or duplicate source IDs reject rows.
- The implicit migrated deck uses target language `en` and explanation language `zh-TW`.
- `target_language_definition` preserves a monolingual definition in the deck's target language;
  it is not a second structured explanation-language meaning.
- `pronunciation`, `target_language_definition`, `supplementary_note`, `learned_on`, and ordered
  synonym/antonym arrays are shared multilingual concepts, not English-specific tables or columns.
- The first version stores one example directly on its card through nullable `example_sentence`,
  `example_translation`, and `example_source` fields. If translation or source is present, sentence
  must also be present.
- Legacy comma-separated synonyms and antonyms become ordered card arrays; tags become normalized
  tag/association rows. Raw values remain in import evidence. Empty split items and normalization
  changes produce diagnostics; limits are never enforced by silently dropping entries.
- Recognized `active` status maps to null `archived_at`. Recognized `inactive` or `deleted` uses the
  import timestamp because the source has no trustworthy archive time. Unknown statuses require
  explicit repair rather than silently becoming active.
- `intervalDays` is known to become stale because the current update payload does not write it. When
  valid last/next timestamps exist, derive the applied interval from their Taiwan calendar dates and
  report disagreement with the raw value. An unreviewed card with neither timestamp starts at zero;
  incomplete or contradictory timestamp combinations require repair.
- Valid imported `nextReview` instants are not retroactively moved to midnight. The agreed midnight
  rule applies after the first new-backend transition.
- A blank `nextReview` on an otherwise valid unreviewed row initializes required `next_review_at` to
  the import time and records that non-source value in diagnostics, matching the schema proposal.
- `overdueDays` remains derived from authoritative time, `next_review_at`, and Taiwan calendar rules.
- A nonempty malformed date, invalid stage/ease factor, missing required term/meaning, unknown status,
  excess structured entries, or contradictory review state is rejected or marked `needs_repair`; it
  is never silently clamped or discarded.
- Each import item records exactly one outcome such as `created`, `skipped_unchanged`, `updated`,
  `rejected`, or `needs_repair`, with row-level diagnostics for every nontrivial conversion.

### Schema proposal

- Exact approved tables, columns, types, keys, checks, indexes, deletion policies, and
  transaction-enforced invariants are documented in
  [`schema.md`](schema.md).
- Owned composite foreign keys use constrained redundant `owner_id` values where necessary to make
  cross-user card/tag/batch/event relationships impossible at the database boundary.
- New cards initialize an immediately due review state using backend creation time as
  `next_review_at`.
- Synonyms and antonyms are ordered card arrays with at most 20 entries each and use card PATCH plus
  the card content version rather than independent child identities or lifecycles.
- The schema remains a design proposal until implemented through Alembic and verified by PostgreSQL
  integration tests.

### Failure and recovery

- The approved operation matrix is checked in as
  [`failure-recovery.md`](failure-recovery.md).
- Deck and card API creation require UUID idempotency keys and store paired creation request hashes
  so ambiguous committed creates cannot duplicate resources. Imports may leave this metadata null.
- PATCH recovery uses refetch-and-compare rather than blind retry against a stale version.
- Reads, desired-state commands, creates, and review submission have explicitly classified safe
  retry behavior; validation, stale state, conflicts, and authentication failures require correction
  or recovery first.
- Card creation plus initial review state, tag deletion plus association/card-version updates, and
  complete review batches have explicit all-or-nothing transaction guarantees.
- Failure logs correlate through request IDs without tokens, credentials, connection strings, or
  private card content by default.

### Request flows and trust boundaries

- Approved Mermaid diagrams are checked in as
  [`request-flows.md`](request-flows.md).
- The runtime diagram separates the untrusted browser, external Google identity provider, backend
  authentication/ownership/domain boundary, PostgreSQL integrity boundary, and safe logs.
- The owned-mutation sequence shows creation idempotency, optimistic updates, archive/restore, tag
  transactions, rollback, and stable responses.
- The review sequence shows authentication, idempotency resolution, deterministic locks, ownership
  and version checks, one authoritative clock read, atomic events/state writes, rollback, and replay
  after a lost response.
- AI provider, queue, deployment, and migration execution are deliberately excluded from the MVP
  runtime diagrams so planned behavior is not presented as implemented architecture.

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

### Part-of-speech representation

- Cards use a hybrid representation: optional `part_of_speech` is a controlled language-neutral
  code, while optional `part_of_speech_detail` preserves language-specific or contextual grammar.
- Initial canonical codes are `noun`, `verb`, `adjective`, `adverb`, `pronoun`, `determiner`,
  `preposition`, `conjunction`, `interjection`, `particle`, `auxiliary`, `numeral`, `phrase`, and
  `other`.
- Canonical codes are stable API values and are not localized storage labels. The frontend may
  display translated labels such as `Verb` or `動詞`.
- `part_of_speech_detail` is trimmed free-form text with a 100-character limit. When the canonical
  code is `other`, a nonempty detail is required.
- The first version records one primary part of speech per contextual card. A term serving different
  grammatical roles may use separate cards, consistent with the duplicate-term policy.
- Recognized legacy Sheet `type` values map to canonical codes. Unrecognized nonempty values map to
  `other`, retain the original value in `part_of_speech_detail`, and produce an import diagnostic
  rather than being discarded.
- Future AI drafts may propose only allowlisted canonical codes; detail remains untrusted text and
  passes normal validation before confirmation.

### Tag normalization and uniqueness

- Tags are user-owned and shared across that user's decks and target languages; they are not scoped
  to one deck or language.
- Tag identity is insensitive to letter case and surrounding whitespace. For one user, `JLPT`,
  `jlpt`, and ` jlpt ` refer to the same tag.
- The backend trims the submitted name, applies a documented Unicode normalization and case-folding
  rule, and stores a normalized key separately from the display name.
- PostgreSQL enforces `UNIQUE (owner_id, normalized_name)` so retries and concurrent requests cannot
  create duplicate normalized tags.
- Different users may independently use the same normalized tag name.
- Creating a tag whose normalized identity already exists should return or reuse the existing owned
  tag rather than create another row. Renaming a tag to collide with another owned tag fails with a
  conflict; automatic merging is out of scope.
- Empty or whitespace-only tag names are rejected.
- Deleting a tag permanently removes the owned tag row and all of its card-tag associations in one
  transaction. Tags are organizational metadata and are not retained as learning or review history.
- PostgreSQL foreign-key cascade may remove `learning_card_tags` rows, but no card, example, review
  state, or review event is deleted.
- The operation locks or otherwise protects affected relationships consistently and increments the
  content version of affected cards because their returned tag collections changed. This does not
  change their independent review-state versions.
- The deleted normalized name becomes available for immediate reuse. Tag deletion has no restore
  operation and the UI must present it as irreversible.
- Deleting one card-tag association remains an idempotent unlink operation and does not delete the
  shared tag resource.

### List pagination

- Card, review-history, and other potentially growing `/v1` collection endpoints use cursor
  pagination rather than page-number or offset pagination.
- The cursor is opaque to clients and represents the last deterministic sort tuple returned by the
  server. Every ordering includes a unique stable ID as its final tie-breaker.
- A successful page returns its items and a `next_cursor`; `next_cursor` is null when there is no
  following page.
- Clients must resend the same filters and ordering when following a cursor. A malformed cursor or
  one incompatible with the requested list shape returns a boundary-validation error.
- Card management defaults to `updated_at DESC, id DESC`, showing the most recently changed cards
  first with card UUID as the deterministic tie-breaker.
- Review history defaults to `reviewed_at DESC, id DESC`, showing the newest event first with its
  identity `BIGINT` as the deterministic tie-breaker.
- Due review retrieval uses `next_review_at ASC, card_id ASC`, showing the most overdue or earliest
  due card first with card UUID as the deterministic tie-breaker.
- The card list supports `deck_id`, `target_language`, `status`, `tag_id`, and `query` filters.
  `status` accepts `active`, `archived`, or `all` and defaults to `active`. `query` performs ordinary
  normalized substring matching over term, meaning, and optional reading; it is not semantic search.
- Review history supports `card_id`, `deck_id`, `target_language`, `decision`, `reviewed_from`,
  `reviewed_to`, and `batch_id`. The lower time boundary is inclusive and the upper boundary is
  exclusive: `reviewed_at >= reviewed_from AND reviewed_at < reviewed_to`.
- Supplied filters combine with logical AND. The first version accepts one `deck_id` and one
  `tag_id` per card-list request rather than multi-ID and any/all tag query modes.
- Ownership is always derived from authentication and there is no `owner_id` filter. Submitted
  resource filters enforce the non-disclosing ownership rule.
- Unknown filters and unsupported combinations are rejected rather than silently ignored.
- Cursors are bound to the normalized filter and ordering shape and cannot be reused after those
  parameters change.
- Due-review selection remains a separate endpoint using one target language and the already agreed
  selected-deck scope.
- Ordinary management and history collections default to 20 items and accept `limit` values from 1
  through 100. This applies to card, review-history, deck, and tag lists.
- Due-review retrieval defaults to and permits at most 10 cards, matching the maximum atomic review
  submission batch so one fetched review set does not need to be split across transactions.
- An omitted `limit` uses the endpoint default. A non-integer, zero, negative, or above-maximum
  value returns a boundary-validation error rather than being silently clamped.
- A page may validly contain fewer items than requested. An empty terminal page returns an empty
  `items` array and `next_cursor: null`.
- The effective `limit` is part of the cursor query shape and cannot change while following that
  cursor.

### Stable `/v1` error and response contract

- Every `/v1` error uses `{ "error": { "code", "message", "retryable", "request_id", "details"? } }`.
  `code`, `message`, `retryable`, and `request_id` are always present; safe code-specific `details`
  is optional.
- Frontend behavior depends on stable machine-readable `code` values, never comparisons against the
  human-readable fallback `message`.
- The backend generates a new request UUID for every HTTP request, returns it in `error.request_id`
  and the `X-Request-ID` response header, and includes it in structured logs. It is unrelated to an
  idempotency key.
- `400 Bad Request` covers an uninterpretable request or query with codes such as `malformed_json`,
  `invalid_query_parameter`, `invalid_cursor`, and `unsupported_filter`.
- `401 Unauthorized` covers missing, invalid, or expired authentication with
  `authentication_required`, `invalid_token`, or `expired_token`.
- `403 Forbidden` is reserved for intentionally visible resources whose operation is prohibited,
  using `operation_forbidden`; it is expected to be uncommon in the private first version.
- `404 Not Found` uses resource codes such as `deck_not_found`, `card_not_found`, `tag_not_found`,
  `review_batch_not_found`, and `draft_not_found`. The same response is used for nonexistent and
  cross-owner resources.
- `409 Conflict` covers valid commands conflicting with durable state, including
  `stale_review_state`, `review_target_inactive`, `idempotency_key_reused`, `tag_name_conflict`,
  `deck_language_locked`, and future `draft_already_confirmed`.
- `422 Unprocessable Content` uses `validation_failed` with optional `details.fields` entries. Each
  entry contains a field `path`, stable field-level `code`, and fallback `message`. Initial field
  codes include `required`, `too_short`, `too_long`, `invalid_format`, `invalid_choice`, `duplicate`,
  `too_many_items`, and `unsupported_language`.
- `429 Too Many Requests` uses `rate_limited`, `retryable: true`, and a `Retry-After` header.
- `500 Internal Server Error` uses generic `internal_error`; `503 Service Unavailable` uses
  `service_unavailable` or `database_unavailable`. Retryable temporary failures may include
  `Retry-After`.
- Internal exceptions, SQL, stack traces, schema names, credentials, and tokens are never returned.
- Batch error details identify an item only when safe. An inaccessible card returns the
  non-disclosing `card_not_found` response without owner, deck, state, version, or existence clues.
- A stale owned card may safely include its item index, card ID, expected version, and current
  version so the client can refresh before creating a new logical submission.
- Successful resources are returned directly rather than under a universal `data` wrapper.
  Successful collections consistently return `{ "items": [...], "next_cursor": ... }`.

### Deck and card write contracts

Deck resources expose `GET /v1/decks`, `POST /v1/decks`, `GET /v1/decks/{deck_id}`,
`PATCH /v1/decks/{deck_id}`, `DELETE /v1/decks/{deck_id}`, and
`POST /v1/decks/{deck_id}/restore`.

- Deck creation accepts only `title`, `target_language`, and `explanation_language`; ownership, ID,
  version, timestamps, and archive state are server-controlled. It requires a UUID
  `Idempotency-Key` and returns the same `201 Created`, `Location`, and complete resource on a
  same-key/same-hash replay.
- Deck titles are trimmed and nonempty. Duplicate titles are allowed.
- Deck PATCH is partial, rejects unknown fields and an empty body, and uses `If-Match` with the
  current content version. Success returns the complete resource and its new `ETag`; stale input
  returns `409 stale_deck`.
- Target and explanation languages may change only while no card, including an archived card, has
  ever been created under the deck. Otherwise the operation returns `409 deck_language_locked`.
- Archived decks cannot be edited or receive newly created cards until restored.
- Deck DELETE sets `archived_at` and returns `204 No Content`; repeating it returns `204` without a
  second transition. Restore clears `archived_at`, returns the current resource, and is also
  idempotent.
- Archiving and restoring a deck do not rewrite each card's individual `archived_at` value.

Card resources expose `GET /v1/cards`, `POST /v1/decks/{deck_id}/cards`,
`GET /v1/cards/{card_id}`, `PATCH /v1/cards/{card_id}`, `DELETE /v1/cards/{card_id}`, and
`POST /v1/cards/{card_id}/restore`.

- Card creation is nested under the owned deck so the body cannot choose ownership, deck language,
  or explanation language. It requires a UUID `Idempotency-Key` and accepts content fields such as
  term, meaning, optional reading, romanization, part of speech, and note.
- Term and meaning are trimmed and required; optional blank strings normalize to null. Duplicate
  terms remain valid. Server-controlled IDs, timestamps, versions, archive fields, and review state
  are rejected as inputs.
- Card creation and its initial review state are inserted atomically. Success returns `201 Created`,
  `Location`, and the complete card.
- Card PATCH uses `If-Match`, returns the complete updated card and new `ETag`, rejects unknown or
  immutable fields, and returns `409 stale_card` for a content-version mismatch.
- Optional fields may be cleared with explicit null, while term and meaning cannot become null or
  blank. Moving a card by patching `deck_id` is outside the first version.
- An archived card, or a card inside an archived deck, cannot be edited until the relevant resource
  is restored.
- Card DELETE independently sets the card's `archived_at`, preserves its example, tags, review
  state, and history, and idempotently returns `204`.
- Card restore clears only its individual `archived_at`. If its deck is still archived, the card is
  individually active but remains unavailable for review; responses expose effective eligibility
  such as `deck_archived_at` and `review_eligible`.
- `card.version` protects content, its embedded example, synonym/antonym arrays, tags, archive, and restore
  operations.
  `review_state.version` independently protects scheduling transitions so an unrelated note edit
  does not invalidate a pending review decision.
- The first version supports exactly one example per card, stored in the card's example fields.
  Normal card PATCH with `If-Match` creates, edits, or clears it; there is no example child resource,
  ordering, independent version, archive, restore, or endpoint.
- Removing the example sets sentence, translation, and source to null. Archiving the card preserves
  these fields automatically.
- Tag associations use idempotent
  `PUT /v1/cards/{card_id}/tags/{tag_id}` and
  `DELETE /v1/cards/{card_id}/tags/{tag_id}` rather than being hidden inside a general card PATCH.
- Permanent deletion of decks and cards is outside the first version.

### Card detail representation

- `GET /v1/cards/{card_id}` returns the complete owned card with its optional embedded example and
  all active tags, synonyms, and antonyms in deterministic display order.
- The bounded relationship limits make this representation predictable: at most 20 tags, 20
  synonyms, and 20 antonyms.
- `GET /v1/cards` returns compact card summaries rather than embedding every child collection in
  every list item.
- Synonyms and antonyms are card fields, not child resources. Card PATCH replaces an explicitly
  supplied array, an empty array clears it, and an omitted array remains unchanged.

### Tag endpoint contracts

- `GET /v1/tags` uses the approved cursor contract and returns tag ID, display name, version, and
  card count.
- `POST /v1/tags` accepts `display_name`. It returns `201 Created` plus `Location` for a new normalized
  identity, or `200 OK` with the existing owned tag when the normalized name already exists.
- Concurrent normalized-name creation relies on `UNIQUE (owner_id, normalized_name)`; the loser
  reads and returns the winning owned row.
- `PATCH /v1/tags/{tag_id}` uses `If-Match`, returns the updated tag and new `ETag`, and reports
  `stale_tag` or `tag_name_conflict` as appropriate.
- `PUT /v1/cards/{card_id}/tags/{tag_id}` uses the card `If-Match`, verifies common ownership and the
  20-tag cap, and returns the complete card with its current/new `ETag`. Repeating an existing
  attachment succeeds without another version increment.
- `DELETE /v1/cards/{card_id}/tags/{tag_id}` removes only the association and returns the complete
  card. Repeating an absent association succeeds without another version increment.
- `DELETE /v1/tags/{tag_id}` permanently deletes the owned tag and associations in one transaction,
  locking affected cards in deterministic UUID order and incrementing their content versions. It
  returns `204`; cards and review data remain intact.

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
- Review state inherits ownership through its card.
- Tags belong to one user and cannot be attached to another user's cards.
- Only the owner can view or modify their decks, cards, tags, review state, or review history.
- The backend derives current identity from a server-verified Google token.
- API inputs cannot choose `owner_id`, email, or another ownership identity.
- Every submitted resource ID is untrusted and every query must enforce the authenticated ownership
  boundary.
- Frontend visibility checks are user experience only; backend authorization is authoritative.
- A lookup for a resource owned by another user returns the same non-disclosing `404 Not Found`
  response as a nonexistent resource. It must not confirm that the other user's resource exists.
- The proposed status rule is:
  - `401 Unauthorized` when authentication is missing or invalid;
  - `404 Not Found` when the requested resource does not exist or is not owned by the authenticated
    user;
  - `403 Forbidden` only when the resource is intentionally visible to the user but the requested
    operation is not permitted, such as a possible future read-only shared deck;
  - `409 Conflict` when an owned resource exists but its current state prevents the operation, such
    as submitting a review after its card or deck was archived.
- The `404` response does not replace authorization: resource queries must still constrain results
  by the authenticated owner.

### Entity IDs and generation authority

- PostgreSQL generates every persistent entity ID. Create requests do not accept client-generated
  IDs, and the API returns the generated ID after insertion.
- Client-addressable resources use PostgreSQL-generated UUIDs. This includes decks, cards, tags,
  import runs, AI generation runs, and card drafts.
- Internal records use `BIGINT GENERATED ALWAYS AS IDENTITY` where an independent key is useful.
  This includes users, review events, and import items.
- One-to-one state and pure relationship tables do not receive unnecessary independent IDs:
  `review_states` uses `card_id` as its primary key, and `learning_card_tags` uses the composite
  `(card_id, tag_id)` primary key.
- The boundary is whether an ID is independently addressed through the client API, not an arbitrary
  preference for each table.
- UUIDs reduce casual enumeration but are not an authorization mechanism. Every lookup still
  enforces ownership, including the non-disclosing `404` rule.

### Timestamps, timezone, and clock authority

- PostgreSQL stores instants using `timestamptz` rather than timestamp values without timezone
  context.
- The API serializes timestamps as RFC 3339 values. A canonical UTC `Z` representation is proposed
  for transport, while the frontend displays times in `Asia/Taipei`.
- The first version supports `Asia/Taipei` as its only user-facing and calendar timezone; per-user
  timezone preferences are out of scope.
- The backend clock is authoritative for review submission time and schedule transitions. Clients
  do not submit trusted `reviewed_at`, `next_review_at`, or other calculated scheduling timestamps.
- Database-generated audit timestamps may use database time, but the review service owns the
  scheduling decision and supplies the transaction's calculated transition consistently.
- Tests must be able to control or inject the backend's notion of current time so boundary behavior
  is deterministic.
- Day-based review intervals use `Asia/Taipei` calendar days rather than exact elapsed multiples of
  24 hours.
- A review day begins at `00:00 Asia/Taipei`. Adding an interval of one day means the card becomes
  due at the start of the next Taiwan calendar day, not after 24 elapsed hours.
- The accepted tradeoff is that a review completed shortly before midnight may become due again
  shortly after midnight.

### AI scope

- AI generation will not be implemented in the first database-backed version.
- Issue #5 must still define the future conceptual boundary so the model and API do not bypass it:

  `generation request -> validated editable draft -> explicit confirmation -> learning card`

- AI output must never directly create or overwrite a confirmed learning card.
- Provider and model selection remain out of scope.

The approved future lifecycle is checked in as
[`ai-draft-lifecycle.md`](ai-draft-lifecycle.md). It specifies separate versioned
drafts and generation runs, a strict provider field allowlist, stale/late-result protection,
failure states, explicit idempotent confirmation, one-card-per-draft enforcement, discard behavior,
privacy/retention questions, and the MVP implementation boundary.

### Alternatives, tradeoffs, and unresolved decisions

- The approved record is checked in as
  [`alternatives.md`](alternatives.md).
- It records credible rejected alternatives for language modeling, scheduling authority and
  compatibility, authorization disclosure, IDs, calendar semantics, content normalization, tags,
  archival behavior, batching, pagination, review reservations, AI drafts, and infrastructure.
- It explicitly accepts the costs of duplicate terms, midnight scheduling, all-or-nothing batches,
  non-disclosing errors, embedded first-version content, archive storage, irreversible tag deletion,
  cursor navigation, PATCH reconciliation, corrected scheduling, and constrained redundant ownership.
- It separates choices required before their implementation area from deployment/migration choices
  deferred to later milestones and provider/retention/execution choices deferred with AI integration.

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

The MVP contracts for these functional areas are documented above. Later implementation must turn
them into tests rather than silently changing them.

## Routed later decisions

Implementation-area and later-milestone choices are explicitly listed in
[`alternatives.md`](alternatives.md); they do not block the Issue #5 design boundary
and must become acceptance criteria before their affected implementation begins.

## Ticket acceptance status

- [x] Direction chosen: one shared language-aware backend model, not separate language applications.
- [x] API identity and ownership must come from verified authentication, not request input.
- [x] AI output cannot directly create a confirmed card.
- [x] Complete primary business invariants and ownership rules.
- [x] Map every current Sheet field.
- [x] Complete failure behavior and recovery expectations.
- [x] Draft the `/v1` API and stable error envelope.
- [x] Check in the schema proposal and diagrams.
- [x] Record alternatives and unresolved decisions.
- [x] Verify Joseph can explain the design and a credible alternative without generated notes.

## Final consistency review

- Reviewed the handoff, schema proposal, failure matrix, request-flow diagrams, AI lifecycle, and
  alternatives record together on 2026-08-29.
- Confirmed removed multi-example and related-term child models are described only as rejected or
  explicitly absent alternatives, not active schema/API behavior.
- Corrected `nextReview` import wording to match required initialized `next_review_at` state.
- Added the approved creation idempotency requirement to the deck/card endpoint summaries.
- Confirmed review success and replay are reconstructable from stored batch/event snapshots,
  including previous/resulting last-review timestamps.
- Confirmed card content versions remain independent from review-state versions and archive/tag
  changes follow the documented transaction boundaries.
- Confirmed all runtime artifacts keep AI provider integration outside the database-backed MVP.
- No remaining cross-document inconsistency blocks the design.
- Joseph explained that a shared model avoids duplicating language-specific table/application paths
  while accepting language-aware validation, and identified separate per-language tables as a
  credible alternative.
- He also explained that ownership and language should derive from the authenticated owned deck to
  prevent mismatched client-supplied values.
- The design-defense acceptance item is complete. Formal GitHub issue closure remains an external
  tracking action and was not performed in this session.

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
