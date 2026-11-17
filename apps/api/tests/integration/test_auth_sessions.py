"""Real PostgreSQL session rotation, revocation, ownership and storage contracts."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text

from app import auth
from app.auth import VerifiedGoogleIdentity, token_hash
from app.config import Settings
from app.main import create_app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1",
        reason="requires disposable PostgreSQL",
    ),
]


class Verifier:
    def verify(self, token):
        if token != "synthetic-google-credential":
            raise auth._invalid_credentials()
        return VerifiedGoogleIdentity(
            "session-owner",
            "owner@example.test",
            "Owner",
            "https://lh3.googleusercontent.com/synthetic",
        )


@pytest.fixture
def session_client(migrated_database_engine, monkeypatch):
    monkeypatch.setenv("GOOGLE_ALLOWED_EMAILS", "owner@example.test")
    clock = [datetime(2026, 11, 17, tzinfo=UTC)]
    monkeypatch.setattr(auth, "auth_clock", lambda: clock[0])
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        client.app.state.token_verifier = Verifier()
        yield client, clock, migrated_database_engine


def exchange(client):
    response = client.post(
        "/v1/auth/session", json={"credential": "synthetic-google-credential"}
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def refresh(client, token):
    return client.post("/v1/auth/refresh", json={"refresh_token": token})


def bearer(tokens):
    return {"Authorization": "Bearer " + tokens["access_token"]}


def snapshot(engine):
    with engine.connect() as connection:
        return [
            connection.execute(text(f"SELECT * FROM {table} ORDER BY 1")).all()
            for table in ("auth_sessions", "auth_refresh_tokens", "auth_access_tokens")
        ]


def test_exchange_returns_profile_and_only_hashes_are_stored(
    session_client, caplog, capsys
):
    client, clock, engine = session_client
    tokens = exchange(client)
    assert tokens["profile"] == {
        "name": "Owner",
        "picture": "https://lh3.googleusercontent.com/synthetic",
    }
    assert tokens["user"]["email"] == "owner@example.test"
    assert datetime.fromisoformat(tokens["access_expires_at"]) == clock[0] + timedelta(
        seconds=900
    )
    assert client.get("/v1/me", headers=bearer(tokens)).json() == tokens["user"]
    with engine.connect() as connection:
        for table, key in (
            ("auth_access_tokens", "access_token"),
            ("auth_refresh_tokens", "refresh_token"),
        ):
            assert connection.execute(
                text(f"SELECT token_hash FROM {table}")
            ).scalar_one() == token_hash(tokens[key])
        serialized = str(snapshot(engine))
        assert "Owner" not in serialized
        assert "googleusercontent" not in serialized
    output = caplog.text + capsys.readouterr().out
    for secret in (
        tokens["access_token"],
        tokens["refresh_token"],
        "synthetic-google-credential",
    ):
        assert secret not in serialized
        assert secret not in output


def test_refresh_rotation_and_grace_issue_nothing_change_nothing(session_client):
    client, clock, engine = session_client
    first = exchange(client)
    clock[0] += timedelta(seconds=60)
    rotated = refresh(client, first["refresh_token"])
    assert rotated.status_code == 200
    assert rotated.headers["cache-control"] == "no-store"
    second = rotated.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert second["access_token"] != first["access_token"]
    assert second["user"] == first["user"]
    # Profile is not persisted; the browser retains its separately cached profile.
    assert second["profile"] == {"name": None, "picture": None}
    before = snapshot(engine)
    clock[0] += timedelta(seconds=10)
    reused = refresh(client, first["refresh_token"])
    assert reused.status_code == 409
    assert reused.json()["error"]["code"] == "refresh_superseded"
    assert "access_token" not in reused.json()
    assert snapshot(engine) == before
    assert client.get("/v1/me", headers=bearer(second)).status_code == 200


def test_refresh_reuse_outside_grace_revokes_family_and_deletes_access(session_client):
    client, clock, engine = session_client
    first = exchange(client)
    second = refresh(client, first["refresh_token"]).json()
    clock[0] += timedelta(seconds=11)
    reused = refresh(client, first["refresh_token"])
    assert reused.status_code == 401
    assert reused.json()["error"]["code"] == "refresh_reused"
    assert first["refresh_token"] not in reused.text
    assert second["access_token"] not in reused.text
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT revoked_reason FROM auth_sessions")
            ).scalar_one()
            == "reuse"
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM auth_access_tokens")
            ).scalar_one()
            == 0
        )
    assert (
        refresh(client, second["refresh_token"]).json()["error"]["code"]
        == "refresh_invalid"
    )
    for tokens in (first, second):
        assert client.get("/v1/me", headers=bearer(tokens)).status_code == 401


def test_concurrent_refresh_rotates_exactly_once(session_client):
    client, _, engine = session_client
    tokens = exchange(client)
    start = Barrier(2)

    connections = set()

    def lock_barrier(connection, _cursor, statement, *_args):
        if "FOR UPDATE OF s" in statement:
            connections.add(id(connection.connection.driver_connection))
            start.wait(timeout=10)

    runtime_engine = client.app.state.database_engine
    event.listen(runtime_engine, "before_cursor_execute", lock_barrier)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(lambda _: refresh(client, tokens["refresh_token"]), range(2))
            )
    finally:
        event.remove(runtime_engine, "before_cursor_execute", lock_barrier)
    assert len(connections) == 2
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert [r.json()["error"]["code"] for r in responses if r.status_code == 409] == [
        "refresh_superseded"
    ]
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM auth_refresh_tokens")
            ).scalar_one()
            == 2
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM auth_refresh_tokens WHERE rotated_at IS NULL"
                )
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM auth_access_tokens")
            ).scalar_one()
            == 2
        )
        assert (
            connection.execute(
                text("SELECT revoked_at FROM auth_sessions")
            ).scalar_one()
            is None
        )


@pytest.mark.parametrize("kind", ["idle", "absolute"])
def test_refresh_idle_and_absolute_expiry(session_client, kind):
    client, clock, _ = session_client
    client.app.state.settings = Settings(
        _env_file=None,
        google_allowed_emails="owner@example.test",
        auth_refresh_idle_ttl_seconds=300,
        auth_refresh_absolute_ttl_seconds=600,
    )
    tokens = exchange(client)
    if kind == "absolute":
        clock[0] += timedelta(seconds=299)
        tokens = refresh(client, tokens["refresh_token"]).json()
        clock[0] += timedelta(seconds=299)
        tokens = refresh(client, tokens["refresh_token"]).json()
        assert datetime.fromisoformat(tokens["refresh_expires_at"]) == datetime(
            2026, 11, 17, tzinfo=UTC
        ) + timedelta(seconds=600)
        clock[0] += timedelta(seconds=2)
    else:
        clock[0] += timedelta(seconds=300)
    assert (
        refresh(client, tokens["refresh_token"]).json()["error"]["code"]
        == "refresh_invalid"
    )
    assert client.get("/v1/me", headers=bearer(tokens)).status_code == 401


@pytest.mark.parametrize("method", ["refresh", "access", "both"])
def test_logout_is_idempotent_and_invalidates_session(session_client, method):
    client, _, _ = session_client
    tokens = exchange(client)
    kwargs = {}
    if method in ("refresh", "both"):
        kwargs["json"] = {"refresh_token": tokens["refresh_token"]}
    if method in ("access", "both"):
        kwargs["headers"] = bearer(tokens)
    assert client.post("/v1/auth/logout", **kwargs).status_code == 204
    assert client.post("/v1/auth/logout", **kwargs).status_code == 204
    assert (
        refresh(client, tokens["refresh_token"]).json()["error"]["code"]
        == "refresh_invalid"
    )
    assert client.get("/v1/me", headers=bearer(tokens)).status_code == 401
    assert client.post("/v1/auth/logout").status_code == 204


@pytest.mark.parametrize("first_request", ["access", "refresh"])
def test_allowlist_removal_revokes_and_is_authoritative(session_client, first_request):
    client, _, engine = session_client
    tokens = exchange(client)
    client.app.state.settings = Settings(
        _env_file=None, google_allowed_emails="someone-else@example.test"
    )
    response = (
        client.get("/v1/me", headers=bearer(tokens))
        if first_request == "access"
        else refresh(client, tokens["refresh_token"])
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "account_not_allowed"
    assert refresh(client, tokens["refresh_token"]).status_code == 403
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT revoked_reason FROM auth_sessions")
            ).scalar_one()
            == "allowlist"
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM auth_access_tokens")
            ).scalar_one()
            == 0
        )


def test_disallowed_exchange_creates_no_user_or_session(session_client):
    client, _, engine = session_client
    client.app.state.settings = Settings(
        _env_file=None, google_allowed_emails="someone-else@example.test"
    )
    denied = client.post(
        "/v1/auth/session", json={"credential": "synthetic-google-credential"}
    )
    assert denied.status_code == 403
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM users")).scalar_one() == 0
    assert snapshot(engine) == [[], [], []]


def test_google_bearer_rejected_and_expired_access_has_distinct_code(session_client):
    client, clock, _ = session_client
    tokens = exchange(client)
    for path in ("/v1/me", "/v1/decks"):
        response = client.get(
            path, headers={"Authorization": "Bearer synthetic-google-credential"}
        )
        assert response.status_code == 401
    clock[0] += timedelta(seconds=900)
    expired = client.get("/v1/me", headers=bearer(tokens))
    assert expired.status_code == 401
    assert expired.json()["error"]["code"] == "access_token_expired"
    second = refresh(client, tokens["refresh_token"])
    assert second.status_code == 200
    assert client.get("/v1/me", headers=bearer(second.json())).status_code == 200


def test_exchange_cleanup_is_user_scoped(session_client):
    client, clock, engine = session_client
    first = exchange(client)
    clock[0] += timedelta(days=8)

    class OtherVerifier(Verifier):
        def verify(self, token):
            if token == "other-credential":
                return VerifiedGoogleIdentity(
                    "other-session-owner", "other@example.test"
                )
            return super().verify(token)

    client.app.state.token_verifier = OtherVerifier()
    client.app.state.settings = Settings(
        _env_file=None, google_allowed_emails="owner@example.test,other@example.test"
    )
    other = client.post("/v1/auth/session", json={"credential": "other-credential"})
    assert other.status_code == 200
    with engine.connect() as connection:
        # Exchanging the other user must leave the first user's expired rows alone.
        assert (
            connection.execute(text("SELECT count(*) FROM auth_sessions")).scalar_one()
            == 2
        )
    exchange(client)
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT count(*) FROM auth_sessions")).scalar_one()
            == 2
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM auth_refresh_tokens WHERE token_hash = :hash"
                ),
                {"hash": token_hash(first["refresh_token"])},
            ).scalar_one()
            == 0
        )
    assert client.get("/v1/me", headers=bearer(other.json())).status_code == 200


def test_unknown_refresh_and_failed_exchange_leave_no_tokens(session_client):
    client, _, engine = session_client
    before = snapshot(engine)
    for credential in ("expired", "bad-audience", "bad-signature", "unverified"):
        denied = client.post("/v1/auth/session", json={"credential": credential})
        assert denied.status_code == 401
        assert credential not in denied.text
    unknown = refresh(client, "elr_unknown-synthetic-token")
    assert unknown.status_code == 401
    assert unknown.json()["error"]["code"] == "refresh_invalid"
    assert snapshot(engine) == before


def test_hash_length_and_single_current_refresh_are_database_constraints(
    session_client,
):
    from sqlalchemy.exc import IntegrityError

    client, clock, engine = session_client
    tokens = exchange(client)
    with engine.connect() as connection:
        family = connection.execute(text("SELECT id FROM auth_sessions")).scalar_one()
    for digest, expected in (
        (b"short", "ck_auth_refresh_hash"),
        (b"x" * 32, "uq_auth_refresh_current"),
    ):
        with pytest.raises(IntegrityError) as captured, engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO auth_refresh_tokens (token_hash, session_id, issued_at) VALUES (:hash, :family, :now)"
                ),
                {"hash": digest, "family": family, "now": clock[0]},
            )
        assert captured.value.orig.diag.constraint_name == expected
    assert refresh(client, tokens["refresh_token"]).status_code == 200
