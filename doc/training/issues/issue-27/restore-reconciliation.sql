-- Read-only, content-free manifest. Run on source and isolated restore from
-- equivalent snapshots; compare outputs without committing private row values.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT metric, value FROM (
    SELECT 'alembic_version' AS metric, max(version_num)::text AS value
    FROM alembic_version
    UNION ALL SELECT 'schema_tables', count(*)::text
    FROM information_schema.tables
    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
    UNION ALL SELECT 'schema_columns', count(*)::text
    FROM information_schema.columns WHERE table_schema = 'public'
    UNION ALL SELECT 'schema_constraints', count(*)::text
    FROM pg_catalog.pg_constraint WHERE connamespace = 'public'::regnamespace
    UNION ALL SELECT 'schema_indexes', count(*)::text
    FROM pg_catalog.pg_indexes WHERE schemaname = 'public'
    UNION ALL SELECT 'users', count(*)::text FROM users
    UNION ALL SELECT 'learning_decks', count(*)::text FROM learning_decks
    UNION ALL SELECT 'learning_cards', count(*)::text FROM learning_cards
    UNION ALL SELECT 'tags', count(*)::text FROM tags
    UNION ALL SELECT 'learning_card_tags', count(*)::text FROM learning_card_tags
    UNION ALL SELECT 'review_states', count(*)::text FROM review_states
    UNION ALL SELECT 'review_batches', count(*)::text FROM review_batches
    UNION ALL SELECT 'review_events', count(*)::text FROM review_events
    UNION ALL SELECT 'import_runs', count(*)::text FROM import_runs
    UNION ALL SELECT 'import_items', count(*)::text FROM import_items
    UNION ALL SELECT 'confirmed_import_runs', count(*)::text FROM confirmed_import_runs
    UNION ALL SELECT 'confirmed_import_mappings', count(*)::text
    FROM confirmed_import_mappings
    UNION ALL SELECT 'cards_wrong_deck_owner', count(*)::text
    FROM learning_cards AS c
    LEFT JOIN learning_decks AS d ON d.id = c.deck_id
    WHERE d.id IS NULL OR d.owner_id <> c.owner_id
    UNION ALL SELECT 'states_wrong_card_owner', count(*)::text
    FROM review_states AS s
    LEFT JOIN learning_cards AS c ON c.id = s.card_id
    WHERE c.id IS NULL OR c.owner_id <> s.owner_id
    UNION ALL SELECT 'mappings_wrong_owner_or_deck', count(*)::text
    FROM confirmed_import_mappings AS m
    LEFT JOIN confirmed_import_runs AS r ON r.id = m.confirmed_import_run_id
    LEFT JOIN learning_cards AS c ON c.id = m.learning_card_id
    WHERE r.id IS NULL OR c.id IS NULL
       OR r.owner_id <> m.owner_id OR c.owner_id <> m.owner_id
       OR c.deck_id <> r.deck_id
) AS checks
ORDER BY metric;

COMMIT;
