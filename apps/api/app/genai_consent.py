"""Authenticated consent and the shared boundary before sending content to GenAI."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import CurrentUserDependency
from app.database import database_session
from app.errors import ApiError

router = APIRouter(prefix="/v1/me/genai-consent")
SessionDependency = Annotated[Session, Depends(database_session, scope="function")]


class GenAIConsentResponse(BaseModel):
    genai_consent_at: datetime | None


def has_genai_consent(session: Session, owner_id: int, *, lock: bool = False) -> bool:
    """Read fresh consent; hold a shared user lock when serializing with withdrawal.

    Callers that persist derived data must keep this lock until their write commits.
    Never cache this decision in the authenticated identity or a background task.
    """
    return (
        session.execute(
            text(
                "SELECT genai_consent_at FROM users WHERE id = :owner_id"
                + (" FOR SHARE" if lock else "")
            ),
            {"owner_id": owner_id},
        ).scalar_one_or_none()
        is not None
    )


def require_genai_consent(session: Session, owner_id: int) -> None:
    """Reject before external processing and serialize the request with withdrawal."""
    if not has_genai_consent(session, owner_id, lock=True):
        raise ApiError(
            status_code=403,
            code="genai_consent_required",
            message="Consent is required to send card text and search queries to Google Vertex AI.",
        )


@router.get("", response_model=GenAIConsentResponse)
def read_consent(
    user: CurrentUserDependency, session: SessionDependency
) -> GenAIConsentResponse:
    return GenAIConsentResponse(
        genai_consent_at=session.execute(
            text("SELECT genai_consent_at FROM users WHERE id = :owner_id"),
            {"owner_id": user.id},
        ).scalar_one()
    )


@router.put("", response_model=GenAIConsentResponse)
def grant_consent(
    user: CurrentUserDependency, session: SessionDependency
) -> GenAIConsentResponse:
    """Grant only the caller's consent; repeated grants retain the original time."""
    return GenAIConsentResponse(
        genai_consent_at=session.execute(
            text("""
                UPDATE users
                SET genai_consent_at = COALESCE(genai_consent_at, clock_timestamp())
                WHERE id = :owner_id RETURNING genai_consent_at
            """),
            {"owner_id": user.id},
        ).scalar_one()
    )


@router.delete("", response_model=GenAIConsentResponse)
def withdraw_consent(
    user: CurrentUserDependency, session: SessionDependency
) -> GenAIConsentResponse:
    """Clear consent and all owned embeddings in the same request transaction."""
    session.execute(
        text("UPDATE users SET genai_consent_at = NULL WHERE id = :owner_id"),
        {"owner_id": user.id},
    )
    session.execute(
        text("DELETE FROM card_embeddings WHERE owner_id = :owner_id"),
        {"owner_id": user.id},
    )
    return GenAIConsentResponse(genai_consent_at=None)
