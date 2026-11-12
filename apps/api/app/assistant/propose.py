"""Validate and prepare ephemeral card proposals using only owner-bound reads."""

import unicodedata
from collections import Counter, defaultdict
from uuid import UUID, uuid4

from pydantic import ConfigDict
from sqlalchemy import text

from app.writes import CardDrafts, CardFields


class ProposeArguments(CardDrafts):
    model_config = ConfigDict(extra="forbid", strict=True)
    deck_id: UUID | None = None


# Hand-written function declaration: provider schemas do not use the response
# schema projection, so array/length/dependent constraints stay server-side.
PROPOSE_SCHEMA = {
    "name": "propose_cards",
    "description": "Propose owned card drafts without writing or saving cards.",
    "parameters": {
        "type": "object",
        "properties": {
            "deck_id": {"type": "string"},
            "cards": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "term": {"type": "string"},
                        "meaning": {"type": "string"},
                        "reading": {"type": "string"},
                        "pronunciation": {"type": "string"},
                        "romanization": {"type": "string"},
                        "target_language_definition": {"type": "string"},
                        "example_sentence": {"type": "string"},
                        "example_translation": {"type": "string"},
                        "example_source": {"type": "string"},
                        "synonyms": {"type": "array", "items": {"type": "string"}},
                        "antonyms": {"type": "array", "items": {"type": "string"}},
                        "part_of_speech": {"type": "string"},
                        "part_of_speech_detail": {"type": "string"},
                        "note": {"type": "string"},
                        "supplementary_note": {"type": "string"},
                        "learned_on": {"type": "string"},
                    },
                    "required": ["term", "meaning"],
                },
            },
        },
        "required": ["cards"],
    },
}


class ProposalResult(dict):
    """Compact functionResponse with separately held, validated display content."""

    def __init__(self, *, deck, drafts, warnings):
        super().__init__(
            status="ok",
            proposal_id=str(uuid4()),
            deck_id=deck["id"],
            card_count=len(drafts),
            warnings=warnings,
        )
        self.deck = deck
        self.drafts = drafts


def normalize_term(term):
    return unicodedata.normalize("NFC", term).strip().casefold()


def deck_summary(row):
    return {
        "id": str(row["id"]),
        "title": row["title"],
        "target_language": row["target_language"],
    }


def propose_cards(session, owner_id, arguments):
    # Reuse the content envelope rather than any HTTP handler or write model.
    drafts = CardDrafts.model_validate({"cards": arguments["cards"]}).cards
    if arguments.get("deck_id") is not None:
        row = (
            session.execute(
                text("""
                SELECT id, title, target_language, archived_at FROM learning_decks
                WHERE id = :id AND owner_id = :owner_id
            """),
                {"id": arguments["deck_id"], "owner_id": owner_id},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return {"error": "deck_not_found"}
        if row.get("archived_at") is not None:
            return {"error": "deck_archived"}
        deck = deck_summary(row)
    else:
        rows = (
            session.execute(
                text("""
                SELECT id, title, target_language FROM learning_decks
                WHERE owner_id = :owner_id AND archived_at IS NULL
                ORDER BY updated_at DESC, id DESC LIMIT 21
            """),
                {"owner_id": owner_id},
            )
            .mappings()
            .all()
        )
        if len(rows) != 1:
            return {
                "status": "needs_deck",
                "decks": [deck_summary(r) for r in rows[:20]],
            }
        deck = deck_summary(rows[0])

    rows = (
        session.execute(
            text("""
            SELECT c.id, c.term FROM learning_cards c
            JOIN learning_decks d ON (d.id, d.owner_id) = (c.deck_id, c.owner_id)
            WHERE c.owner_id = :owner_id AND d.owner_id = :owner_id
              AND c.deck_id = :deck_id
              AND c.archived_at IS NULL AND d.archived_at IS NULL
            ORDER BY c.id
        """),
            {"owner_id": owner_id, "deck_id": deck["id"]},
        )
        .mappings()
        .all()
    )
    existing = defaultdict(list)
    for row in rows:
        existing[normalize_term(row["term"])].append(str(row["id"]))
    counts = Counter(normalize_term(card.term) for card in drafts)
    warnings = [
        {
            "code": "duplicate_term",
            "term": card.term,
            "draft_index": index,
            "existing_card_ids": existing[normalize_term(card.term)],
        }
        for index, card in enumerate(drafts)
        if counts[normalize_term(card.term)] > 1 or existing[normalize_term(card.term)]
    ]
    return ProposalResult(deck=deck, drafts=drafts, warnings=warnings)


def proposal_payload(output: ProposalResult):
    """Allow-list every wire field; no raw arguments or executor dict is copied."""
    return {
        "proposal_id": output["proposal_id"],
        "deck": {key: output.deck[key] for key in ("id", "title", "target_language")},
        "drafts": [
            card.model_dump(mode="json", include=set(CardFields.model_fields))
            for card in output.drafts
        ],
        "warnings": [
            {
                key: warning[key]
                for key in ("code", "term", "draft_index", "existing_card_ids")
            }
            for warning in output["warnings"]
        ],
    }
