import threading
from unittest.mock import Mock

import anyio
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from starlette.requests import Request

from app.config import Settings
from app.main import create_app
from app.public_admission import PublicAdmission, PublicPermit
from app.public_reviews import PUBLIC_REVIEW_PATH, PublicReviewCards, public_batch


def test_rejections_precede_database_and_auth_and_ignore_forged_headers() -> None:
    with TestClient(create_app()) as client:
        client.app.state.settings = Settings(public_review_burst=1)
        client.app.state.public_admission = PublicAdmission(client.app.state.settings)
        client.app.state.database_session_factory = Mock(
            side_effect=OperationalError("safe", {}, None)
        )
        client.app.state.token_verifier = Mock()
        first = client.get(PUBLIC_REVIEW_PATH, headers={"X-Forwarded-For": "192.0.2.1"})
        assert first.status_code == 503
        second = client.get(
            PUBLIC_REVIEW_PATH, headers={"X-Forwarded-For": "192.0.2.2"}
        )
        assert second.status_code == 429
        assert second.json()["error"]["code"] == "rate_limited"
        assert second.headers["Retry-After"] == "10"
        assert client.app.state.database_session_factory.call_count == 1
        client.app.state.token_verifier.verify.assert_not_called()
        for response in [first, second]:
            assert response.headers["Cache-Control"] == "no-store"
        assert client.app.state.public_admission._in_flight == 0


def test_query_keys_and_methods_never_open_database_and_errors_are_uncacheable() -> (
    None
):
    with TestClient(create_app()) as client:
        factory = Mock()
        client.app.state.database_session_factory = factory
        for key in ["deck_id", "limit", "cursor", "seed", "sort", "unknown"]:
            response = client.get(PUBLIC_REVIEW_PATH, params={key: "bad"})
            assert response.status_code == 400
            assert response.headers["Cache-Control"] == "no-store"
        for method in ["post", "head", "put", "delete"]:
            response = getattr(client, method)(PUBLIC_REVIEW_PATH)
            assert response.status_code == 405
            assert response.headers["Cache-Control"] == "no-store"
        preflight = client.options(
            PUBLIC_REVIEW_PATH,
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert preflight.status_code == 200
        assert preflight.headers["Cache-Control"] == "no-store"
        assert not client.app.state.public_admission._sources
        factory.assert_not_called()


def test_read_only_first_statement_cleanup_and_cors() -> None:
    with TestClient(create_app()) as client:
        session = Mock()
        session.execute.return_value.mappings.return_value = []
        client.app.state.database_session_factory = Mock(return_value=session)
        response = client.get(
            PUBLIC_REVIEW_PATH, headers={"Origin": "http://localhost:5173"}
        )
        assert response.status_code == 200
        assert response.json() == {"items": []}
        statements = [str(call.args[0]) for call in session.execute.call_args_list]
        assert statements[0] == "SET TRANSACTION READ ONLY"
        assert "set_config('statement_timeout'" in statements[1]
        assert "LIMIT 10" in statements[2]
        session.commit.assert_called_once()
        session.close.assert_called_once()
        assert client.app.state.public_admission._in_flight == 0
        assert "Retry-After" in response.headers["Access-Control-Expose-Headers"]
        assert response.headers.get("Access-Control-Allow-Credentials") is None


def test_failed_query_rolls_back_closes_and_releases_permit() -> None:
    with TestClient(create_app()) as client:
        session = Mock()
        session.execute.side_effect = OperationalError("safe", {}, None)
        client.app.state.database_session_factory = Mock(return_value=session)
        response = client.get(PUBLIC_REVIEW_PATH)
        assert response.status_code == 503
        session.rollback.assert_called_once()
        session.close.assert_called_once()
        assert client.app.state.public_admission._in_flight == 0


def test_cancellation_does_not_release_until_sync_operation_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = threading.Event()
    finish = threading.Event()
    settings = Settings()
    admission = PublicAdmission(settings)
    app = create_app()
    app.state.settings = settings
    app.state.public_admission = admission
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": PUBLIC_REVIEW_PATH,
            "query_string": b"",
            "headers": [],
            "client": ("192.0.2.1", 1),
            "app": app,
        }
    )

    def blocking_read(_request: Request) -> PublicReviewCards:
        entered.set()
        assert finish.wait(timeout=5)
        return PublicReviewCards(items=[])

    monkeypatch.setattr("app.public_reviews._read_batch", blocking_read)

    async def run() -> None:
        async with anyio.create_task_group() as group:
            group.start_soon(public_batch, request)
            await anyio.to_thread.run_sync(entered.wait)
            group.cancel_scope.cancel()
            assert admission._in_flight == 1
            assert not isinstance(admission.try_acquire("other"), PublicPermit)
            finish.set()
        assert admission._in_flight == 0

    anyio.run(run)


def test_busy_and_unexpected_errors_have_safe_headers() -> None:
    with TestClient(create_app()) as client:
        admission = client.app.state.public_admission
        permit = admission.try_acquire("held")
        assert isinstance(permit, PublicPermit)
        factory = Mock(side_effect=RuntimeError("never disclose"))
        client.app.state.database_session_factory = factory
        response = client.get(PUBLIC_REVIEW_PATH)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "public_review_busy"
        assert response.json()["error"]["retryable"] is True
        assert response.headers["Retry-After"] == "1"
        assert response.headers["Cache-Control"] == "no-store"
        factory.assert_not_called()
        permit.release()
        failed = client.get(PUBLIC_REVIEW_PATH)
        assert failed.status_code == 500
        assert "never disclose" not in failed.text
        assert failed.headers["Cache-Control"] == "no-store"
        assert admission._in_flight == 0


def test_default_http_allowance_two_batches_then_countdown_and_refill() -> None:
    now = [0.0]
    with TestClient(create_app()) as client:
        client.app.state.public_admission = PublicAdmission(
            Settings(), clock=lambda: now[0]
        )
        session = Mock()
        session.execute.return_value.mappings.return_value = []
        factory = Mock(return_value=session)
        client.app.state.database_session_factory = factory
        assert client.get(PUBLIC_REVIEW_PATH).status_code == 200
        assert client.get(PUBLIC_REVIEW_PATH).status_code == 200
        rejected = client.get(PUBLIC_REVIEW_PATH)
        assert rejected.status_code == 429
        assert rejected.headers["Retry-After"] == "10"
        assert factory.call_count == 2
        now[0] = 10
        assert client.get(PUBLIC_REVIEW_PATH).status_code == 200
        assert factory.call_count == 3
