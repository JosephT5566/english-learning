# Issue #8 Implementation Design

- Date: 2026-09-03
- Status: Core schema, bilingual fixture, and ER diagram verified locally
- Dependency: Issue #7 persistence foundations are merged on `main` at `b1227ae`

The implemented entity relationships, composite ownership keys, deletion behavior, and
transaction-only boundaries are visualized in the [Issue #8 ER diagram](erd.md).

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

| Access pattern                                      | Index                                                           | Rationale                                                                       |
| --------------------------------------------------- | --------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| List active cards in a deck, newest first           | `(deck_id, created_at DESC, id DESC) WHERE archived_at IS NULL` | Deck equality leads; ID makes equal timestamps deterministic                    |
| Filter a user's decks by language and archive state | `(owner_id, target_language, archived_at)`                      | Matches ownership and language filters                                          |
| List cards attached to one tag                      | `(tag_id, card_id)` on `learning_card_tags`                    | Supports reverse traversal and stable card-ID order                              |
| Retrieve a user's due cards in due order            | `(owner_id, next_review_at, card_id)` on `review_states`        | Owner and due range lead; card ID is the stable tie-breaker                     |
| Show a user's review history newest first           | `(owner_id, reviewed_at DESC, id DESC)` on `review_events`      | Supports owner-scoped reverse chronology with deterministic order               |
| Show one card's review history newest first         | `(card_id, reviewed_at DESC, id DESC)` on `review_events`       | Supports card-scoped reverse chronology with deterministic order                |
| Reconstruct one batch response in event order       | `(batch_id, id)` on `review_events`                             | Batch equality leads; generated event ID provides explicit reconstruction order |

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

### Test harness mental model

`temporary_database_url` owns creation and deletion of one uniquely named empty PostgreSQL database.
`migrated_database_engine` depends on that fixture, points Alembic at the temporary URL, runs
`upgrade head`, and yields a SQLAlchemy engine for schema tests. Helpers such as `insert_user()` and
`insert_deck()` then establish valid prerequisite rows before each test exercises accepted and
rejected writes.

The engine is a connection factory/pool, not the database itself or one permanent connection.
Teardown disposes it before the temporary database fixture drops the database. Because these are
function-scoped fixtures, every test invocation is isolated. The migration lifecycle test
deliberately uses the empty-database fixture directly so it can control upgrade and downgrade itself.

This boundary proves that Alembic creates the expected PostgreSQL tables, defaults, keys, indexes,
and checks. It does not by itself prove ORM metadata agreement, API behavior, authentication,
production-data import, or deployment behavior.

The current lifecycle assertions inspect both head and the reverted Issue #7 baseline. Because that
baseline intentionally has no domain tables, confirming that only `alembic_version` remains is an
appropriate structural check. This is not a universal proof that `upgrade()` and `downgrade()` are
exact inverses: Alembic can record the expected revision even if unasserted columns, constraints,
indexes, defaults, or transformed data are wrong. Once older revisions contain real schema or data,
important adjacent revision boundaries require their own expected-schema and data assertions.

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

## Second implementation slice

The same unshipped revision now adds confirmed `learning_cards`. PostgreSQL requires a matching
owned `(deck_id, owner_id)` pair and nonblank term/meaning, while nullable language-specific fields
allow English and Japanese to share one table. Named checks cover optional lengths, embedded-example
dependencies, related-word array bounds/null elements, part-of-speech values, creation replay data,
versions, timestamps, and archive ordering. Physical deck deletion is restricted while cards remain.

Representative English and Japanese card tests pass through the same schema. The partial active-card
index is verified to have `(deck_id, created_at DESC, id DESC)` and `archived_at IS NULL`; this is
index-definition evidence only, not an `EXPLAIN` or performance result.

## Third implementation slice

Revision `20260902_0002` now includes owned `tags` and `learning_card_tags`. A tag's normalized name
is unique only within its owner, so different owners can use the same tag identity. Unique
`(tags.id, owner_id)` and the existing owned card key let the association validate both
`(tag_id, owner_id)` and `(card_id, owner_id)` as composite foreign keys. Primary key
`(card_id, tag_id)` rejects duplicate attachment.

Deleting a tag cascades to association rows only and leaves the learning card intact. The card-side
foreign key restricts physical deletion while tagged, consistent with archive-first card behavior.
The reverse `(tag_id, card_id)` index supports the named tag-filtering access pattern; only its
definition is verified so far. The maximum 20 tags per card remains a future transaction rule that
must lock the card before counting and inserting associations.

## Fourth implementation slice

Revision `20260902_0002` now includes `review_states`. Primary key `card_id` directly limits each
card to one current row, while `(card_id, owner_id)` references the owned card and restricts physical
card deletion. Stage, ease, interval, next-review time, and version are required without database
defaults, preserving the backend as the explicit scheduling authority. `last_reviewed_at` remains
nullable for a new card, and a present value cannot follow `next_review_at`.

Focused PostgreSQL tests reject every omitted scheduling field, cross-owner state, duplicate state,
out-of-range stage/ease/interval/version values, invalid review-time ordering, and physical card
deletion while state remains. The `(owner_id, next_review_at, card_id)` index definition matches the
named due-review pattern; archived card/deck filtering and query-plan evidence remain pending.

## Fifth implementation slice

Revision `20260902_0002` now includes `review_batches` and `review_events`. A batch owns one client
idempotency key under unique `(owner_id, idempotency_key)` and records the request hash, backend
review time, algorithm version, and 1-10 item count. Unique `(id, owner_id)` supports the event's
composite owned-batch foreign key.

Each event also references an owned card and requires a complete before/after schedule snapshot,
except for the intentionally nullable previous last-review time. Named checks enforce supported and
matching decision/quality values, stage/ease/interval ranges, positive consecutive versions,
previous/resulting schedule ordering, monotonic review time, and equality between review time and
the resulting last-review time. Unique `(batch_id, card_id)` prevents two events for one card in a
batch, and restrictive foreign keys retain card and batch identities while history exists.

The owner-history, card-history, and batch-reconstruction index definitions are verified against
their named access patterns. Static row constraints cannot prove that `item_count` equals the final
event count or that an event matches and atomically updates current state; request-hash replay,
locking, atomic writes, and the no-update/delete application contract remain future review-service
responsibilities.

## Sixth implementation slice

`tests/fixtures/multilingual_learning_domain.sql` provides deterministic synthetic data spanning
every Issue #8 table. One owner has English and Japanese decks/cards, reusable tags shared across
languages, matching current review states, and one two-card batch whose before/after events align
with those states. Fixed UUIDs keep relationships readable while PostgreSQL generates internal user
and event identity values.

The integration test loads the fixture in one transaction, verifies exact table counts,
language-specific optional fields through the shared card table, cross-language tag reuse, batch
membership, and resulting-event/current-state agreement. A repeated load fails on the expected
durable user identity. This is a test fixture, not a production seed, import implementation, or
proof that cross-row agreement is enforced for arbitrary writes.

## Seventh implementation slice

The Mermaid [entity-relationship diagram](erd.md) now covers every implemented table and physical
foreign-key relationship in revision `20260902_0002`. Supporting notes make the composite owned keys,
one-to-one review-state identity, many-to-many tag association, history cardinality, and asymmetric
deletion behavior explicit.

The diagram deliberately does not draw a database relationship between current state and events.
Their agreement, atomic update, locking, and replay behavior are future review-service transaction
guarantees rather than implemented foreign keys. This distinction prevents planned application
behavior from being presented as current database enforcement.

## Eighth implementation slice

`tests/integration/test_query_plans.py` builds a deterministic representative dataset in one
isolated migrated PostgreSQL 17 database, runs `ANALYZE`, then executes all seven named reads with
`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`. The JSON plan assertions prove that PostgreSQL naturally
selects each deliberate index, including the review-state index in the joined due-card query.

The dataset contains 100 owners, 2,000 decks, and 40,000 rows in each of cards, states, tag links,
and review events. Planner methods remain enabled. The test intentionally does not assert cost,
timing, buffer totals, or a complete plan tree, so the evidence remains about index selection rather
than unstable performance numbers. The full method, mapping, and limitations are recorded in the
[query-plan report](query-plans.md).
