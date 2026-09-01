import pytest
from fastapi.testclient import TestClient

import app.health as health_module
from app.main import create_app


def test_liveness_returns_ok() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    ("database_available", "expected_status_code", "expected_body"),
    [
        (
            True,
            200,
            {"status": "ready", "checks": {"database": "ok"}},
        ),
        (
            False,
            503,
            {
                "status": "not_ready",
                "checks": {"database": "unavailable"},
            },
        ),
    ],
)
def test_readiness_reports_safe_database_state(
    monkeypatch: pytest.MonkeyPatch,
    database_available: bool,
    expected_status_code: int,
    expected_body: dict[str, object],
) -> None:
    monkeypatch.setattr(
        health_module,
        "check_database_readiness",
        lambda engine: database_available,
    )

    with TestClient(create_app()) as client:
        response = client.get("/health/ready")

    assert response.status_code == expected_status_code
    assert response.json() == expected_body


def test_readiness_recovers_without_restarting_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_states = iter([False, True])
    monkeypatch.setattr(
        health_module,
        "check_database_readiness",
        lambda engine: next(database_states),
    )

    with TestClient(create_app()) as client:
        unavailable_response = client.get("/health/ready")
        recovered_response = client.get("/health/ready")

    assert unavailable_response.status_code == 503
    assert unavailable_response.json() == {
        "status": "not_ready",
        "checks": {"database": "unavailable"},
    }
    assert recovered_response.status_code == 200
    assert recovered_response.json() == {
        "status": "ready",
        "checks": {"database": "ok"},
    }
