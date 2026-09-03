"""Add the owned multilingual learning domain.

Revision ID: 20260902_0002
Revises: 20260901_0001
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260902_0002"
down_revision: str | Sequence[str] | None = "20260901_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create users, language-aware decks, and confirmed cards."""

    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column("google_subject", sa.Text(), nullable=False),
        sa.Column("normalized_email", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(btrim(google_subject)) > 0",
            name="ck_users_google_subject_nonblank",
        ),
        sa.CheckConstraint(
            "char_length(btrim(normalized_email)) > 0",
            name="ck_users_normalized_email_nonblank",
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name="ck_users_timestamps_ordered",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint(
            "google_subject",
            name="uq_users_google_subject",
        ),
    )

    op.create_table(
        "learning_decks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("target_language", sa.Text(), nullable=False),
        sa.Column("explanation_language", sa.Text(), nullable=False),
        sa.Column(
            "creation_idempotency_key",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("creation_request_hash", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(btrim(title)) BETWEEN 1 AND 100",
            name="ck_learning_decks_title_length",
        ),
        sa.CheckConstraint(
            "target_language IN ('en', 'ja')",
            name="ck_learning_decks_target_language_supported",
        ),
        sa.CheckConstraint(
            "explanation_language IN ('en', 'ja', 'zh-TW')",
            name="ck_learning_decks_explanation_language_supported",
        ),
        sa.CheckConstraint(
            "(creation_idempotency_key IS NULL) = (creation_request_hash IS NULL)",
            name="ck_learning_decks_creation_replay_fields_paired",
        ),
        sa.CheckConstraint(
            "creation_request_hash IS NULL "
            "OR char_length(btrim(creation_request_hash)) > 0",
            name="ck_learning_decks_creation_request_hash_nonblank",
        ),
        sa.CheckConstraint(
            "version >= 1",
            name="ck_learning_decks_version_positive",
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name="ck_learning_decks_timestamps_ordered",
        ),
        sa.CheckConstraint(
            "archived_at IS NULL OR archived_at >= created_at",
            name="ck_learning_decks_archive_not_before_creation",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_learning_decks_owner_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_learning_decks"),
        sa.UniqueConstraint(
            "id",
            "owner_id",
            name="uq_learning_decks_id_owner_id",
        ),
    )
    op.create_index(
        "ix_learning_decks_owner_language_archive",
        "learning_decks",
        ["owner_id", "target_language", "archived_at"],
        unique=False,
    )
    op.create_index(
        "uq_learning_decks_owner_creation_idempotency_key",
        "learning_decks",
        ["owner_id", "creation_idempotency_key"],
        unique=True,
        postgresql_where=sa.text("creation_idempotency_key IS NOT NULL"),
    )

    op.create_table(
        "learning_cards",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("deck_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("term", sa.Text(), nullable=False),
        sa.Column("meaning", sa.Text(), nullable=False),
        sa.Column("reading", sa.Text(), nullable=True),
        sa.Column("pronunciation", sa.Text(), nullable=True),
        sa.Column("romanization", sa.Text(), nullable=True),
        sa.Column("target_language_definition", sa.Text(), nullable=True),
        sa.Column("example_sentence", sa.Text(), nullable=True),
        sa.Column("example_translation", sa.Text(), nullable=True),
        sa.Column("example_source", sa.Text(), nullable=True),
        sa.Column(
            "synonyms",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column(
            "antonyms",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("part_of_speech", sa.Text(), nullable=True),
        sa.Column("part_of_speech_detail", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("supplementary_note", sa.Text(), nullable=True),
        sa.Column("learned_on", sa.Date(), nullable=True),
        sa.Column(
            "creation_idempotency_key",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("creation_request_hash", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(btrim(term)) BETWEEN 1 AND 255",
            name="ck_learning_cards_term_length",
        ),
        sa.CheckConstraint(
            "char_length(btrim(meaning)) BETWEEN 1 AND 2000",
            name="ck_learning_cards_meaning_length",
        ),
        sa.CheckConstraint(
            "reading IS NULL OR char_length(btrim(reading)) BETWEEN 1 AND 255",
            name="ck_learning_cards_reading_length",
        ),
        sa.CheckConstraint(
            "pronunciation IS NULL "
            "OR char_length(btrim(pronunciation)) BETWEEN 1 AND 255",
            name="ck_learning_cards_pronunciation_length",
        ),
        sa.CheckConstraint(
            "romanization IS NULL "
            "OR char_length(btrim(romanization)) BETWEEN 1 AND 255",
            name="ck_learning_cards_romanization_length",
        ),
        sa.CheckConstraint(
            "target_language_definition IS NULL "
            "OR char_length(btrim(target_language_definition)) BETWEEN 1 AND 2000",
            name="ck_learning_cards_target_language_definition_length",
        ),
        sa.CheckConstraint(
            "example_sentence IS NULL "
            "OR char_length(btrim(example_sentence)) BETWEEN 1 AND 1000",
            name="ck_learning_cards_example_sentence_length",
        ),
        sa.CheckConstraint(
            "example_translation IS NULL "
            "OR char_length(btrim(example_translation)) BETWEEN 1 AND 1000",
            name="ck_learning_cards_example_translation_length",
        ),
        sa.CheckConstraint(
            "example_source IS NULL "
            "OR char_length(btrim(example_source)) BETWEEN 1 AND 500",
            name="ck_learning_cards_example_source_length",
        ),
        sa.CheckConstraint(
            "example_sentence IS NOT NULL "
            "OR (example_translation IS NULL AND example_source IS NULL)",
            name="ck_learning_cards_example_dependents_require_sentence",
        ),
        sa.CheckConstraint(
            "cardinality(synonyms) <= 20",
            name="ck_learning_cards_synonyms_count",
        ),
        sa.CheckConstraint(
            "array_position(synonyms, NULL) IS NULL",
            name="ck_learning_cards_synonyms_no_nulls",
        ),
        sa.CheckConstraint(
            "cardinality(antonyms) <= 20",
            name="ck_learning_cards_antonyms_count",
        ),
        sa.CheckConstraint(
            "array_position(antonyms, NULL) IS NULL",
            name="ck_learning_cards_antonyms_no_nulls",
        ),
        sa.CheckConstraint(
            "part_of_speech IS NULL OR part_of_speech IN ("
            "'noun', 'verb', 'adjective', 'adverb', 'pronoun', "
            "'determiner', 'preposition', 'conjunction', 'interjection', "
            "'particle', 'auxiliary', 'numeral', 'phrase', 'other'"
            ")",
            name="ck_learning_cards_part_of_speech_supported",
        ),
        sa.CheckConstraint(
            "part_of_speech_detail IS NULL "
            "OR char_length(btrim(part_of_speech_detail)) BETWEEN 1 AND 100",
            name="ck_learning_cards_part_of_speech_detail_length",
        ),
        sa.CheckConstraint(
            "part_of_speech IS DISTINCT FROM 'other' "
            "OR part_of_speech_detail IS NOT NULL",
            name="ck_learning_cards_other_part_of_speech_requires_detail",
        ),
        sa.CheckConstraint(
            "note IS NULL OR char_length(btrim(note)) BETWEEN 1 AND 4000",
            name="ck_learning_cards_note_length",
        ),
        sa.CheckConstraint(
            "supplementary_note IS NULL "
            "OR char_length(btrim(supplementary_note)) BETWEEN 1 AND 4000",
            name="ck_learning_cards_supplementary_note_length",
        ),
        sa.CheckConstraint(
            "(creation_idempotency_key IS NULL) = (creation_request_hash IS NULL)",
            name="ck_learning_cards_creation_replay_fields_paired",
        ),
        sa.CheckConstraint(
            "creation_request_hash IS NULL "
            "OR char_length(btrim(creation_request_hash)) > 0",
            name="ck_learning_cards_creation_request_hash_nonblank",
        ),
        sa.CheckConstraint(
            "version >= 1",
            name="ck_learning_cards_version_positive",
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name="ck_learning_cards_timestamps_ordered",
        ),
        sa.CheckConstraint(
            "archived_at IS NULL OR archived_at >= created_at",
            name="ck_learning_cards_archive_not_before_creation",
        ),
        sa.ForeignKeyConstraint(
            ["deck_id", "owner_id"],
            ["learning_decks.id", "learning_decks.owner_id"],
            name="fk_learning_cards_deck_id_owner_id_learning_decks",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_learning_cards"),
        sa.UniqueConstraint(
            "id",
            "owner_id",
            name="uq_learning_cards_id_owner_id",
        ),
    )
    op.create_index(
        "ix_learning_cards_active_deck_created_id",
        "learning_cards",
        ["deck_id", sa.text("created_at DESC"), sa.text("id DESC")],
        unique=False,
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    op.create_index(
        "uq_learning_cards_owner_creation_idempotency_key",
        "learning_cards",
        ["owner_id", "creation_idempotency_key"],
        unique=True,
        postgresql_where=sa.text("creation_idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    """Remove cards, learning decks, and users in dependency order."""

    op.drop_index(
        "uq_learning_cards_owner_creation_idempotency_key",
        table_name="learning_cards",
    )
    op.drop_index(
        "ix_learning_cards_active_deck_created_id",
        table_name="learning_cards",
    )
    op.drop_table("learning_cards")

    op.drop_index(
        "uq_learning_decks_owner_creation_idempotency_key",
        table_name="learning_decks",
    )
    op.drop_index(
        "ix_learning_decks_owner_language_archive",
        table_name="learning_decks",
    )
    op.drop_table("learning_decks")
    op.drop_table("users")
