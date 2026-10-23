"""Machine export must fail closed before touching learning data."""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app

PATH = "/v1/internal/guest-cards/export"
CONFIG = {
    "guest_export_deck_id": "e3fa16a8-698b-445f-af1f-920c6758b377",
    "guest_export_audience": "https://export.example.test/guest-cards",
    "guest_export_subject": "1234567890",
    "guest_export_email": "guest-export@project.iam.gserviceaccount.com",
}


def claims(**updates):
    return {
        "iss": "https://accounts.google.com",
        "aud": CONFIG["guest_export_audience"],
        "sub": CONFIG["guest_export_subject"],
        "email": CONFIG["guest_export_email"],
        "email_verified": True,
        **updates,
    }


def test_partial_settings_rejected():
    with pytest.raises(ValidationError):
        Settings(guest_export_audience=CONFIG["guest_export_audience"])
    with pytest.raises(ValidationError):
        Settings(**{**CONFIG, "guest_export_audience": "local-development-client-id"})
    assert Settings(**CONFIG).guest_export_deck_id is not None


@pytest.mark.parametrize(
    "updates",
    [
        {"sub": "browser-user"},
        {"email": "other@project.iam.gserviceaccount.com"},
        {"aud": "browser-client"},
        {"iss": "evil"},
        {"email_verified": False},
        {"sub": None},
        {"email": None},
    ],
)
def test_wrong_claims_cannot_checkout_database(monkeypatch, updates):
    monkeypatch.setattr(
        "app.guest_export.google_id_token.verify_oauth2_token",
        Mock(return_value=claims(**updates)),
    )
    with TestClient(create_app()) as client:
        client.app.state.settings = Settings(**CONFIG)
        factory = Mock()
        client.app.state.database_session_factory = factory
        response = client.get(PATH, headers={"Authorization": "Bearer test-token"})
        assert response.status_code == 401
        factory.assert_not_called()


def test_disabled_missing_and_expired_credentials_never_checkout(monkeypatch):
    verifier = Mock(side_effect=ValueError("sensitive rejected token"))
    monkeypatch.setattr(
        "app.guest_export.google_id_token.verify_oauth2_token", verifier
    )
    with TestClient(create_app()) as client:
        factory = Mock()
        client.app.state.database_session_factory = factory
        assert client.get(PATH).status_code == 503
        client.app.state.settings = Settings(**CONFIG)
        assert client.get(PATH).status_code == 401
        response = client.get(PATH, headers={"Authorization": "Bearer expired"})
        assert response.status_code == 401
        assert "sensitive" not in response.text
        factory.assert_not_called()


def test_filters_and_busy_fail_without_database(monkeypatch):
    monkeypatch.setattr(
        "app.guest_export.google_id_token.verify_oauth2_token",
        Mock(return_value=claims()),
    )
    with TestClient(create_app()) as client:
        client.app.state.settings = Settings(**CONFIG)
        factory = Mock()
        client.app.state.database_session_factory = factory
        headers = {"Authorization": "Bearer test-token"}
        assert (
            client.get(PATH, params={"limit": "50"}, headers=headers).status_code == 400
        )
        assert client.app.state.guest_export_permit.acquire(blocking=False)
        try:
            response = client.get(PATH, headers=headers)
            assert response.status_code == 503
        finally:
            client.app.state.guest_export_permit.release()
        factory.assert_not_called()
