"""Build display parts only from validated, successful tool outputs."""

from typing import Literal, TypedDict

from app.assistant.propose import ProposalResult, proposal_payload


class CardListItem(TypedDict):
    id: str
    deck_id: str
    term: str
    meaning: str


class CardListPayload(TypedDict):
    purpose: Literal["due", "search"]
    items: list[CardListItem]


class CardListPart(TypedDict):
    id: str
    type: Literal["card_list"]
    payload: CardListPayload


class CardProposalPart(TypedDict):
    id: str
    type: Literal["card_proposal"]
    payload: dict


AssistantPart = CardListPart | CardProposalPart


def build_part(
    name: str, output: dict, status: str, ordinal: int
) -> AssistantPart | None:
    if (
        status == "ok"
        and name == "propose_cards"
        and isinstance(output, ProposalResult)
        and output.get("status") == "ok"
    ):
        return {
            "id": f"p{ordinal}",
            "type": "card_proposal",
            "payload": proposal_payload(output),
        }
    if status != "ok" or name not in {"get_due_cards", "search_cards"}:
        return None
    items = output["items"]
    if not items or any(
        not all(
            isinstance(item.get(key), str)
            for key in ("id", "deck_id", "term", "meaning")
        )
        for item in items
    ):
        return None
    return {
        "id": f"p{ordinal}",
        "type": "card_list",
        "payload": {
            "purpose": "due" if name == "get_due_cards" else "search",
            "items": [
                {
                    "id": item["id"],
                    "deck_id": item["deck_id"],
                    "term": item["term"],
                    "meaning": item["meaning"],
                }
                for item in items
            ],
        },
    }
