"""HTTP contract tests for stable, non-disclosing API errors."""

from typing import Annotated
from uuid import UUID

from fastapi import Query
from fastapi.testclient import TestClient

from app.errors import ApiError
from app.main import create_app


def assert_request_id(response_body: dict[str, object], header_value: str) -> None:
    """Assert the response uses one valid request UUID in body and header."""

    error = response_body["error"]
    assert isinstance(error, dict)
    request_id = error["request_id"]
    assert UUID(str(request_id))
    assert header_value == request_id


def test_expected_api_error_preserves_only_explicit_public_fields() -> None:
    app = create_app()

    @app.get("/v1/conflict")
    def conflict() -> None:
        raise ApiError(
            status_code=409,
            code="stale_review_state",
            message="The review state changed; refresh and retry.",
            details={"expected_version": 4, "current_version": 5},
        )

    with TestClient(app) as client:
        response = client.get("/v1/conflict")

    assert response.status_code == 409
    body = response.json()
    assert body["error"] | {"request_id": "ignored"} == {
        "code": "stale_review_state",
        "message": "The review state changed; refresh and retry.",
        "retryable": False,
        "request_id": "ignored",
        "details": {"expected_version": 4, "current_version": 5},
    }
    assert_request_id(body, response.headers["X-Request-ID"])


def test_validation_error_does_not_echo_rejected_input() -> None:
    app = create_app()

    @app.get("/v1/items")
    def list_items(limit: Annotated[int, Query(ge=1, le=100)]) -> None:
        return None

    secret_input = "postgresql+psycopg://user:password@private-db/items"
    with TestClient(app) as client:
        response = client.get("/v1/items", params={"limit": secret_input})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_failed"
    assert body["error"]["retryable"] is False
    assert body["error"]["details"] == {
        "fields": [
            {
                "path": ["query", "limit"],
                "code": "invalid_format",
                "message": "This value has an invalid format.",
            }
        ]
    }
    assert secret_input not in response.text
    assert "password" not in response.text
    assert_request_id(body, response.headers["X-Request-ID"])


def test_unexpected_error_hides_exception_and_connection_details() -> None:
    app = create_app()

    @app.get("/v1/failure")
    def failure() -> None:
        raise RuntimeError(
            "connection failed for postgresql://admin:secret@private-db/internal"
        )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/v1/failure")

    assert response.status_code == 500
    body = response.json()
    assert body["error"] | {"request_id": "ignored"} == {
        "code": "internal_error",
        "message": "An unexpected error occurred.",
        "retryable": False,
        "request_id": "ignored",
    }
    assert "secret" not in response.text
    assert "private-db" not in response.text
    assert "RuntimeError" not in response.text
    assert_request_id(body, response.headers["X-Request-ID"])


def test_framework_404_uses_stable_error_envelope() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/v1/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "endpoint_not_found"
    assert body["error"]["retryable"] is False
    assert "details" not in body["error"]
    assert_request_id(body, response.headers["X-Request-ID"])


def test_success_responses_receive_distinct_request_ids() -> None:
    with TestClient(create_app()) as client:
        first_response = client.get("/health/live")
        second_response = client.get("/health/live")

    first_request_id = first_response.headers["X-Request-ID"]
    second_request_id = second_response.headers["X-Request-ID"]
    assert UUID(first_request_id)
    assert UUID(second_request_id)
    assert first_request_id != second_request_id
