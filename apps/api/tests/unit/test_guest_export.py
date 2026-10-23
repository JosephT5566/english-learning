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


def test_anonymous_route_retired_without_database_access():
    with TestClient(create_app()) as client:
        factory = Mock()
        client.app.state.database_session_factory = factory
        assert client.get("/v1/public/review-cards").status_code == 404
        factory.assert_not_called()


def test_google_verifier_receives_dedicated_audience(monkeypatch):
    verifier = Mock(return_value=claims())
    monkeypatch.setattr(
        "app.guest_export.google_id_token.verify_oauth2_token", verifier
    )
    with TestClient(create_app()) as client:
        client.app.state.settings = Settings(**CONFIG)
        response = client.get(
            PATH,
            params={"unsupported": "yes"},
            headers={"Authorization": "Bearer synthetic"},
        )
        assert response.status_code == 400
        assert verifier.call_args.args[0] == "synthetic"
        assert verifier.call_args.args[2] == CONFIG["guest_export_audience"]


def test_cancelled_export_keeps_permit_until_thread_cleanup(monkeypatch):
    import threading
    from datetime import UTC, datetime

    import anyio
    from fastapi import Request, Response

    from app.guest_export import GuestSnapshot, export_guest_cards

    entered = threading.Event()
    finish = threading.Event()
    app = create_app()
    app.state.guest_export_permit = threading.BoundedSemaphore(1)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": PATH,
            "query_string": b"",
            "headers": [],
            "app": app,
        }
    )

    def blocking_read(_request):
        entered.set()
        assert finish.wait(timeout=5)
        return GuestSnapshot(schema_version=1, generated_at=datetime.now(UTC), items=[])

    monkeypatch.setattr("app.guest_export._read_export", blocking_read)

    async def run():
        async def request_task(*, task_status=anyio.TASK_STATUS_IGNORED):
            with anyio.CancelScope() as scope:
                task_status.started(scope)
                await export_guest_cards(request, Response(), None)

        with anyio.fail_after(5):
            async with anyio.create_task_group() as group:
                scope = await group.start(request_task)
                try:
                    assert await anyio.to_thread.run_sync(entered.wait, 5)
                    scope.cancel()
                    await anyio.wait_all_tasks_blocked()
                    assert not app.state.guest_export_permit.acquire(blocking=False)
                finally:
                    finish.set()
            assert app.state.guest_export_permit.acquire(blocking=False)
            app.state.guest_export_permit.release()

    anyio.run(run)
