"""Privacy and correlation tests for request completion events."""

import json
from uuid import UUID

import pytest
from fastapi import Query
from fastapi.testclient import TestClient

import app.health as health_module
from app.errors import ApiError
from app.main import create_app


def _event(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    lines = [line for line in capsys.readouterr().out.splitlines() if line]
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert isinstance(event, dict)
    return event


def test_success_event_uses_server_id_and_route_template(
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = create_app()

    @app.get("/v1/test-items/{item_id}")
    def item(item_id: str) -> dict[str, str]:
        return {"id": item_id}

    with TestClient(app) as client:
        response = client.get(
            "/v1/test-items/private-card-123?search=secret-query",
            headers={
                "X-Request-ID": "client-supplied-id",
                "Authorization": "Bearer private-token-value",
            },
        )

    event = _event(capsys)
    assert response.status_code == 200
    assert UUID(str(event["request_id"]))
    assert event["request_id"] == response.headers["X-Request-ID"]
    assert event["request_id"] != "client-supplied-id"
    assert event["route"] == "/v1/test-items/{item_id}"
    assert event["method"] == "GET"
    assert event["status_code"] == 200
    assert event["outcome"] == "success"
    assert isinstance(event["duration_ms"], int)
    assert "private-card-123" not in json.dumps(event)
    assert "secret-query" not in json.dumps(event)
    assert "private-token-value" not in json.dumps(event)


def test_failures_share_response_id_and_exclude_sensitive_values(
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = create_app()

    @app.get("/v1/test-validation")
    def validation(value: int = Query(ge=1)) -> None:
        return None

    @app.get("/v1/test-database")
    def database() -> None:
        raise ApiError(
            status_code=503,
            code="database_unavailable",
            message="The database is temporarily unavailable.",
            retryable=True,
        )

    @app.get("/v1/test-conflict")
    def conflict() -> None:
        raise ApiError(
            status_code=409,
            code="version_conflict",
            message="The resource changed.",
        )

    @app.get("/v1/test-unexpected")
    def unexpected() -> None:
        raise RuntimeError("postgresql://admin:secret@private-db/private-cards")

    with TestClient(app) as client:
        responses = [
            client.get("/v1/test-validation?value=secret-query"),
            client.get("/v1/test-database"),
            client.get("/v1/test-conflict"),
            client.get("/v1/test-unexpected"),
            client.get("/v1/cards"),
        ]

    captured = capsys.readouterr()
    events = [json.loads(line) for line in captured.out.splitlines() if line]
    assert len(events) == len(responses)
    assert [event["outcome"] for event in events] == [
        "validation",
        "database",
        "conflict",
        "unexpected",
        "authentication",
    ]
    assert [event.get("error_code") for event in events] == [
        "validation_failed",
        "database_unavailable",
        "version_conflict",
        "internal_error",
        "authentication_required",
    ]
    for response, event in zip(responses, events, strict=True):
        assert response.headers["X-Request-ID"] == event["request_id"]
        assert response.json()["error"]["request_id"] == event["request_id"]
    assert "secret-query" not in captured.out + captured.err
    assert "postgresql://" not in captured.out + captured.err
    assert "private-cards" not in captured.out + captured.err
    assert "RuntimeError" not in captured.out + captured.err


def test_unmatched_path_is_not_logged(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with TestClient(create_app()) as client:
        response = client.get("/private-token-in-path")

    event = _event(capsys)
    assert response.status_code == 404
    assert event["route"] == "unmatched"
    assert "private-token-in-path" not in json.dumps(event)


def test_readiness_failure_is_classified_as_database(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(health_module, "check_database_readiness", lambda engine: False)

    with TestClient(create_app()) as client:
        response = client.get("/health/ready")

    event = _event(capsys)
    assert response.status_code == 503
    assert event["outcome"] == "database"
    assert event["error_code"] == "database_unavailable"


def test_broken_log_sink_does_not_change_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken_print(*args: object, **kwargs: object) -> None:
        raise OSError("stdout unavailable")

    monkeypatch.setattr("builtins.print", broken_print)
    with TestClient(create_app()) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert UUID(response.headers["X-Request-ID"])
