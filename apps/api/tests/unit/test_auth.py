"""Authentication boundary tests without live Google or PostgreSQL calls."""

import pytest
from fastapi.testclient import TestClient

import app.auth as auth_module
from app.auth import GoogleTokenVerifier
from app.errors import ApiError
from app.main import create_app


def test_google_verifier_passes_configured_audience_and_normalizes_claims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def verify(token: str, request: object, audience: str) -> dict[str, object]:
        captured.update(token=token, request=request, audience=audience)
        return {
            "sub": " stable-google-sub ",
            "email": " User@Example.COM ",
            "email_verified": True,
        }

    monkeypatch.setattr(auth_module.google_id_token, "verify_oauth2_token", verify)
    verifier = GoogleTokenVerifier("expected-client-id")

    identity = verifier.verify("safe-token")

    assert captured["audience"] == "expected-client-id"
    assert captured["token"] == "safe-token"
    assert identity.subject == "stable-google-sub"
    assert identity.email == "user@example.com"


@pytest.mark.parametrize(
    "case",
    ["expired", "invalid-audience", "malformed", "invalid-signature"],
)
def test_google_verifier_rejects_invalid_standard_token_cases(
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    def reject(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise ValueError(case)

    monkeypatch.setattr(auth_module.google_id_token, "verify_oauth2_token", reject)

    with pytest.raises(ApiError) as captured:
        GoogleTokenVerifier("expected-client-id").verify(f"raw-{case}-token")

    assert captured.value.status_code == 401
    assert captured.value.code == "invalid_authentication"
    assert f"raw-{case}-token" not in str(captured.value)


@pytest.mark.parametrize(
    "claims",
    [
        {"email": "user@example.test", "email_verified": True},
        {"sub": "subject", "email_verified": True},
        {"sub": "subject", "email": "user@example.test", "email_verified": False},
    ],
)
def test_google_verifier_requires_subject_email_and_verified_email(
    monkeypatch: pytest.MonkeyPatch,
    claims: dict[str, object],
) -> None:
    monkeypatch.setattr(
        auth_module.google_id_token,
        "verify_oauth2_token",
        lambda *_args: claims,
    )

    with pytest.raises(ApiError) as captured:
        GoogleTokenVerifier("expected-client-id").verify("safe-token")

    assert captured.value.code == "invalid_authentication"


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("GET", "/v1/me", {}),
        ("GET", "/v1/decks", {}),
        ("POST", "/v1/decks", {"json": {}}),
        ("GET", "/v1/decks/10000000-0000-0000-0000-000000000001", {}),
        ("PATCH", "/v1/decks/10000000-0000-0000-0000-000000000001", {"json": {}}),
        ("DELETE", "/v1/decks/10000000-0000-0000-0000-000000000001", {}),
        ("GET", "/v1/cards", {}),
        ("POST", "/v1/cards", {"json": {}}),
        ("GET", "/v1/cards/20000000-0000-0000-0000-000000000001", {}),
        ("PATCH", "/v1/cards/20000000-0000-0000-0000-000000000001", {"json": {}}),
        ("DELETE", "/v1/cards/20000000-0000-0000-0000-000000000001", {}),
        ("GET", "/v1/reviews/due", {"params": {"target_language": "en"}}),
        ("POST", "/v1/reviews", {"json": {}}),
    ],
)
def test_protected_endpoints_reject_missing_authentication_consistently(
    method: str,
    path: str,
    kwargs: dict[str, object],
) -> None:
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        response = client.request(method, path, **kwargs)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "authentication_required"


class RejectingVerifier:
    def verify(self, _token: str) -> None:
        raise ApiError(
            status_code=401,
            code="invalid_authentication",
            message="Authentication credentials are invalid.",
        )


@pytest.mark.parametrize(
    "token", ["expired-secret", "wrong-audience-secret", "malformed-secret"]
)
def test_protected_endpoint_rejects_invalid_tokens_without_echoing_them(
    token: str,
) -> None:
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        client.app.state.token_verifier = RejectingVerifier()
        response = client.get(
            "/v1/decks",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_authentication"
    assert token not in response.text
