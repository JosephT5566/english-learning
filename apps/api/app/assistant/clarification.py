"""Ephemeral clarification data; correlation ids never grant authority."""

from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from sqlalchemy import text

QuestionText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
]
OptionLabel = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
]


class ClarificationOption(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    label: OptionLabel


class ClarificationArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    question: QuestionText
    options: Annotated[list[ClarificationOption], Field(max_length=4)] = []
    allow_free_text: bool
    purpose: Literal["term", "other"] = "term"

    @model_validator(mode="after")
    def answerable(self):
        if not self.options and not self.allow_free_text:
            raise ValueError("an option or free text is required")
        return self


ASK_SCHEMA = {
    "name": "ask_clarification",
    "description": "Ask about an ambiguous term or scope before proposing drafts. Never ask for optional fields or deck ids.",
    "parameters": {
        "type": "object",
        "properties": {
            "question": {"type": "string"},
            "options": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"label": {"type": "string"}},
                    "required": ["label"],
                },
            },
            "allow_free_text": {"type": "boolean"},
            "purpose": {"type": "string", "enum": ["term", "other"]},
        },
        "required": ["question", "allow_free_text"],
    },
}


def clarification_count(messages):
    return sum(
        part.get("type") == "clarification_question" and part.get("purpose") != "deck"
        for message in messages
        if message["role"] == "assistant"
        for part in message.get("parts", [])
    )


def ask_clarification(arguments, messages=()):
    if clarification_count(messages) >= 3:
        return {"error": "clarification_limit"}
    validated = ClarificationArguments.model_validate(arguments)
    return {
        "status": "ok",
        "question_id": str(uuid4()),
        "question": validated.question,
        "options": [
            {"id": str(uuid4()), "label": option.label} for option in validated.options
        ],
        "allow_free_text": validated.allow_free_text,
        "purpose": validated.purpose,
    }


def deck_question(decks):
    return {
        "question_id": str(uuid4()),
        "question": "Which deck should these drafts use?"
        if decks
        else "No active decks are available. Create a deck before proposing cards.",
        "options": [
            {"id": str(uuid4()), "label": deck["title"], "deck_id": deck["id"]}
            for deck in decks[:20]
        ],
        "allow_free_text": False,
        "purpose": "deck",
    }


def fill_deck_answer(session, owner_id, arguments, messages):
    if arguments.get("deck_id") is not None:
        return arguments
    for message in reversed(messages):
        if message["role"] != "user":
            continue
        for part in reversed(message.get("parts", [])):
            if part.get("type") != "clarification_answer" or not part.get("deck_id"):
                continue
            # The client-supplied correlation/option ids are not authorization.
            try:
                deck_id = UUID(str(part["deck_id"]))
            except (ValueError, TypeError, AttributeError):
                return {"error": "deck_not_found"}
            row = (
                session.execute(
                    text("""
                SELECT id FROM learning_decks
                WHERE id = :id AND owner_id = :owner_id AND archived_at IS NULL
            """),
                    {"id": deck_id, "owner_id": owner_id},
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return {"error": "deck_not_found"}
            return {**arguments, "deck_id": str(deck_id)}
    return arguments


def question_text(payload):
    lines = [payload["question"]]
    lines.extend(
        f"{index}. {option['label']}"
        for index, option in enumerate(payload["options"], 1)
    )
    return "\n".join(lines)


class HistoryOption(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: UUID
    label: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    deck_id: UUID | None = None

    @field_validator("id", "deck_id", mode="before")
    @classmethod
    def parse_uuid(cls, value):
        return UUID(value) if isinstance(value, str) else value


class HistoryClarificationQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: Literal["clarification_question"]
    question_id: UUID
    question: QuestionText
    options: Annotated[list[HistoryOption], Field(max_length=20)]
    allow_free_text: bool
    purpose: Literal["deck", "term", "other"] = "term"

    @field_validator("question_id", mode="before")
    @classmethod
    def parse_uuid(cls, value):
        return UUID(value) if isinstance(value, str) else value

    @model_validator(mode="after")
    def valid_options(self):
        if len({o.id for o in self.options}) != len(self.options):
            raise ValueError("duplicate option ids")
        if self.purpose == "deck":
            if self.allow_free_text or any(o.deck_id is None for o in self.options):
                raise ValueError("deck questions require deck options and no free text")
        elif (
            len(self.options) > 4
            or any(o.deck_id is not None or len(o.label) > 80 for o in self.options)
            or (not self.options and not self.allow_free_text)
        ):
            raise ValueError("invalid term/scope options")
        return self


class HistoryClarificationAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: Literal["clarification_answer"]
    question_id: UUID
    option_id: UUID | None = None
    text: (
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=100000),
        ]
        | None
    ) = None
    deck_id: UUID | None = None

    @field_validator("question_id", "option_id", "deck_id", mode="before")
    @classmethod
    def parse_uuid(cls, value):
        return UUID(value) if isinstance(value, str) else value

    @model_validator(mode="after")
    def answered(self):
        if self.option_id is None and not self.text:
            raise ValueError("an option or text is required")
        return self
