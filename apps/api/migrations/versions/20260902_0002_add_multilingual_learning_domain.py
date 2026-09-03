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
    """Create the owned multilingual learning and review domain."""

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

    op.create_table(
        "tags",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
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
            "char_length(btrim(display_name)) BETWEEN 1 AND 50",
            name="ck_tags_display_name_length",
        ),
        sa.CheckConstraint(
            "char_length(btrim(normalized_name)) BETWEEN 1 AND 100",
            name="ck_tags_normalized_name_length",
        ),
        sa.CheckConstraint(
            "version >= 1",
            name="ck_tags_version_positive",
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name="ck_tags_timestamps_ordered",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_tags_owner_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tags"),
        sa.UniqueConstraint(
            "owner_id",
            "normalized_name",
            name="uq_tags_owner_id_normalized_name",
        ),
        sa.UniqueConstraint(
            "id",
            "owner_id",
            name="uq_tags_id_owner_id",
        ),
    )

    op.create_table(
        "learning_card_tags",
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("card_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["card_id", "owner_id"],
            ["learning_cards.id", "learning_cards.owner_id"],
            name="fk_learning_card_tags_card_id_owner_id_learning_cards",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tag_id", "owner_id"],
            ["tags.id", "tags.owner_id"],
            name="fk_learning_card_tags_tag_id_owner_id_tags",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "card_id",
            "tag_id",
            name="pk_learning_card_tags",
        ),
    )
    op.create_index(
        "ix_learning_card_tags_tag_id_card_id",
        "learning_card_tags",
        ["tag_id", "card_id"],
        unique=False,
    )

    op.create_table(
        "review_batches",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "idempotency_key",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("algorithm_version", sa.Text(), nullable=False),
        sa.Column("item_count", sa.SmallInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(btrim(request_hash)) > 0",
            name="ck_review_batches_request_hash_nonblank",
        ),
        sa.CheckConstraint(
            "char_length(btrim(algorithm_version)) > 0",
            name="ck_review_batches_algorithm_version_nonblank",
        ),
        sa.CheckConstraint(
            "item_count BETWEEN 1 AND 10",
            name="ck_review_batches_item_count_range",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_review_batches_owner_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_review_batches"),
        sa.UniqueConstraint(
            "owner_id",
            "idempotency_key",
            name="uq_review_batches_owner_id_idempotency_key",
        ),
        sa.UniqueConstraint(
            "id",
            "owner_id",
            name="uq_review_batches_id_owner_id",
        ),
    )

    op.create_table(
        "review_states",
        sa.Column("card_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("review_stage", sa.SmallInteger(), nullable=False),
        sa.Column("ease_factor", sa.Numeric(3, 2), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "review_stage BETWEEN 1 AND 5",
            name="ck_review_states_review_stage_range",
        ),
        sa.CheckConstraint(
            "ease_factor BETWEEN 1.30 AND 2.50",
            name="ck_review_states_ease_factor_range",
        ),
        sa.CheckConstraint(
            "interval_days >= 0",
            name="ck_review_states_interval_days_nonnegative",
        ),
        sa.CheckConstraint(
            "version >= 1",
            name="ck_review_states_version_positive",
        ),
        sa.CheckConstraint(
            "last_reviewed_at IS NULL OR next_review_at >= last_reviewed_at",
            name="ck_review_states_next_review_not_before_last_review",
        ),
        sa.ForeignKeyConstraint(
            ["card_id", "owner_id"],
            ["learning_cards.id", "learning_cards.owner_id"],
            name="fk_review_states_card_id_owner_id_learning_cards",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("card_id", name="pk_review_states"),
    )
    op.create_index(
        "ix_review_states_owner_next_review_card",
        "review_states",
        ["owner_id", "next_review_at", "card_id"],
        unique=False,
    )

    op.create_table(
        "review_events",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("card_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("quality", sa.SmallInteger(), nullable=False),
        sa.Column("previous_review_stage", sa.SmallInteger(), nullable=False),
        sa.Column("resulting_review_stage", sa.SmallInteger(), nullable=False),
        sa.Column("previous_ease_factor", sa.Numeric(3, 2), nullable=False),
        sa.Column("resulting_ease_factor", sa.Numeric(3, 2), nullable=False),
        sa.Column("previous_interval_days", sa.Integer(), nullable=False),
        sa.Column("resulting_interval_days", sa.Integer(), nullable=False),
        sa.Column(
            "previous_last_reviewed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "resulting_last_reviewed_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "previous_next_review_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "resulting_next_review_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("previous_version", sa.Integer(), nullable=False),
        sa.Column("resulting_version", sa.Integer(), nullable=False),
        sa.Column("algorithm_version", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "decision IN ('no', 'no_a_bit', 'yes_a_bit', 'yes')",
            name="ck_review_events_decision_supported",
        ),
        sa.CheckConstraint(
            "quality IN (0, 2, 3, 5)",
            name="ck_review_events_quality_supported",
        ),
        sa.CheckConstraint(
            "(decision = 'no' AND quality = 0) "
            "OR (decision = 'no_a_bit' AND quality = 2) "
            "OR (decision = 'yes_a_bit' AND quality = 3) "
            "OR (decision = 'yes' AND quality = 5)",
            name="ck_review_events_decision_quality_match",
        ),
        sa.CheckConstraint(
            "previous_review_stage BETWEEN 1 AND 5 "
            "AND resulting_review_stage BETWEEN 1 AND 5",
            name="ck_review_events_review_stage_ranges",
        ),
        sa.CheckConstraint(
            "previous_ease_factor BETWEEN 1.30 AND 2.50 "
            "AND resulting_ease_factor BETWEEN 1.30 AND 2.50",
            name="ck_review_events_ease_factor_ranges",
        ),
        sa.CheckConstraint(
            "previous_interval_days >= 0 AND resulting_interval_days >= 0",
            name="ck_review_events_interval_days_nonnegative",
        ),
        sa.CheckConstraint(
            "previous_version >= 1 AND resulting_version = previous_version + 1",
            name="ck_review_events_version_transition",
        ),
        sa.CheckConstraint(
            "char_length(btrim(algorithm_version)) > 0",
            name="ck_review_events_algorithm_version_nonblank",
        ),
        sa.CheckConstraint(
            "previous_last_reviewed_at IS NULL "
            "OR previous_next_review_at >= previous_last_reviewed_at",
            name="ck_review_events_previous_schedule_ordered",
        ),
        sa.CheckConstraint(
            "previous_last_reviewed_at IS NULL "
            "OR reviewed_at >= previous_last_reviewed_at",
            name="ck_review_events_review_time_monotonic",
        ),
        sa.CheckConstraint(
            "resulting_last_reviewed_at = reviewed_at",
            name="ck_review_events_resulting_last_review_matches_review",
        ),
        sa.CheckConstraint(
            "resulting_next_review_at >= resulting_last_reviewed_at",
            name="ck_review_events_resulting_schedule_ordered",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id", "owner_id"],
            ["review_batches.id", "review_batches.owner_id"],
            name="fk_review_events_batch_id_owner_id_review_batches",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["card_id", "owner_id"],
            ["learning_cards.id", "learning_cards.owner_id"],
            name="fk_review_events_card_id_owner_id_learning_cards",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_review_events"),
        sa.UniqueConstraint(
            "batch_id",
            "card_id",
            name="uq_review_events_batch_id_card_id",
        ),
    )
    op.create_index(
        "ix_review_events_owner_reviewed_id",
        "review_events",
        ["owner_id", sa.text("reviewed_at DESC"), sa.text("id DESC")],
        unique=False,
    )
    op.create_index(
        "ix_review_events_card_reviewed_id",
        "review_events",
        ["card_id", sa.text("reviewed_at DESC"), sa.text("id DESC")],
        unique=False,
    )
    op.create_index(
        "ix_review_events_batch_id_id",
        "review_events",
        ["batch_id", "id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove review history and learning data in dependency order."""

    op.drop_index(
        "ix_review_events_batch_id_id",
        table_name="review_events",
    )
    op.drop_index(
        "ix_review_events_card_reviewed_id",
        table_name="review_events",
    )
    op.drop_index(
        "ix_review_events_owner_reviewed_id",
        table_name="review_events",
    )
    op.drop_table("review_events")

    op.drop_index(
        "ix_review_states_owner_next_review_card",
        table_name="review_states",
    )
    op.drop_table("review_states")
    op.drop_table("review_batches")

    op.drop_index(
        "ix_learning_card_tags_tag_id_card_id",
        table_name="learning_card_tags",
    )
    op.drop_table("learning_card_tags")
    op.drop_table("tags")

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
