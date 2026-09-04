"""Fast read-API failure-boundary tests."""

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.main import create_app


class FailingSession:
    """Minimal session double that fails without leaking recognizable internals."""

    def execute(self, *_args: object, **_kwargs: object) -> None:
        raise OperationalError(
            "SELECT secret FROM private_schema",
            {},
            RuntimeError("postgresql://admin:secret@private-db/internal"),
        )

    def close(self) -> None:
        pass


def test_database_failure_is_retryable_and_does_not_expose_details() -> None:
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        client.app.state.database_session_factory = FailingSession
        response = client.get("/v1/decks")

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "database_unavailable"
    assert body["error"]["retryable"] is True
    assert "secret" not in response.text
    assert "private" not in response.text
    assert "SELECT" not in response.text
