"""Owner-derived deck and card creation, editing, and archival."""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import CurrentUserDependency
from app.database import database_session
from app.errors import ApiError
from app.reads import (
    CARD_DETAIL_COLUMNS,
    DECK_COLUMNS,
    CardDetail,
    Deck,
    _not_found,
    _reject_unknown_filters,
)

router = APIRouter(prefix="/v1")
SessionDependency = Annotated[Session, Depends(database_session)]
Title = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
Term = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
]
Meaning = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]
ShortText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
]
Definition = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]
Example = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
]
Source = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]
Note = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
]
PartOfSpeech = Literal[
    "noun",
    "verb",
    "adjective",
    "adverb",
    "pronoun",
    "determiner",
    "preposition",
    "conjunction",
    "interjection",
    "particle",
    "auxiliary",
    "numeral",
    "phrase",
    "other",
]


class WriteModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeckCreate(WriteModel):
    title: Title
    target_language: Literal["en", "ja"]
    explanation_language: Literal["en", "ja", "zh-TW"]


class DeckUpdate(WriteModel):
    version: Annotated[int, Field(ge=1)]
    title: Title | None = None
    explanation_language: Literal["en", "ja", "zh-TW"] | None = None

    @model_validator(mode="after")
    def require_change(self) -> "DeckUpdate":
        if not (self.model_fields_set - {"version"}):
            raise ValueError("at least one editable field is required")
        return self


class CardFields(WriteModel):
    term: Term
    meaning: Meaning
    reading: ShortText | None = None
    pronunciation: ShortText | None = None
    romanization: ShortText | None = None
    target_language_definition: Definition | None = None
    example_sentence: Example | None = None
    example_translation: Example | None = None
    example_source: Source | None = None
    synonyms: Annotated[list[ShortText], Field(max_length=20)] = []
    antonyms: Annotated[list[ShortText], Field(max_length=20)] = []
    part_of_speech: PartOfSpeech | None = None
    part_of_speech_detail: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    ] = None
    note: Note | None = None
    supplementary_note: Note | None = None
    learned_on: date | None = None

    @model_validator(mode="after")
    def validate_dependent_fields(self) -> "CardFields":
        if self.example_sentence is None and (
            self.example_translation is not None or self.example_source is not None
        ):
            raise ValueError("example translation and source require a sentence")
        if self.part_of_speech == "other" and self.part_of_speech_detail is None:
            raise ValueError("other part of speech requires detail")
        return self


class CardCreate(CardFields):
    deck_id: UUID


class CardUpdate(WriteModel):
    version: Annotated[int, Field(ge=1)]
    term: Term | None = None
    meaning: Meaning | None = None
    reading: ShortText | None = None
    pronunciation: ShortText | None = None
    romanization: ShortText | None = None
    target_language_definition: Definition | None = None
    example_sentence: Example | None = None
    example_translation: Example | None = None
    example_source: Source | None = None
    synonyms: Annotated[list[ShortText] | None, Field(max_length=20)] = None
    antonyms: Annotated[list[ShortText] | None, Field(max_length=20)] = None
    part_of_speech: PartOfSpeech | None = None
    part_of_speech_detail: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    ] = None
    note: Note | None = None
    supplementary_note: Note | None = None
    learned_on: date | None = None

    @model_validator(mode="after")
    def require_change(self) -> "CardUpdate":
        if not (self.model_fields_set - {"version"}):
            raise ValueError("at least one editable field is required")
        return self


def _card_detail(session: Session, card_id: UUID, owner_id: int) -> CardDetail:
    row = (
        session.execute(
            text(
                f"""
                SELECT {CARD_DETAIL_COLUMNS}
                FROM learning_cards AS c
                JOIN learning_decks AS d
                  ON (d.id, d.owner_id) = (c.deck_id, c.owner_id)
                LEFT JOIN review_states AS s
                  ON (s.card_id, s.owner_id) = (c.id, c.owner_id)
                WHERE c.id = :id AND c.owner_id = :owner_id
                """
            ),
            {"id": card_id, "owner_id": owner_id},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise _not_found("card")
    return CardDetail.model_validate(row)


def _version_conflict() -> ApiError:
    return ApiError(
        status_code=409,
        code="version_conflict",
        message="The resource changed since it was read.",
    )


@router.post("/decks", response_model=Deck, status_code=status.HTTP_201_CREATED)
def create_deck(
    request: Request,
    payload: Annotated[DeckCreate, Body()],
    session: SessionDependency,
    user: CurrentUserDependency,
) -> Deck:
    _reject_unknown_filters(request, set())
    row = (
        session.execute(
            text(
                f"""
                INSERT INTO learning_decks (
                    owner_id, title, target_language, explanation_language
                ) VALUES (
                    :owner_id, :title, :target_language, :explanation_language
                )
                RETURNING {DECK_COLUMNS.replace("d.", "")}
                """
            ),
            {"owner_id": user.id, **payload.model_dump()},
        )
        .mappings()
        .one()
    )
    return Deck.model_validate(row)


@router.patch("/decks/{deck_id}", response_model=Deck)
def update_deck(
    deck_id: UUID,
    request: Request,
    payload: Annotated[DeckUpdate, Body()],
    session: SessionDependency,
    user: CurrentUserDependency,
) -> Deck:
    _reject_unknown_filters(request, set())
    changes = payload.model_dump(exclude={"version"}, exclude_unset=True)
    assignments = [f"{field} = :{field}" for field in changes]
    assignments.extend(["version = version + 1", "updated_at = CURRENT_TIMESTAMP"])
    row = (
        session.execute(
            text(
                f"""
                UPDATE learning_decks
                SET {", ".join(assignments)}
                WHERE id = :id AND owner_id = :owner_id AND version = :version
                RETURNING {DECK_COLUMNS.replace("d.", "")}
                """
            ),
            {
                "id": deck_id,
                "owner_id": user.id,
                "version": payload.version,
                **changes,
            },
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        owned = session.execute(
            text(
                "SELECT 1 FROM learning_decks WHERE id = :id AND owner_id = :owner_id"
            ),
            {"id": deck_id, "owner_id": user.id},
        ).scalar_one_or_none()
        if owned is None:
            raise _not_found("deck")
        raise _version_conflict()
    return Deck.model_validate(row)


@router.delete("/decks/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_deck(
    deck_id: UUID,
    request: Request,
    session: SessionDependency,
    user: CurrentUserDependency,
) -> Response:
    _reject_unknown_filters(request, set())
    archived = session.execute(
        text(
            """
            UPDATE learning_decks
            SET archived_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP,
                version = version + 1
            WHERE id = :id AND owner_id = :owner_id AND archived_at IS NULL
            RETURNING id
            """
        ),
        {"id": deck_id, "owner_id": user.id},
    ).scalar_one_or_none()
    if archived is None:
        owned = session.execute(
            text(
                "SELECT 1 FROM learning_decks WHERE id = :id AND owner_id = :owner_id"
            ),
            {"id": deck_id, "owner_id": user.id},
        ).scalar_one_or_none()
        if owned is None:
            raise _not_found("deck")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/cards", response_model=CardDetail, status_code=status.HTTP_201_CREATED)
def create_card(
    request: Request,
    payload: Annotated[CardCreate, Body()],
    session: SessionDependency,
    user: CurrentUserDependency,
) -> CardDetail:
    _reject_unknown_filters(request, set())
    deck_archived = session.execute(
        text(
            "SELECT archived_at FROM learning_decks WHERE id = :id AND owner_id = :owner_id"
        ),
        {"id": payload.deck_id, "owner_id": user.id},
    ).one_or_none()
    if deck_archived is None:
        raise _not_found("deck")
    if deck_archived[0] is not None:
        raise ApiError(
            status_code=409,
            code="deck_archived",
            message="Cards cannot be added to an archived deck.",
        )

    values = payload.model_dump()
    columns = ["owner_id", *values]
    card_id = session.execute(
        text(
            f"""
            INSERT INTO learning_cards ({", ".join(columns)})
            VALUES ({", ".join(f":{column}" for column in columns)})
            RETURNING id
            """
        ),
        {"owner_id": user.id, **values},
    ).scalar_one()
    return _card_detail(session, card_id, user.id)


@router.patch("/cards/{card_id}", response_model=CardDetail)
def update_card(
    card_id: UUID,
    request: Request,
    payload: Annotated[CardUpdate, Body()],
    session: SessionDependency,
    user: CurrentUserDependency,
) -> CardDetail:
    _reject_unknown_filters(request, set())
    changes = payload.model_dump(exclude={"version"}, exclude_unset=True)
    assignments = [f"{field} = :{field}" for field in changes]
    assignments.extend(["version = version + 1", "updated_at = CURRENT_TIMESTAMP"])
    updated = session.execute(
        text(
            f"""
            UPDATE learning_cards
            SET {", ".join(assignments)}
            WHERE id = :id AND owner_id = :owner_id AND version = :version
            RETURNING id
            """
        ),
        {
            "id": card_id,
            "owner_id": user.id,
            "version": payload.version,
            **changes,
        },
    ).scalar_one_or_none()
    if updated is None:
        owned = session.execute(
            text(
                "SELECT 1 FROM learning_cards WHERE id = :id AND owner_id = :owner_id"
            ),
            {"id": card_id, "owner_id": user.id},
        ).scalar_one_or_none()
        if owned is None:
            raise _not_found("card")
        raise _version_conflict()
    return _card_detail(session, card_id, user.id)


@router.delete("/cards/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_card(
    card_id: UUID,
    request: Request,
    session: SessionDependency,
    user: CurrentUserDependency,
) -> Response:
    _reject_unknown_filters(request, set())
    archived = session.execute(
        text(
            """
            UPDATE learning_cards
            SET archived_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP,
                version = version + 1
            WHERE id = :id AND owner_id = :owner_id AND archived_at IS NULL
            RETURNING id
            """
        ),
        {"id": card_id, "owner_id": user.id},
    ).scalar_one_or_none()
    if archived is None:
        owned = session.execute(
            text(
                "SELECT 1 FROM learning_cards WHERE id = :id AND owner_id = :owner_id"
            ),
            {"id": card_id, "owner_id": user.id},
        ).scalar_one_or_none()
        if owned is None:
            raise _not_found("card")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
