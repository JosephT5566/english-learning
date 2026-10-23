"""Explicit content-only projection shared by publication boundaries."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.reads import TargetLanguage


class PublicReviewCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    target_language: TargetLanguage
    term: str
    meaning: str
    pronunciation: str | None
    reading: str | None
    romanization: str | None
    part_of_speech: str | None
    part_of_speech_detail: str | None
    target_language_definition: str | None
    example_sentence: str | None
    example_translation: str | None
    synonyms: list[str]
    antonyms: list[str]


PUBLIC_CARD_PROJECTION = """
    SELECT c.id, d.target_language, c.term, c.meaning,
           c.pronunciation, c.reading, c.romanization,
           c.part_of_speech, c.part_of_speech_detail,
           c.target_language_definition, c.example_sentence, c.example_translation,
           c.synonyms, c.antonyms
    FROM learning_cards AS c
    JOIN learning_decks AS d ON d.id = c.deck_id AND d.owner_id = c.owner_id
"""
