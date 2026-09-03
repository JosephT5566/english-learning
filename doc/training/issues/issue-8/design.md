# Issue #8 Implementation Design

- Date: 2026-09-02
- Status: Accepted design; users/decks slice verified locally
- Dependency: Issue #7 persistence foundations are merged on `main` at `b1227ae`

## Boundary

This ticket implements the relational learning core. AI drafts, Google Sheets import records,
authentication behavior, and read APIs remain outside this migration. The database must reject
invalid ownership relationships and scheduling values even when application validation has a bug.

## Confirmed cards and multilingual fields

- `learning_cards` contains confirmed learning content only. `term` and `meaning` are required and
  must be nonblank after trimming.
- Incomplete or untrusted AI output must eventually use separate `card_drafts` tables; it must not
  be represented through nullable confirmed-card fields or a status in this ticket.
- `learning_cards.deck_id` is required. A card derives its target and explanation languages from
  its deck rather than duplicating language columns that could disagree.
- `reading`, `pronunciation`, and `romanization` are nullable shared columns with length constraints
  when present. The backend applies language-aware rules after loading the deck because an ordinary
  PostgreSQL `CHECK` cannot inspect another table.
- English and Japanese fixtures must exercise these same tables and ownership rules.

## Ownership keys

- A deck has a required `owner_id` foreign key to `users.id`. Physical deletion of an owner with
  retained learning data is restricted.
- `learning_decks` exposes unique `(id, owner_id)` so cards can use a composite owned foreign key.
- A card has required `deck_id` and `owner_id`, with `(deck_id, owner_id)` referencing the owned
  deck. This redundant constrained owner ID lets PostgreSQL reject cross-owner relationships.
- Other owned associations use the same pattern rather than relying on two independent foreign
  keys, which would accept an existing owner paired with another owner's existing resource.

## Review state and scheduling

- `review_states.card_id` is the primary key. An unrelated review-state ID is unnecessary, and the
  primary key directly enforces at most one current state for each card.
- `(card_id, owner_id)` references the owned card.
- Required columns use `NOT NULL`; checks separately reject present-but-invalid values.
- `review_stage` is in 1-5, `ease_factor` is `NUMERIC(3,2)` in 1.30-2.50,
  `interval_days` is nonnegative, and `version` is positive.
- `next_review_at` is required. `last_reviewed_at` is nullable for a new card; when present,
  `next_review_at >= last_reviewed_at`.
- The backend clock and scheduling algorithm create review times, but database checks remain a
  defense against invalid application writes.

## Embedded example decision

The first version keeps one optional example directly on `learning_cards` through
`example_sentence`, `example_translation`, and `example_source`.

- Translation or source requires a nonblank sentence.
- The example changes under the card's version and has no independent endpoint, ordering,
  archive state, or lifecycle.
- A separate `card_examples` table was rejected because one-to-many cardinality and independent
  behavior are not required yet.
- JSON storage was also rejected because it would weaken field-level relational constraints for no
  current benefit.
- Accepted consequence: supporting multiple examples later requires a migration and API change.

## Tags and associations

- Tags belong to one user. Unique `(owner_id, normalized_name)` provides normalized per-user tag
  identity while allowing different users to use the same name.
- Tags expose unique `(id, owner_id)` for owned associations.
- `learning_card_tags` has primary key `(card_id, tag_id)` to prevent duplicate attachment and also
  stores `owner_id`.
- Composite foreign keys `(card_id, owner_id)` and `(tag_id, owner_id)` reject cross-owner tag
  attachment. Independent card and tag foreign keys would not provide that guarantee.
- Deleting a tag cascades only to association rows. Cards and decks archive instead of being
  physically deleted because review history and recovery require stable identities.

## Review events and retry ownership

- The existing atomic review design accepts 1-10 decisions in one command. The idempotency key
  therefore belongs to an owned `review_batches` row, rather than being repeated independently on
  every event. Events are unique per `(batch_id, card_id)`.
- Each event preserves the decision, mapped quality, authoritative `reviewed_at`, algorithm version,
  and previous/resulting stage, ease, interval, last-review time, next-review time, and state version.
- Local checks enforce the same scheduling ranges as current state,
  `resulting_version = previous_version + 1`, and
  `resulting_last_reviewed_at = reviewed_at`. The backend validates the complete algorithmic
  transition.
- `(card_id, owner_id)` references the owned card and `(batch_id, owner_id)` references the owned
  batch, preventing history from crossing ownership boundaries.
- Review events have no application update or delete path.

## Index rationale

Only indexes tied to named access patterns are accepted initially:

| Access pattern | Index | Rationale |
| --- | --- | --- |
| List active cards in a deck, newest first | `(deck_id, created_at DESC, id DESC) WHERE archived_at IS NULL` | Deck equality leads; ID makes equal timestamps deterministic |
| Filter a user's decks by language and archive state | `(owner_id, target_language, archived_at)` | Matches ownership and language filters |
| Retrieve a user's due cards in due order | `(owner_id, next_review_at, card_id)` on `review_states` | Owner and due range lead; card ID is the stable tie-breaker |
| Show a user's review history newest first | `(owner_id, reviewed_at DESC, id DESC)` on `review_events` | Supports owner-scoped reverse chronology with deterministic order |

The due query still joins cards and decks to exclude effectively archived content. A trigram search
index remains deferred until a representative query and `EXPLAIN` result justify it.

## PostgreSQL verification plan

- Upgrade an empty temporary database to the new revision, downgrade to the Issue #7 baseline, and
  re-upgrade.
- Test every important required field, supported-language check, range check, uniqueness rule,
  foreign key, composite ownership relationship, and deletion behavior against PostgreSQL.
- Prove one review state per card and reject cross-owner review events and tag associations.
- Insert representative English and Japanese fixtures through the same schema.
- Verify invalid scheduling values and timestamp ordering are rejected.
- Inspect the named list, language, due-review, and history queries with representative data before
  claiming index effectiveness.

## First implementation slice

Add `users` and `learning_decks` in the new domain migration, then prove that a deck requires an
existing owner, accepts only supported target languages, supports both English and Japanese through
one table, and restricts deletion of an owner with retained decks.

### Result

Revision `20260902_0002` implements the slice with named PostgreSQL constraints, a per-owner partial
unique creation-replay index, the language-filtering index, and a reversible downgrade. Tests cover
the generated IDs, shared English/Japanese table, required and existing owners, supported languages,
nonblank identity/title/hash data, uniqueness, version/timestamp/archive checks, replay pairing, and
restricted deletion. The temporary and development databases both passed upgrade, downgrade to the
Issue #7 baseline, and re-upgrade.
