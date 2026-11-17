"""Header-session boundary checks without Google or a database."""

import base64
import hashlib

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import auth
from app.config import Settings
from app.main import create_app


@pytest.mark.parametrize(
    ("name", "default", "minimum", "maximum"),
    [
        ("auth_access_ttl_seconds", 900, 60, 3600),
        ("auth_refresh_idle_ttl_seconds", 604800, 300, 2592000),
        ("auth_refresh_absolute_ttl_seconds", 2592000, 300, 7776000),
        ("auth_refresh_reuse_grace_seconds", 10, 0, 60),
    ],
)
def test_auth_setting_defaults_and_bounds(name, default, minimum, maximum):
    assert getattr(Settings(_env_file=None), name) == default
    for value in (minimum, maximum):
        assert getattr(Settings(_env_file=None, **{name: value}), name) == value
    for value in (minimum - 1, maximum + 1):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **{name: value})


def test_token_format_entropy_and_hash():
    for prefix in ("ela_", "elr_"):
        tokens = {auth.new_token(prefix) for _ in range(100)}
        assert len(tokens) == 100
        for token in tokens:
            assert token.startswith(prefix)
            raw = base64.urlsafe_b64decode(token[4:] + "=")
            assert len(raw) >= 32
            assert auth.token_hash(token) == hashlib.sha256(token.encode()).digest()
            assert len(auth.token_hash(token)) == 32


@pytest.mark.parametrize("token", ["google.id.token", "elr_wrong-type", "unknown"])
def test_wrong_prefix_rejected_without_lookup_or_verifier(token, caplog, capsys):
    def forbidden():
        pytest.fail("wrong prefix must not check out a database session")

    with TestClient(create_app(), raise_server_exceptions=False) as client:
        client.app.state.database_session_factory = forbidden
        response = client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_authentication"
    assert token not in response.text
    assert token not in caplog.text + capsys.readouterr().out


@pytest.mark.parametrize(
    "path,field", [("session", "credential"), ("refresh", "refresh_token")]
)
def test_auth_errors_and_validation_never_echo_secrets(path, field, caplog, capsys):
    class Reject:
        def verify(self, _token):
            raise auth._invalid_credentials()

    secret = "synthetic-private-credential"
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        client.app.state.token_verifier = Reject()
        for value in (secret, {"private": secret}):
            response = client.post(f"/v1/auth/{path}", json={field: value})
            assert response.status_code in (401, 422)
            assert secret not in response.text
            assert response.headers["cache-control"] == "no-store"
    assert secret not in caplog.text + capsys.readouterr().out
