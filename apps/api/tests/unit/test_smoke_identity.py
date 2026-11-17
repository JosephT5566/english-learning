"""Smoke identity configuration and Google verification without network calls."""

from functools import partial
from itertools import combinations
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from google.auth.exceptions import GoogleAuthError
from pydantic import ValidationError

from app import auth, config
from app.config import ConfigurationError, Settings
from app.main import create_app

SMOKE = {
    "release_smoke_audience": "https://smoke.example.invalid/release-smoke",
    "release_smoke_subject": "1234567890",
    "release_smoke_email": "release-smoke@synthetic.iam.gserviceaccount.com",
}


def claims():
    return {
        "iss": "https://accounts.google.com",
        "aud": SMOKE["release_smoke_audience"],
        "sub": SMOKE["release_smoke_subject"],
        "email": SMOKE["release_smoke_email"],
        "email_verified": True,
    }


def test_smoke_settings_default_to_disabled_and_accept_complete_identity():
    settings = Settings(_env_file=None)
    assert all(getattr(settings, name) is None for name in SMOKE)
    enabled = Settings(_env_file=None, **SMOKE)
    assert all(getattr(enabled, name) == value for name, value in SMOKE.items())


@pytest.mark.parametrize(
    "keys", [keys for count in (1, 2) for keys in combinations(SMOKE, count)]
)
def test_smoke_settings_reject_every_partial_configuration(keys):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{key: SMOKE[key] for key in keys})


@pytest.mark.parametrize(
    "audience",
    [
        "http://smoke.example.invalid/release-smoke",
        "https:///missing-host",
        "https://user:private@smoke.example.invalid/path",
        "https://smoke.example.invalid/path?private=value",
        "https://smoke.example.invalid/path#private",
        "https://smoke.example.invalid:bad/path",
        "",
    ],
)
def test_smoke_audience_requires_https_without_credentials_query_or_fragment(audience):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{**SMOKE, "release_smoke_audience": audience})


@pytest.mark.parametrize("other", ["human", "export"])
def test_smoke_audience_is_distinct_from_human_and_guest_export(other):
    values = dict(SMOKE)
    if other == "human":
        values["google_oauth_client_id"] = SMOKE["release_smoke_audience"]
    else:
        values.update(
            guest_export_deck_id="10000000-0000-4000-8000-000000000001",
            guest_export_subject="999",
            guest_export_email="export@synthetic.iam.gserviceaccount.com",
            guest_export_audience=SMOKE["release_smoke_audience"],
        )
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


@pytest.mark.parametrize(
    "values",
    [
        {"release_smoke_audience": SMOKE["release_smoke_audience"]},
        {**SMOKE, "release_smoke_subject": "private-nonnumeric-subject"},
        {**SMOKE, "release_smoke_email": "private-human@example.invalid"},
        {**SMOKE, "release_smoke_audience": "http://private.example.invalid/path"},
        {**SMOKE, "google_oauth_client_id": SMOKE["release_smoke_audience"]},
    ],
)
def test_smoke_configuration_errors_never_include_values(monkeypatch, values):
    monkeypatch.setattr(config, "Settings", partial(Settings, _env_file=None, **values))
    with pytest.raises(ConfigurationError) as captured:
        config.load_settings()
    assert all(str(value) not in str(captured.value) for value in values.values())


def test_smoke_verifier_uses_dedicated_audience_and_namespaced_subject(monkeypatch):
    verify = Mock(return_value=claims())
    monkeypatch.setattr(auth.google_id_token, "verify_oauth2_token", verify)
    identity = auth.GoogleSmokeTokenVerifier(Settings(_env_file=None, **SMOKE)).verify(
        "synthetic-smoke-id-token"
    )
    assert verify.call_args.args[2] == SMOKE["release_smoke_audience"]
    assert identity.subject == "service-account:" + SMOKE["release_smoke_subject"]
    assert identity.email == SMOKE["release_smoke_email"]
    assert identity.principal_kind == "smoke"


@pytest.mark.parametrize(
    "change",
    [
        {"iss": "https://untrusted.example.invalid"},
        {"iss": None},
        {"aud": "human-audience"},
        {"aud": "https://export.example.invalid/guest-cards"},
        {"sub": "9876543210"},
        {"email": "other@synthetic.iam.gserviceaccount.com"},
        {"email": SMOKE["release_smoke_email"].upper()},
        {"email_verified": False},
        {"email_verified": "true"},
    ],
)
def test_smoke_verifier_requires_exact_signed_claims(monkeypatch, change):
    monkeypatch.setattr(
        auth.google_id_token,
        "verify_oauth2_token",
        Mock(return_value={**claims(), **change}),
    )
    with pytest.raises(auth.ApiError) as captured:
        auth.GoogleSmokeTokenVerifier(Settings(_env_file=None, **SMOKE)).verify(
            "synthetic-smoke-id-token"
        )
    assert captured.value.status_code == 401
    assert "synthetic-smoke-id-token" not in str(captured.value)


@pytest.mark.parametrize(
    "failure,status,code",
    [
        (ValueError("private-provider-message"), 401, "invalid_authentication"),
        (
            GoogleAuthError("private-provider-message"),
            503,
            "identity_provider_unavailable",
        ),
    ],
)
def test_smoke_verifier_sanitizes_provider_failures(monkeypatch, failure, status, code):
    monkeypatch.setattr(
        auth.google_id_token, "verify_oauth2_token", Mock(side_effect=failure)
    )
    with pytest.raises(auth.ApiError) as captured:
        auth.GoogleSmokeTokenVerifier(Settings(_env_file=None, **SMOKE)).verify(
            "synthetic-smoke-id-token"
        )
    assert (captured.value.status_code, captured.value.code) == (status, code)
    assert "private-provider-message" not in str(captured.value)


def test_disabled_smoke_verifier_rejects_before_google(monkeypatch):
    verify = Mock()
    monkeypatch.setattr(auth.google_id_token, "verify_oauth2_token", verify)
    with pytest.raises(auth.ApiError):
        auth.GoogleSmokeTokenVerifier(Settings(_env_file=None)).verify(
            "synthetic-smoke-id-token"
        )
    verify.assert_not_called()


def test_smoke_id_bearer_never_reaches_verifier_or_database():
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        session = Mock()
        session.execute.side_effect = AssertionError(
            "ID-token bearer reached the database"
        )
        client.app.state.database_session_factory = Mock(return_value=session)
        client.app.state.smoke_token_verifier = Mock()
        for path in ("/v1/me", "/v1/decks"):
            response = client.get(
                path, headers={"Authorization": "Bearer synthetic-smoke-id-token"}
            )
            assert response.status_code == 401
        client.app.state.smoke_token_verifier.verify.assert_not_called()
        session.execute.assert_not_called()


@pytest.mark.parametrize(
    "allowed", ["", SMOKE["release_smoke_email"], "human@example.test"]
)
def test_service_account_cannot_exchange_through_human_audience(monkeypatch, allowed):
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        client.app.state.settings = Settings(
            _env_file=None, google_allowed_emails=allowed, **SMOKE
        )
        client.app.state.token_verifier = Mock()
        client.app.state.token_verifier.verify.return_value = (
            auth.VerifiedGoogleIdentity(
                SMOKE["release_smoke_subject"],
                SMOKE["release_smoke_email"],
            )
        )
        client.app.state.smoke_token_verifier = Mock()
        session = Mock()
        session.execute.side_effect = AssertionError("rejected exchange reached SQL")
        client.app.state.database_session_factory = Mock(return_value=session)
        response = client.post(
            "/v1/auth/session", json={"credential": "synthetic-human-audience-sa-token"}
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "account_not_allowed"
        client.app.state.smoke_token_verifier.verify.assert_not_called()
        session.execute.assert_not_called()


@pytest.mark.parametrize("status", [403, 503])
def test_smoke_fallback_never_masks_human_denial_or_provider_outage(status):
    from types import SimpleNamespace

    human = Mock()
    human.verify.side_effect = auth.ApiError(
        status_code=status, code="synthetic_failure", message="Safe error."
    )
    smoke = Mock()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                token_verifier=human,
                smoke_token_verifier=smoke,
                settings=Settings(_env_file=None, **SMOKE),
            )
        )
    )
    with pytest.raises(auth.ApiError) as captured:
        auth._verified_identity(
            request, auth.SessionCredential(credential="synthetic-credential")
        )
    assert captured.value.status_code == status
    smoke.verify.assert_not_called()


def test_human_invalid_credentials_try_independently_verified_smoke_identity():
    from types import SimpleNamespace

    human = Mock()
    human.verify.side_effect = auth._invalid_credentials()
    identity = auth.VerifiedGoogleIdentity(
        "service-account:" + SMOKE["release_smoke_subject"],
        SMOKE["release_smoke_email"],
        principal_kind="smoke",
    )
    smoke = Mock()
    smoke.verify.return_value = identity
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                token_verifier=human,
                smoke_token_verifier=smoke,
                settings=Settings(_env_file=None, **SMOKE),
            )
        )
    )
    assert (
        auth._verified_identity(
            request, auth.SessionCredential(credential="synthetic-credential")
        )
        == identity
    )
    human.verify.assert_called_once_with("synthetic-credential")
    smoke.verify.assert_called_once_with("synthetic-credential")


@pytest.mark.parametrize("changed", [False, True])
def test_smoke_session_recheck_uses_exact_identity_and_persists_revocation(changed):
    from datetime import UTC, datetime
    from types import SimpleNamespace

    values = {**SMOKE, "release_smoke_subject": "9876543210"} if changed else SMOKE
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(settings=Settings(_env_file=None, **values))
        )
    )
    row = SimpleNamespace(
        id="synthetic-session",
        principal_kind="smoke",
        google_subject="service-account:" + SMOKE["release_smoke_subject"],
        normalized_email=SMOKE["release_smoke_email"],
    )
    session = Mock()
    now = datetime(2026, 11, 17, tzinfo=UTC)
    if changed:
        with pytest.raises(auth.ApiError) as captured:
            auth._check_principal(request, session, row, now)
        assert captured.value.status_code == 401
        assert session.execute.call_count == 2
        assert session.execute.call_args_list[0].args[1]["reason"] == "operator"
        session.commit.assert_called_once()
    else:
        auth._check_principal(request, session, row, now)
        session.execute.assert_not_called()
        session.commit.assert_not_called()
