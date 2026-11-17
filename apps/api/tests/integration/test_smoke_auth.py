"""Smoke and human sessions through real PostgreSQL/RLS, with fake Google claims."""

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import auth
from app.auth import GoogleSmokeTokenVerifier, GoogleTokenVerifier
from app.config import Settings
from app.main import create_app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1",
        reason="requires disposable PostgreSQL",
    ),
]

SMOKE = {
    "release_smoke_audience": "https://smoke.example.invalid/release-smoke",
    "release_smoke_subject": "1234567890",
    "release_smoke_email": "release-smoke@synthetic.iam.gserviceaccount.com",
}
HUMAN_AUDIENCE = "synthetic-human-client-id"
EXPORT_AUDIENCE = "https://export.example.invalid/guest-cards"


def smoke_claims(**changes):
    return {
        "iss": "https://accounts.google.com",
        "aud": SMOKE["release_smoke_audience"],
        "sub": SMOKE["release_smoke_subject"],
        "email": SMOKE["release_smoke_email"],
        "email_verified": True,
        **changes,
    }


class FakeGoogleClaims:
    def __init__(self):
        self.tokens = {
            "smoke-id-token": smoke_claims(),
            "human-id-token": {
                "iss": "https://accounts.google.com",
                "aud": HUMAN_AUDIENCE,
                "sub": "human-subject",
                "email": "human@example.test",
                "email_verified": True,
            },
        }

    def verify(self, token, audience):
        claims = self.tokens.get(token)
        if claims is None or claims["aud"] != audience:
            raise auth._invalid_credentials()
        return claims


class HumanVerifier(GoogleTokenVerifier):
    def __init__(self, source, audience):
        super().__init__(audience)
        self.source = source

    def _claims(self, token):
        return self.source.verify(token, self._audience)


class SmokeVerifier(GoogleSmokeTokenVerifier):
    def __init__(self, source, settings):
        super().__init__(settings)
        self.source = source

    def _claims(self, token):
        return self.source.verify(token, self._audience)


@pytest.fixture
def smoke_client(migrated_database_engine):
    source = FakeGoogleClaims()
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        settings = Settings(
            _env_file=None,
            google_oauth_client_id=HUMAN_AUDIENCE,
            google_allowed_emails="human@example.test",
            **SMOKE,
        )
        client.app.state.settings = settings
        client.app.state.token_verifier = HumanVerifier(source, HUMAN_AUDIENCE)
        client.app.state.smoke_token_verifier = SmokeVerifier(source, settings)
        yield client, source, migrated_database_engine


def exchange(client, credential="smoke-id-token"):
    response = client.post("/v1/auth/session", json={"credential": credential})
    assert response.status_code == 200
    return response.json()


def bearer(tokens):
    return {"Authorization": "Bearer " + tokens["access_token"]}


def create_deck(client, tokens, title):
    response = client.post(
        "/v1/decks",
        headers={**bearer(tokens), "Idempotency-Key": str(uuid4())},
        json={"title": title, "target_language": "en", "explanation_language": "zh-TW"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_smoke_exchange_refresh_owned_writes_and_no_genai_consent(
    smoke_client, caplog, capsys
):
    client, _, engine = smoke_client
    first = exchange(client)
    assert first["user"]["email"] == SMOKE["release_smoke_email"]
    assert client.get("/v1/me", headers=bearer(first)).json() == first["user"]
    deck = create_deck(client, first, "Synthetic smoke deck")
    assert client.get(f"/v1/decks/{deck}", headers=bearer(first)).status_code == 200
    # Human allowlist changes do not disable the independent smoke principal.
    client.app.state.settings = client.app.state.settings.model_copy(
        update={"google_allowed_emails": "unrelated@example.test"}
    )
    rotated = client.post(
        "/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
    )
    assert rotated.status_code == 200
    second = rotated.json()
    assert second["user"] == first["user"]
    assert second["refresh_token"] != first["refresh_token"]
    assert client.get("/v1/me", headers=bearer(second)).json() == first["user"]
    assert client.get(f"/v1/decks/{deck}", headers=bearer(second)).status_code == 200
    assert client.get("/v1/me/genai-consent", headers=bearer(second)).json() == {
        "genai_consent_at": None
    }
    denied = client.post(
        "/v1/assistant/messages",
        headers=bearer(second),
        json={"messages": [{"role": "user", "content": "Synthetic prompt"}]},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "genai_consent_required"
    with engine.connect() as connection:
        user = connection.execute(
            text(
                "SELECT google_subject, normalized_email, genai_consent_at FROM users WHERE id = :id"
            ),
            {"id": first["user"]["id"]},
        ).one()
        assert tuple(user) == (
            "service-account:" + SMOKE["release_smoke_subject"],
            SMOKE["release_smoke_email"],
            None,
        )
        assert (
            connection.execute(
                text("SELECT principal_kind FROM auth_sessions WHERE user_id = :id"),
                {"id": first["user"]["id"]},
            ).scalar_one()
            == "smoke"
        )
    output = caplog.text + capsys.readouterr().out
    assert all(
        secret not in output
        for secret in (
            "smoke-id-token",
            first["access_token"],
            first["refresh_token"],
            second["access_token"],
            second["refresh_token"],
        )
    )


def test_smoke_and_human_cannot_read_each_others_owned_data(smoke_client):
    client, _, _ = smoke_client
    smoke = exchange(client)
    human = exchange(client, "human-id-token")
    assert smoke["user"]["id"] != human["user"]["id"]
    smoke_deck = create_deck(client, smoke, "Synthetic smoke deck")
    human_deck = create_deck(client, human, "Synthetic human deck")
    for tokens, owned, foreign in (
        (smoke, smoke_deck, human_deck),
        (human, human_deck, smoke_deck),
    ):
        assert (
            client.get(f"/v1/decks/{owned}", headers=bearer(tokens)).status_code == 200
        )
        assert (
            client.get(f"/v1/decks/{foreign}", headers=bearer(tokens)).status_code
            == 404
        )
        listed = client.get("/v1/decks?target_language=en", headers=bearer(tokens))
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()["items"]] == [owned]


@pytest.mark.parametrize(
    "changes,status",
    [
        ({"aud": HUMAN_AUDIENCE}, 403),
        ({"aud": EXPORT_AUDIENCE}, 401),
        ({"sub": "9876543210"}, 401),
        ({"email": "other@synthetic.iam.gserviceaccount.com"}, 401),
        ({"email_verified": False}, 401),
        ({"iss": "https://untrusted.example.invalid"}, 401),
    ],
)
def test_smoke_exchange_rejection_matrix_creates_no_user_or_session(
    smoke_client, changes, status
):
    client, source, engine = smoke_client
    source.tokens["rejected-smoke-id-token"] = smoke_claims(**changes)
    denied = client.post(
        "/v1/auth/session", json={"credential": "rejected-smoke-id-token"}
    )
    assert denied.status_code == status
    assert "rejected-smoke-id-token" not in denied.text
    with engine.connect() as connection:
        for table in (
            "users",
            "auth_sessions",
            "auth_refresh_tokens",
            "auth_access_tokens",
        ):
            assert (
                connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
                == 0
            )


def test_smoke_exchange_disabled_rejects_and_human_sign_in_still_works(smoke_client):
    client, _, engine = smoke_client
    client.app.state.settings = Settings(
        _env_file=None,
        google_oauth_client_id=HUMAN_AUDIENCE,
        google_allowed_emails="human@example.test",
    )
    denied = client.post("/v1/auth/session", json={"credential": "smoke-id-token"})
    assert denied.status_code == 401
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM users")).scalar_one() == 0
    human = exchange(client, "human-id-token")
    assert client.get("/v1/me", headers=bearer(human)).status_code == 200


@pytest.mark.parametrize("first_request", ["access", "refresh"])
@pytest.mark.parametrize("change", ["unset", "subject", "email"])
def test_smoke_settings_removed_or_identity_changed_revokes_session(
    smoke_client, change, first_request
):
    client, _, engine = smoke_client
    tokens = exchange(client)
    values = dict(SMOKE)
    if change == "unset":
        values = {}
    elif change == "subject":
        values["release_smoke_subject"] = "9876543210"
    else:
        values["release_smoke_email"] = "replacement@synthetic.iam.gserviceaccount.com"
    client.app.state.settings = Settings(
        _env_file=None,
        google_oauth_client_id=HUMAN_AUDIENCE,
        google_allowed_emails="human@example.test",
        **values,
    )

    def refresh():
        return client.post(
            "/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )

    first = (
        client.get("/v1/me", headers=bearer(tokens))
        if first_request == "access"
        else refresh()
    )
    assert first.status_code == 401
    assert client.get("/v1/me", headers=bearer(tokens)).status_code == 401
    assert refresh().json()["error"]["code"] == "refresh_invalid"
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT revoked_reason FROM auth_sessions")
            ).scalar_one()
            == "operator"
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM auth_access_tokens")
            ).scalar_one()
            == 0
        )
    # Restoring configuration cannot revive a revoked family.
    client.app.state.settings = Settings(_env_file=None, **SMOKE)
    assert refresh().status_code == 401


def test_smoke_google_id_bearer_is_rejected_on_owner_endpoints(smoke_client):
    client, _, _ = smoke_client
    exchange(client)
    for path in ("/v1/me", "/v1/decks"):
        denied = client.get(path, headers={"Authorization": "Bearer smoke-id-token"})
        assert denied.status_code == 401
