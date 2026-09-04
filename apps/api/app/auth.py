"""Google ID-token authentication and stable internal-user resolution."""

from dataclasses import dataclass
from typing import Annotated, Any, Protocol

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token as google_id_token
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import database_session
from app.errors import ApiError

router = APIRouter(prefix="/v1")


@dataclass(frozen=True)
class VerifiedGoogleIdentity:
    """Allowlisted identity claims from one verified Google ID token."""

    subject: str
    email: str


@dataclass(frozen=True)
class AuthenticatedUser:
    """Internal authorization identity derived only by the backend."""

    id: int
    google_subject: str
    email: str


class TokenVerifier(Protocol):
    """Replaceable Google-token verification boundary."""

    def verify(self, token: str) -> VerifiedGoogleIdentity: ...


class GoogleTokenVerifier:
    """Verify Google signatures and claims for one configured OAuth audience."""

    def __init__(self, audience: str) -> None:
        self._audience = audience

    def verify(self, token: str) -> VerifiedGoogleIdentity:
        try:
            claims: dict[str, Any] = google_id_token.verify_oauth2_token(
                token,
                GoogleAuthRequest(),
                self._audience,
            )
        except ValueError:
            raise _invalid_credentials() from None
        except GoogleAuthError:
            raise ApiError(
                status_code=503,
                code="identity_provider_unavailable",
                message="Authentication is temporarily unavailable.",
                retryable=True,
            ) from None

        subject = claims.get("sub")
        email = claims.get("email")
        if (
            not isinstance(subject, str)
            or not subject.strip()
            or len(subject) > 255
            or not isinstance(email, str)
            or not email.strip()
            or len(email) > 320
            or claims.get("email_verified") is not True
        ):
            raise _invalid_credentials()

        return VerifiedGoogleIdentity(
            subject=subject.strip(),
            email=email.strip().casefold(),
        )


bearer_scheme = HTTPBearer(auto_error=False)


def _invalid_credentials() -> ApiError:
    return ApiError(
        status_code=401,
        code="invalid_authentication",
        message="Authentication credentials are invalid.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _credentials(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> str:
    if credentials is None:
        raise ApiError(
            status_code=401,
            code="authentication_required",
            message="Authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if credentials.scheme.casefold() != "bearer" or not credentials.credentials:
        raise _invalid_credentials()
    return credentials.credentials


def current_user(
    request: Request,
    token: Annotated[str, Depends(_credentials)],
    session: Annotated[Session, Depends(database_session)],
) -> AuthenticatedUser:
    """Verify identity, upsert by Google subject, and return internal ownership."""

    identity = request.app.state.token_verifier.verify(token)
    existing = (
        session.execute(
            text(
                """
                SELECT id, google_subject, normalized_email
                FROM users
                WHERE google_subject = :subject
                """
            ),
            {"subject": identity.subject},
        )
        .mappings()
        .one_or_none()
    )
    if existing is not None and existing.normalized_email == identity.email:
        row = existing
    elif existing is not None:
        row = (
            session.execute(
                text(
                    """
                    UPDATE users
                    SET normalized_email = :email, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                    RETURNING id, google_subject, normalized_email
                    """
                ),
                {"id": existing.id, "email": identity.email},
            )
            .mappings()
            .one()
        )
    else:
        row = (
            session.execute(
                text(
                    """
                    INSERT INTO users (google_subject, normalized_email)
                    VALUES (:subject, :email)
                    ON CONFLICT (google_subject) DO NOTHING
                    RETURNING id, google_subject, normalized_email
                    """
                ),
                {"subject": identity.subject, "email": identity.email},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            row = (
                session.execute(
                    text(
                        """
                        SELECT id, google_subject, normalized_email
                        FROM users
                        WHERE google_subject = :subject
                        """
                    ),
                    {"subject": identity.subject},
                )
                .mappings()
                .one()
            )
    return AuthenticatedUser(
        id=row.id,
        google_subject=row.google_subject,
        email=row.normalized_email,
    )


CurrentUserDependency = Annotated[AuthenticatedUser, Depends(current_user)]


@router.get("/me")
def get_me(user: CurrentUserDependency) -> dict[str, object]:
    """Return the authenticated internal identity without exposing Google subject."""

    return {"id": user.id, "email": user.email}
