# Multilingual domain fixture

`multilingual_learning_domain.sql` is synthetic PostgreSQL-only test data for Issue #8. It contains
one owner, English and Japanese decks/cards, reusable tags, current review states, and one two-card
review batch with matching before/after events.

The fixture uses fixed UUIDs so relationships are easy to inspect and assertions remain
deterministic. PostgreSQL still generates identity IDs for the user and review events. Tests load
the file inside one transaction after Alembic upgrades an isolated temporary database.

The shared `temporary_database_url` pytest fixture creates and later drops the uniquely named test
database. `migrated_database_engine` points Alembic at that URL, upgrades it to `head`, and supplies
the SQLAlchemy engine used to load this file. The persistent `english_learning` development database
is untouched unless this SQL file is run against it manually.

This file is not a production seed, Google Sheets import, or idempotent replay script. Load it only
into an empty migrated test database; duplicate loading is expected to fail rather than hide an
unexpected pre-existing row.
