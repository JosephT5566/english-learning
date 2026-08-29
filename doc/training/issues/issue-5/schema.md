# Issue #5 Initial Schema Proposal

- Date: 2026-08-29
- Status: Approved design proposal; not implemented
- Scope: First database-backed English and Japanese learning core

## Design boundaries

- English and Japanese share one schema and review model.
- PostgreSQL generates persistent entity IDs.
- Ownership comes from authentication and is enforced through owned queries and foreign keys.
- Decks and cards archive; tags and tag associations can be removed.
- Review events are immutable and current review state changes atomically with them.
- Import and AI-draft lifecycle tables will be detailed separately.

Client-addressable resources use PostgreSQL-generated UUIDs. Internal users and append-only review
events use identity `BIGINT`s. Controlled values use `TEXT` plus named `CHECK` constraints rather
than PostgreSQL enum types. Instants use `timestamptz`.

## `users`

| Column | Type | Rules |
| --- | --- | --- |
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | Primary key |
| `google_subject` | `TEXT` | Required, nonempty, unique |
| `normalized_email` | `TEXT` | Required, nonempty |
| `created_at` | `TIMESTAMPTZ` | Required |
| `updated_at` | `TIMESTAMPTZ` | Required, not earlier than creation |

Google subject is the durable external identity. Email is not an ownership key.

## `learning_decks`

| Column | Type | Rules |
| --- | --- | --- |
| `id` | `UUID` | Primary key, PostgreSQL default |
| `owner_id` | `BIGINT` | Required FK to `users.id` |
| `title` | `TEXT` | Required, 1-100 characters |
| `target_language` | `TEXT` | `en` or `ja` |
| `explanation_language` | `TEXT` | `en`, `ja`, or `zh-TW` |
| `creation_idempotency_key` | `UUID` | Nullable; required for normal API creation |
| `creation_request_hash` | `TEXT` | Nullable; paired with creation key |
| `archived_at` | `TIMESTAMPTZ` | Nullable |
| `version` | `INTEGER` | Required, at least 1 |
| `created_at` | `TIMESTAMPTZ` | Required |
| `updated_at` | `TIMESTAMPTZ` | Required, not earlier than creation |

Keys and indexes:

- primary key `(id)` and unique `(id, owner_id)` for composite owned foreign keys;
- partial unique `(owner_id, creation_idempotency_key)` where the key is non-null;
- `(owner_id, archived_at, updated_at DESC, id DESC)` for management lists;
- `(owner_id, target_language, archived_at)` for language selection.

Titles are not unique. Languages lock after any active or archived card exists.
Creation key and request hash are constrained to be null together or present together. API creation
requires both; import-created rows may leave both null.

## `learning_cards`

| Column | Type | Rules |
| --- | --- | --- |
| `id` | `UUID` | Primary key, PostgreSQL default |
| `deck_id` | `UUID` | Required |
| `owner_id` | `BIGINT` | Required, constrained with deck |
| `term` | `TEXT` | Required, 1-255 characters |
| `meaning` | `TEXT` | Required, 1-2,000 characters |
| `reading` | `TEXT` | Nullable, 1-255 when present |
| `pronunciation` | `TEXT` | Nullable, 1-255 when present |
| `romanization` | `TEXT` | Nullable, 1-255 when present |
| `target_language_definition` | `TEXT` | Nullable, 1-2,000 when present |
| `example_sentence` | `TEXT` | Nullable, 1-1,000 when present |
| `example_translation` | `TEXT` | Nullable, 1-1,000 when present |
| `example_source` | `TEXT` | Nullable, 1-500 when present |
| `synonyms` | `TEXT[]` | Required default empty; at most 20 validated entries |
| `antonyms` | `TEXT[]` | Required default empty; at most 20 validated entries |
| `part_of_speech` | `TEXT` | Nullable controlled code |
| `part_of_speech_detail` | `TEXT` | Nullable, 1-100 when present |
| `note` | `TEXT` | Nullable, 1-4,000 when present |
| `supplementary_note` | `TEXT` | Nullable, 1-4,000 when present |
| `learned_on` | `DATE` | Nullable Taiwan calendar date |
| `creation_idempotency_key` | `UUID` | Nullable; required for normal API creation |
| `creation_request_hash` | `TEXT` | Nullable; paired with creation key |
| `archived_at` | `TIMESTAMPTZ` | Nullable |
| `version` | `INTEGER` | Required, at least 1 |
| `created_at` | `TIMESTAMPTZ` | Required |
| `updated_at` | `TIMESTAMPTZ` | Required, not earlier than creation |

Composite FK `(deck_id, owner_id)` references `learning_decks(id, owner_id)` with restricted
deletion. Cards derive both languages from the deck.

Allowed part-of-speech codes are `noun`, `verb`, `adjective`, `adverb`, `pronoun`, `determiner`,
`preposition`, `conjunction`, `interjection`, `particle`, `auxiliary`, `numeral`, `phrase`, and
`other`; `other` requires a nonempty detail.

Keys and indexes:

- primary key `(id)` and unique `(id, owner_id)` for owned relationships;
- partial unique `(owner_id, creation_idempotency_key)` where the key is non-null;
- `(deck_id, archived_at, updated_at DESC, id DESC)`;
- `(owner_id, archived_at, updated_at DESC, id DESC)`;
- `(owner_id, learned_on)`;
- planned trigram search index over normalized term, meaning, and reading, retained only after
  representative `EXPLAIN` verification.

Kana/kanji validation for an optional Japanese reading remains in service validation; PostgreSQL
still enforces nullability and length.
Creation key and request hash follow the same paired-null and per-owner replay rules as decks.

The first version supports exactly one optional example per card. Translation or source requires a
nonempty sentence. Card PATCH creates, edits, or clears the example fields under the card content
version; there is no example table, independent lifecycle, or child endpoint.

Synonyms and antonyms are ordered arrays directly on the card. Each contains at most 20 trimmed,
nonempty, normalized-unique entries of at most 255 characters. Card PATCH replaces an explicitly
supplied array and the card content version protects concurrent edits. There are no related-term
IDs, child endpoints, ordering commands, or independent archive records.

## `tags` and `learning_card_tags`

`tags` contains UUID `id`, user `owner_id`, 1-50 character `display_name`, 1-100 character
`normalized_name`, positive `version`, and timestamps. Unique `(owner_id, normalized_name)` defines
identity; unique `(id, owner_id)` supports owned associations. Tags do not archive.

`learning_card_tags` contains `owner_id`, `card_id`, `tag_id`, and `created_at`. Primary key
`(card_id, tag_id)` prevents duplicate attachment. Composite FKs reference
`learning_cards(id, owner_id)` and `tags(id, owner_id)`, making cross-owner attachment impossible.
Tag deletion cascades only to association rows. Index `(tag_id, card_id)` supports tag filtering. A
card may have at most 20 tags, enforced transactionally while locking the card.

## `review_batches`

| Column | Type | Rules |
| --- | --- | --- |
| `id` | `UUID` | Primary key, PostgreSQL default |
| `owner_id` | `BIGINT` | Required FK to user |
| `idempotency_key` | `UUID` | Required client command ID |
| `request_hash` | `TEXT` | Required, nonempty |
| `reviewed_at` | `TIMESTAMPTZ` | Required backend time |
| `algorithm_version` | `TEXT` | Required, nonempty |
| `item_count` | `SMALLINT` | Required, 1-10 |
| `created_at` | `TIMESTAMPTZ` | Required |

Unique `(owner_id, idempotency_key)` provides retry safety. Unique `(id, owner_id)` supports owned
event FKs. Completed batches remain with history.

## `review_states`

| Column | Type | Rules |
| --- | --- | --- |
| `card_id` | `UUID` | Primary key |
| `owner_id` | `BIGINT` | Required, constrained with card |
| `review_stage` | `SMALLINT` | Required, 1-5 |
| `ease_factor` | `NUMERIC(3,2)` | Required, 1.30-2.50 |
| `interval_days` | `INTEGER` | Required, nonnegative |
| `last_reviewed_at` | `TIMESTAMPTZ` | Nullable |
| `next_review_at` | `TIMESTAMPTZ` | Required |
| `version` | `INTEGER` | Required, at least 1 |
| `updated_at` | `TIMESTAMPTZ` | Required |

Composite FK `(card_id, owner_id)` references the owned card with restricted deletion. New cards are
immediately due with stage 1, ease 2.50, interval zero, null last review, backend creation time as
`next_review_at`, and version 1. Imported unreviewed cards without a next-review value use import
time and record the initialization in diagnostics.

Index `(owner_id, next_review_at, card_id)` supports due retrieval; card/deck joins still enforce
effective active state.

## `review_events`

| Column | Type | Rules |
| --- | --- | --- |
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | Primary key |
| `batch_id` | `UUID` | Required |
| `owner_id` | `BIGINT` | Required |
| `card_id` | `UUID` | Required |
| `decision` | `TEXT` | `no`, `no_a_bit`, `yes_a_bit`, or `yes` |
| `quality` | `SMALLINT` | 0, 2, 3, or 5 |
| previous/resulting stage | `SMALLINT` | Each 1-5 |
| previous/resulting ease | `NUMERIC(3,2)` | Each 1.30-2.50 |
| previous/resulting interval | `INTEGER` | Each nonnegative |
| previous/resulting last-review time | `TIMESTAMPTZ` | Previous nullable; resulting required and equals `reviewed_at` |
| previous/resulting next-review time | `TIMESTAMPTZ` | Required |
| previous/resulting version | `INTEGER` | Result equals previous plus one |
| `algorithm_version` | `TEXT` | Required, nonempty |
| `reviewed_at` | `TIMESTAMPTZ` | Required authoritative time |
| `created_at` | `TIMESTAMPTZ` | Required |

Composite FKs bind `(batch_id, owner_id)` to the owned batch and `(card_id, owner_id)` to the owned
card. Unique `(batch_id, card_id)` prevents two transitions for one card in a batch.

Indexes:

- `(owner_id, reviewed_at DESC, id DESC)` for owner history;
- `(card_id, reviewed_at DESC, id DESC)` for card history;
- `(batch_id, id)` for idempotent response reconstruction.

Review events have no application update or delete path. Before-and-after values keep transitions
explainable after scheduling changes.

## Deletion and transaction policy

- Deck-to-card, card-to-content, and card-to-review FKs restrict physical deletion.
- User-facing deletion archives decks and cards.
- Tag deletion cascades only through `learning_card_tags`.
- Review batches, states, and events are retained according to their durable history role.
- Card validation enforces synonym and antonym array bounds; transactions enforce the 20-tag cap.
- A review transaction validates the whole batch, locks states in deterministic card-ID order,
  inserts immutable events, and updates all current states before one commit.
- Expected versions make the first concurrent valid review commit win.

## Verification required during implementation

- Migration tests for every FK, check, uniqueness rule, and partial unique index.
- PostgreSQL integration tests for cross-owner relationships and transactional collection caps.
- Concurrency tests for tag attachment and review batches.
- Query-plan inspection for card lists, due retrieval, history, and substring search before optional
  indexes are finalized.
