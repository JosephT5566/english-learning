INSERT INTO users (google_subject, normalized_email)
VALUES ('fixture-google-subject', 'fixture@example.test');

INSERT INTO learning_decks (
    id,
    owner_id,
    title,
    target_language,
    explanation_language,
    created_at,
    updated_at
)
SELECT
    fixture.id,
    users.id,
    fixture.title,
    fixture.target_language,
    'zh-TW',
    TIMESTAMPTZ '2026-09-01 00:00:00+00',
    TIMESTAMPTZ '2026-09-01 00:00:00+00'
FROM users
CROSS JOIN (
    VALUES
        (
            UUID '10000000-0000-0000-0000-000000000001',
            'English fixture deck',
            'en'
        ),
        (
            UUID '10000000-0000-0000-0000-000000000002',
            'Japanese fixture deck',
            'ja'
        )
) AS fixture(id, title, target_language)
WHERE users.google_subject = 'fixture-google-subject';

INSERT INTO learning_cards (
    id,
    deck_id,
    owner_id,
    term,
    meaning,
    reading,
    pronunciation,
    romanization,
    target_language_definition,
    example_sentence,
    example_translation,
    synonyms,
    antonyms,
    part_of_speech,
    note,
    learned_on,
    created_at,
    updated_at
)
SELECT
    fixture.id,
    fixture.deck_id,
    users.id,
    fixture.term,
    fixture.meaning,
    fixture.reading,
    fixture.pronunciation,
    fixture.romanization,
    fixture.target_language_definition,
    fixture.example_sentence,
    fixture.example_translation,
    fixture.synonyms,
    fixture.antonyms,
    'noun',
    fixture.note,
    DATE '2026-09-01',
    TIMESTAMPTZ '2026-09-01 01:00:00+00',
    TIMESTAMPTZ '2026-09-01 01:00:00+00'
FROM users
CROSS JOIN (
    VALUES
        (
            UUID '20000000-0000-0000-0000-000000000001',
            UUID '10000000-0000-0000-0000-000000000001',
            'serendipity',
            '意外發現美好事物的能力',
            NULL,
            '/ˌser.ənˈdɪp.ə.ti/',
            NULL,
            'the occurrence of a useful discovery by chance',
            'We met by pure serendipity.',
            '我們的相遇純屬美好的偶然。',
            ARRAY['chance', 'fortune']::TEXT[],
            ARRAY['design']::TEXT[],
            'English pronunciation uses the shared optional fields.'
        ),
        (
            UUID '20000000-0000-0000-0000-000000000002',
            UUID '10000000-0000-0000-0000-000000000002',
            '勉強',
            '學習',
            'べんきょう',
            NULL,
            'benkyou',
            '知識や技術を身につけること',
            '毎日日本語を勉強します。',
            '我每天學日文。',
            ARRAY['学習']::TEXT[],
            ARRAY[]::TEXT[],
            'Japanese reading uses the same card table.'
        )
) AS fixture(
    id,
    deck_id,
    term,
    meaning,
    reading,
    pronunciation,
    romanization,
    target_language_definition,
    example_sentence,
    example_translation,
    synonyms,
    antonyms,
    note
)
WHERE users.google_subject = 'fixture-google-subject';

INSERT INTO tags (
    id,
    owner_id,
    display_name,
    normalized_name,
    created_at,
    updated_at
)
SELECT
    fixture.id,
    users.id,
    fixture.display_name,
    fixture.normalized_name,
    TIMESTAMPTZ '2026-09-01 02:00:00+00',
    TIMESTAMPTZ '2026-09-01 02:00:00+00'
FROM users
CROSS JOIN (
    VALUES
        (
            UUID '30000000-0000-0000-0000-000000000001',
            'Core',
            'core'
        ),
        (
            UUID '30000000-0000-0000-0000-000000000002',
            'Noun',
            'noun'
        )
) AS fixture(id, display_name, normalized_name)
WHERE users.google_subject = 'fixture-google-subject';

INSERT INTO learning_card_tags (owner_id, card_id, tag_id, created_at)
SELECT
    users.id,
    fixture.card_id,
    fixture.tag_id,
    TIMESTAMPTZ '2026-09-01 03:00:00+00'
FROM users
CROSS JOIN (
    VALUES
        (
            UUID '20000000-0000-0000-0000-000000000001',
            UUID '30000000-0000-0000-0000-000000000001'
        ),
        (
            UUID '20000000-0000-0000-0000-000000000001',
            UUID '30000000-0000-0000-0000-000000000002'
        ),
        (
            UUID '20000000-0000-0000-0000-000000000002',
            UUID '30000000-0000-0000-0000-000000000001'
        )
) AS fixture(card_id, tag_id)
WHERE users.google_subject = 'fixture-google-subject';

INSERT INTO review_batches (
    id,
    owner_id,
    idempotency_key,
    request_hash,
    reviewed_at,
    algorithm_version,
    item_count,
    created_at
)
SELECT
    UUID '40000000-0000-0000-0000-000000000001',
    users.id,
    UUID '50000000-0000-0000-0000-000000000001',
    'sha256:fixture-review-batch',
    TIMESTAMPTZ '2026-09-02 12:00:00+00',
    'srs-v1',
    2,
    TIMESTAMPTZ '2026-09-02 12:00:01+00'
FROM users
WHERE users.google_subject = 'fixture-google-subject';

INSERT INTO review_states (
    card_id,
    owner_id,
    review_stage,
    ease_factor,
    interval_days,
    last_reviewed_at,
    next_review_at,
    version,
    updated_at
)
SELECT
    fixture.card_id,
    users.id,
    fixture.review_stage,
    fixture.ease_factor,
    fixture.interval_days,
    TIMESTAMPTZ '2026-09-02 12:00:00+00',
    fixture.next_review_at,
    fixture.version,
    TIMESTAMPTZ '2026-09-02 12:00:01+00'
FROM users
CROSS JOIN (
    VALUES
        (
            UUID '20000000-0000-0000-0000-000000000001',
            2::SMALLINT,
            2.50::NUMERIC(3, 2),
            1,
            TIMESTAMPTZ '2026-09-03 00:00:00+00',
            2
        ),
        (
            UUID '20000000-0000-0000-0000-000000000002',
            1::SMALLINT,
            2.20::NUMERIC(3, 2),
            0,
            TIMESTAMPTZ '2026-09-02 12:00:00+00',
            4
        )
) AS fixture(
    card_id,
    review_stage,
    ease_factor,
    interval_days,
    next_review_at,
    version
)
WHERE users.google_subject = 'fixture-google-subject';

INSERT INTO review_events (
    batch_id,
    owner_id,
    card_id,
    decision,
    quality,
    previous_review_stage,
    resulting_review_stage,
    previous_ease_factor,
    resulting_ease_factor,
    previous_interval_days,
    resulting_interval_days,
    previous_last_reviewed_at,
    resulting_last_reviewed_at,
    previous_next_review_at,
    resulting_next_review_at,
    previous_version,
    resulting_version,
    algorithm_version,
    reviewed_at,
    created_at
)
SELECT
    UUID '40000000-0000-0000-0000-000000000001',
    users.id,
    fixture.card_id,
    fixture.decision,
    fixture.quality,
    fixture.previous_review_stage,
    fixture.resulting_review_stage,
    fixture.previous_ease_factor,
    fixture.resulting_ease_factor,
    fixture.previous_interval_days,
    fixture.resulting_interval_days,
    fixture.previous_last_reviewed_at,
    TIMESTAMPTZ '2026-09-02 12:00:00+00',
    fixture.previous_next_review_at,
    fixture.resulting_next_review_at,
    fixture.previous_version,
    fixture.resulting_version,
    'srs-v1',
    TIMESTAMPTZ '2026-09-02 12:00:00+00',
    TIMESTAMPTZ '2026-09-02 12:00:01+00'
FROM users
CROSS JOIN (
    VALUES
        (
            UUID '20000000-0000-0000-0000-000000000001',
            'yes',
            5::SMALLINT,
            1::SMALLINT,
            2::SMALLINT,
            2.50::NUMERIC(3, 2),
            2.50::NUMERIC(3, 2),
            0,
            1,
            NULL::TIMESTAMPTZ,
            TIMESTAMPTZ '2026-09-02 00:00:00+00',
            TIMESTAMPTZ '2026-09-03 00:00:00+00',
            1,
            2
        ),
        (
            UUID '20000000-0000-0000-0000-000000000002',
            'no_a_bit',
            2::SMALLINT,
            2::SMALLINT,
            1::SMALLINT,
            2.30::NUMERIC(3, 2),
            2.20::NUMERIC(3, 2),
            3,
            0,
            TIMESTAMPTZ '2026-09-01 12:00:00+00',
            TIMESTAMPTZ '2026-09-04 00:00:00+00',
            TIMESTAMPTZ '2026-09-02 12:00:00+00',
            3,
            4
        )
) AS fixture(
    card_id,
    decision,
    quality,
    previous_review_stage,
    resulting_review_stage,
    previous_ease_factor,
    resulting_ease_factor,
    previous_interval_days,
    resulting_interval_days,
    previous_last_reviewed_at,
    previous_next_review_at,
    resulting_next_review_at,
    previous_version,
    resulting_version
)
WHERE users.google_subject = 'fixture-google-subject';
