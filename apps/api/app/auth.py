"""Google ID-token authentication and stable internal-user resolution."""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Annotated, Any, Protocol
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token as google_id_token
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import bind_owner, database_session
from app.errors import ApiError

router = APIRouter(prefix="/v1")


@dataclass(frozen=True)
class VerifiedGoogleIdentity:
    """Allowlisted identity claims from one verified Google ID token."""

    subject: str
    email: str
    name: str | None = None
    picture: str | None = None


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
            name=claims.get("name") if isinstance(claims.get("name"), str) else None,
            picture=claims.get("picture")
            if isinstance(claims.get("picture"), str)
            else None,
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


def _allowed(request: Request, email: str) -> bool:
    allowed = request.app.state.settings.google_allowed_emails
    return not allowed or email.casefold() in allowed.split(",")


def _account_not_allowed() -> ApiError:
    return ApiError(
        status_code=403,
        code="account_not_allowed",
        message="This account is not allowed to use the application.",
    )


def _upsert_user(session: Session, identity: VerifiedGoogleIdentity):
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
    return row


def auth_clock() -> datetime:
    """Injectable UTC clock for session expiry and reuse boundaries."""
    return datetime.now(UTC)


def new_token(prefix: str) -> str:
    return prefix + secrets.token_urlsafe(32)


def token_hash(token: str) -> bytes:
    return sha256(token.encode("utf-8")).digest()


def _access_token(token: Annotated[str, Depends(_credentials)]) -> str:
    if not token.startswith("ela_"):
        raise _invalid_credentials()
    return token


def _auth_error(code: str, status: int = 401) -> ApiError:
    return ApiError(
        status_code=status,
        code=code,
        message="The application session is no longer valid.",
        headers={"Cache-Control": "no-store", "WWW-Authenticate": "Bearer"},
    )


def _revoke(session: Session, session_id, reason: str, now: datetime) -> None:
    session.execute(
        text("""
        UPDATE auth_sessions SET revoked_at = :now, revoked_reason = :reason
        WHERE id = :id AND revoked_at IS NULL
    """),
        {"id": session_id, "now": now, "reason": reason},
    )
    session.execute(
        text("DELETE FROM auth_access_tokens WHERE session_id = :id"),
        {"id": session_id},
    )


def _check_allowlist(request: Request, session: Session, row, now: datetime) -> None:
    if row.principal_kind != "human":
        raise _invalid_credentials()
    if row.revoked_reason == "allowlist" or not _allowed(request, row.normalized_email):
        _revoke(session, row.id, "allowlist", now)
        # Auth failures roll back the request dependency; persist revocation first.
        session.commit()
        raise _account_not_allowed()


def current_user(
    request: Request,
    token: Annotated[str, Depends(_access_token)],
    session: Annotated[Session, Depends(database_session, scope="function")],
) -> AuthenticatedUser:
    row = (
        session.execute(
            text("""
        SELECT s.*, a.expires_at, u.google_subject, u.normalized_email
        FROM auth_access_tokens a JOIN auth_sessions s ON s.id = a.session_id
        JOIN users u ON u.id = s.user_id WHERE a.token_hash = :hash
    """),
            {"hash": token_hash(token)},
        )
        .mappings()
        .one_or_none()
    )
    now = auth_clock()
    if row is None or row.revoked_at is not None:
        raise _invalid_credentials()
    _check_allowlist(request, session, row, now)
    if row.idle_expires_at <= now or row.absolute_expires_at <= now:
        raise _invalid_credentials()
    if row.expires_at <= now:
        raise _auth_error("access_token_expired")
    bind_owner(session, row.user_id)
    return AuthenticatedUser(
        id=row.user_id, google_subject=row.google_subject, email=row.normalized_email
    )


CurrentUserDependency = Annotated[AuthenticatedUser, Depends(current_user)]
DatabaseSession = Annotated[Session, Depends(database_session, scope="function")]


class SessionCredential(BaseModel):
    model_config = ConfigDict(extra="forbid")
    credential: SecretStr = Field(min_length=1, max_length=16384)


class RefreshCredential(BaseModel):
    model_config = ConfigDict(extra="forbid")
    refresh_token: SecretStr = Field(min_length=1, max_length=256)


class LogoutCredential(BaseModel):
    model_config = ConfigDict(extra="forbid")
    refresh_token: SecretStr | None = Field(default=None, min_length=1, max_length=256)


class SessionUser(BaseModel):
    id: int
    email: str


class SessionProfile(BaseModel):
    name: str | None = None
    picture: str | None = None


class SessionTokens(BaseModel):
    access_token: str = Field(repr=False)
    access_expires_at: AwareDatetime
    refresh_token: str = Field(repr=False)
    refresh_expires_at: AwareDatetime
    user: SessionUser
    profile: SessionProfile


def _verified_identity(
    request: Request, payload: SessionCredential
) -> VerifiedGoogleIdentity:
    identity = request.app.state.token_verifier.verify(
        payload.credential.get_secret_value()
    )
    if not _allowed(request, identity.email):
        raise _account_not_allowed()
    return identity


def _refresh_token(payload: RefreshCredential) -> str:
    token = payload.refresh_token.get_secret_value()
    if not token.startswith("elr_"):
        raise _auth_error("refresh_invalid")
    return token


def _cleanup(session: Session, user_id: int, now: datetime) -> None:
    session.execute(
        text("""
        DELETE FROM auth_access_tokens a USING auth_sessions s
        WHERE a.session_id = s.id AND s.user_id = :user AND a.expires_at <= :now
    """),
        {"user": user_id, "now": now},
    )
    session.execute(
        text("""
        DELETE FROM auth_sessions WHERE user_id = :user
        AND (idle_expires_at <= :now OR absolute_expires_at <= :now)
    """),
        {"user": user_id, "now": now},
    )


def _issue(
    session: Session, settings, row, now: datetime, profile: SessionProfile
) -> SessionTokens:
    access = new_token("ela_")
    refresh = new_token("elr_")
    access_expiry = now + timedelta(seconds=settings.auth_access_ttl_seconds)
    session.execute(
        text("""
        INSERT INTO auth_access_tokens (token_hash, session_id, expires_at)
        VALUES (:hash, :id, :expiry)
    """),
        {"hash": token_hash(access), "id": row.id, "expiry": access_expiry},
    )
    session.execute(
        text("""
        INSERT INTO auth_refresh_tokens (token_hash, session_id, issued_at)
        VALUES (:hash, :id, :now)
    """),
        {"hash": token_hash(refresh), "id": row.id, "now": now},
    )
    return SessionTokens(
        access_token=access,
        access_expires_at=access_expiry,
        refresh_token=refresh,
        refresh_expires_at=row.idle_expires_at,
        user=SessionUser(id=row.user_id, email=row.normalized_email),
        profile=profile,
    )


@router.post("/auth/session", response_model=SessionTokens)
def exchange_session(
    request: Request,
    response: Response,
    identity: Annotated[VerifiedGoogleIdentity, Depends(_verified_identity)],
    session: DatabaseSession,
) -> SessionTokens:
    response.headers["Cache-Control"] = "no-store"
    user = _upsert_user(session, identity)
    settings = request.app.state.settings
    now = auth_clock()
    _cleanup(session, user.id, now)
    absolute = now + timedelta(seconds=settings.auth_refresh_absolute_ttl_seconds)
    idle = min(
        absolute, now + timedelta(seconds=settings.auth_refresh_idle_ttl_seconds)
    )
    row = (
        session.execute(
            text("""
        INSERT INTO auth_sessions (id, user_id, principal_kind, created_at,
            last_refreshed_at, idle_expires_at, absolute_expires_at)
        VALUES (:id, :user, 'human', :now, :now, :idle, :absolute)
        RETURNING *
    """),
            {
                "id": uuid4(),
                "user": user.id,
                "now": now,
                "idle": idle,
                "absolute": absolute,
            },
        )
        .mappings()
        .one()
    )
    return _issue(
        session,
        settings,
        _IssueIdentity(row.id, row.user_id, idle, user.normalized_email),
        now,
        SessionProfile(name=identity.name, picture=identity.picture),
    )


@dataclass(frozen=True)
class _IssueIdentity:
    id: object
    user_id: int
    idle_expires_at: datetime
    normalized_email: str


def _locked_session(session: Session, token: str):
    # Look up the family first, then lock and re-read the token after any waiter.
    session_id = session.execute(
        text("SELECT session_id FROM auth_refresh_tokens WHERE token_hash = :hash"),
        {"hash": token_hash(token)},
    ).scalar_one_or_none()
    if session_id is None:
        return None
    return (
        session.execute(
            text("""
        SELECT s.*, u.google_subject, u.normalized_email
        FROM auth_sessions s JOIN users u ON u.id = s.user_id
        WHERE s.id = :id FOR UPDATE OF s
    """),
            {"id": session_id},
        )
        .mappings()
        .one_or_none()
    )


@router.post("/auth/refresh", response_model=SessionTokens)
def refresh_session(
    request: Request,
    response: Response,
    token: Annotated[str, Depends(_refresh_token)],
    session: DatabaseSession,
) -> SessionTokens:
    response.headers["Cache-Control"] = "no-store"
    row = _locked_session(session, token)
    now = auth_clock()
    if row is None:
        raise _auth_error("refresh_invalid")
    _check_allowlist(request, session, row, now)
    if row.revoked_at is not None:
        raise _auth_error("refresh_invalid")
    if row.idle_expires_at <= now or row.absolute_expires_at <= now:
        _cleanup(session, row.user_id, now)
        session.commit()
        raise _auth_error("refresh_invalid")
    rotated = session.execute(
        text("SELECT rotated_at FROM auth_refresh_tokens WHERE token_hash = :hash"),
        {"hash": token_hash(token)},
    ).scalar_one()
    settings = request.app.state.settings
    if rotated is not None:
        if (now - rotated).total_seconds() <= settings.auth_refresh_reuse_grace_seconds:
            raise _auth_error("refresh_superseded", 409)
        _revoke(session, row.id, "reuse", now)
        session.commit()
        raise _auth_error("refresh_reused")
    session.execute(
        text(
            "UPDATE auth_refresh_tokens SET rotated_at = :now WHERE token_hash = :hash"
        ),
        {"now": now, "hash": token_hash(token)},
    )
    idle = min(
        row.absolute_expires_at,
        now + timedelta(seconds=settings.auth_refresh_idle_ttl_seconds),
    )
    session.execute(
        text(
            "UPDATE auth_sessions SET last_refreshed_at = :now, idle_expires_at = :idle WHERE id = :id"
        ),
        {"now": now, "idle": idle, "id": row.id},
    )
    _cleanup(session, row.user_id, now)
    return _issue(
        session,
        settings,
        _IssueIdentity(row.id, row.user_id, idle, row.normalized_email),
        now,
        SessionProfile(),
    )


@router.post("/auth/logout", status_code=204)
def logout_session(
    session: DatabaseSession,
    payload: LogoutCredential | None = None,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
) -> Response:
    families = set()
    if payload and payload.refresh_token:
        token = payload.refresh_token.get_secret_value()
        if token.startswith("elr_"):
            family = session.execute(
                text(
                    "SELECT session_id FROM auth_refresh_tokens WHERE token_hash = :hash"
                ),
                {"hash": token_hash(token)},
            ).scalar_one_or_none()
            if family is not None:
                families.add(family)
    if credentials and credentials.credentials.startswith("ela_"):
        family = session.execute(
            text("SELECT session_id FROM auth_access_tokens WHERE token_hash = :hash"),
            {"hash": token_hash(credentials.credentials)},
        ).scalar_one_or_none()
        if family is not None:
            families.add(family)
    for family in sorted(families, key=str):
        session.execute(
            text("SELECT id FROM auth_sessions WHERE id = :id FOR UPDATE"),
            {"id": family},
        )
        _revoke(session, family, "logout", auth_clock())
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get("/me")
def get_me(user: CurrentUserDependency) -> dict[str, object]:
    return {"id": user.id, "email": user.email}
