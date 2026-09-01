import os

import pytest
from fastapi.testclient import TestClient

from app.config import DEFAULT_DATABASE_URL
from app.main import create_app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1",
        reason="set RUN_POSTGRES_INTEGRATION_TESTS=1 to run PostgreSQL integration tests",
    ),
]


def configure_database(monkeypatch: pytest.MonkeyPatch, database_url: str) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("DATABASE_CONNECT_TIMEOUT_SECONDS", "1")


def test_readiness_returns_ready_with_postgres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_database(monkeypatch, DEFAULT_DATABASE_URL)

    with TestClient(create_app()) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ok"},
    }


def test_readiness_returns_safe_response_when_postgres_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unavailable_url = (
        "postgresql+psycopg://"
        "english_learning:english_learning@127.0.0.1:1/english_learning"
    )
    configure_database(monkeypatch, unavailable_url)

    with TestClient(create_app()) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": "unavailable"},
    }
    assert "127.0.0.1" not in response.text
    assert "english_learning" not in response.text
