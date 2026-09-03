# Issue #8 Entity-Relationship Diagram

- Date: 2026-09-03
- Source of truth: Alembic revision `20260902_0002`
- Scope: Implemented persistence schema only

```mermaid
erDiagram
    USERS ||--o{ LEARNING_DECKS : owns
    USERS ||--o{ TAGS : owns
    USERS ||--o{ REVIEW_BATCHES : submits
    LEARNING_DECKS ||--o{ LEARNING_CARDS : contains
    LEARNING_CARDS ||--o{ LEARNING_CARD_TAGS : receives
    TAGS ||--o{ LEARNING_CARD_TAGS : attaches
    LEARNING_CARDS ||--o| REVIEW_STATES : has_current
    LEARNING_CARDS ||--o{ REVIEW_EVENTS : records
    REVIEW_BATCHES ||--o{ REVIEW_EVENTS : groups

    USERS {
        bigint id PK
        text google_subject UK
        text normalized_email
        timestamptz created_at
        timestamptz updated_at
    }

    LEARNING_DECKS {
        uuid id PK
        bigint owner_id FK
        text title
        text target_language
        text explanation_language
        uuid creation_idempotency_key
        text creation_request_hash
        timestamptz archived_at
        integer version
        timestamptz created_at
        timestamptz updated_at
    }

    LEARNING_CARDS {
        uuid id PK
        uuid deck_id FK
        bigint owner_id FK
        text term
        text meaning
        text reading
        text pronunciation
        text romanization
        text target_language_definition
        text example_sentence
        text example_translation
        text example_source
        text_array synonyms
        text_array antonyms
        text part_of_speech
        text part_of_speech_detail
        text note
        text supplementary_note
        date learned_on
        uuid creation_idempotency_key
        text creation_request_hash
        timestamptz archived_at
        integer version
        timestamptz created_at
        timestamptz updated_at
    }

    TAGS {
        uuid id PK
        bigint owner_id FK
        text display_name
        text normalized_name
        integer version
        timestamptz created_at
        timestamptz updated_at
    }

    LEARNING_CARD_TAGS {
        bigint owner_id FK
        uuid card_id PK, FK
        uuid tag_id PK, FK
        timestamptz created_at
    }

    REVIEW_STATES {
        uuid card_id PK, FK
        bigint owner_id FK
        smallint review_stage
        numeric ease_factor
        integer interval_days
        timestamptz last_reviewed_at
        timestamptz next_review_at
        integer version
        timestamptz updated_at
    }

    REVIEW_BATCHES {
        uuid id PK
        bigint owner_id FK
        uuid idempotency_key
        text request_hash
        timestamptz reviewed_at
        text algorithm_version
        smallint item_count
        timestamptz created_at
    }

    REVIEW_EVENTS {
        bigint id PK
        uuid batch_id FK
        bigint owner_id FK
        uuid card_id FK
        text decision
        smallint quality
        smallint previous_review_stage
        smallint resulting_review_stage
        numeric previous_ease_factor
        numeric resulting_ease_factor
        integer previous_interval_days
        integer resulting_interval_days
        timestamptz previous_last_reviewed_at
        timestamptz resulting_last_reviewed_at
        timestamptz previous_next_review_at
        timestamptz resulting_next_review_at
        integer previous_version
        integer resulting_version
        text algorithm_version
        timestamptz reviewed_at
        timestamptz created_at
    }
```

## Composite ownership keys

The relationship lines show entity cardinality, but these multi-column constraints carry the
ownership guarantee:

| Child columns                           | Parent columns                 | Purpose                                     |
| --------------------------------------- | ------------------------------ | ------------------------------------------- |
| `learning_cards(deck_id, owner_id)`     | `learning_decks(id, owner_id)` | A card cannot name another owner's deck     |
| `learning_card_tags(card_id, owner_id)` | `learning_cards(id, owner_id)` | The association owner must own the card     |
| `learning_card_tags(tag_id, owner_id)`  | `tags(id, owner_id)`           | The same association owner must own the tag |
| `review_states(card_id, owner_id)`      | `learning_cards(id, owner_id)` | Current state cannot cross card ownership   |
| `review_events(batch_id, owner_id)`     | `review_batches(id, owner_id)` | History cannot use another owner's batch    |
| `review_events(card_id, owner_id)`      | `learning_cards(id, owner_id)` | History cannot use another owner's card     |

The parent tables expose matching unique owned keys. The repeated `owner_id` values are deliberate:
independent foreign keys would prove only that each ID exists, not that their combination belongs to
one user.

Other uniqueness rules define durable identity and retry boundaries:

- `users.google_subject` is globally unique.
- Deck and card creation keys are unique per owner when present.
- `tags(owner_id, normalized_name)` is unique per owner.
- `review_batches(owner_id, idempotency_key)` is unique per owner.
- `review_events(batch_id, card_id)` prevents two events for one card in a batch.

## Cardinality and identity

- A user may own zero or more decks, tags, and review batches. Every one of those rows has exactly
  one owner.
- A deck may contain zero or more cards; every confirmed card belongs to exactly one deck.
- Cards and tags form a many-to-many relationship through `learning_card_tags`. Its composite
  primary key `(card_id, tag_id)` prevents duplicate attachment.
- A card may have zero or one current `review_states` row. Using `card_id` as the state primary key
  enforces that limit without an unrelated state ID.
- A batch and card may each have zero or more retained events. Unique `(batch_id, card_id)` permits
  at most one event for a card within one batch.

## Deletion behavior

All owner, deck, card, state, batch, and event relationships use restricted physical deletion so
retained learning/history identities cannot disappear underneath child rows. User-facing deck and
card deletion will archive rather than physically delete them. The sole cascade is
`tags -> learning_card_tags`: permanently deleting a tag removes only its attachment rows and never
deletes a card.

## What the diagram does not imply

- Card language is derived through its required deck; `learning_cards` intentionally has no
  duplicated language column.
- The embedded example fields are part of the card and have no separate lifecycle.
- There is no foreign key between `review_events` and `review_states`. Matching event snapshots to
  current state, updating both atomically, locking, and replay behavior belong to the future review
  transaction service.
- A batch's `item_count` and final event count are not enforceable with an ordinary row check. The
  service must establish their agreement before commit.
- Relationship lines represent implemented foreign keys. They do not claim that API authorization
  or application transactions already exist.
