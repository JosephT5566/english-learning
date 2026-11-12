"""Re-read client-held ids as owner-scoped data, never tool calls or authority."""

from sqlalchemy import bindparam, text
from sqlalchemy.exc import SQLAlchemyError

from app.assistant.tools import (
    AssistantDeadlineExceeded,
    check_budget,
    set_query_budget,
)


def resolve_card_refs(session, owner_id, ids, deadline, cancelled):
    try:
        set_query_budget(session, deadline, readonly=True, cancelled=cancelled)
        rows = (
            session.execute(
                text("""
                SELECT c.id, c.deck_id, c.term
                FROM learning_cards c
                JOIN learning_decks d ON (d.id, d.owner_id) = (c.deck_id, c.owner_id)
                WHERE c.owner_id = :owner_id AND d.owner_id = :owner_id
                  AND c.archived_at IS NULL AND d.archived_at IS NULL
                  AND c.id IN :ids
            """).bindparams(bindparam("ids", expanding=True)),
                {"owner_id": owner_id, "ids": list(ids)},
            )
            .mappings()
            .all()
        )
        check_budget(deadline, cancelled)
        return {
            row["id"]: {
                "id": str(row["id"]),
                "deck_id": str(row["deck_id"]),
                "term": row["term"],
            }
            for row in rows
        }
    except SQLAlchemyError as error:
        if getattr(getattr(error, "orig", None), "sqlstate", None) == "57014":
            raise AssistantDeadlineExceeded() from None
        raise
    finally:
        session.rollback()
