from fastapi.testclient import TestClient

from app.main import create_app

LOCAL_ORIGIN = "http://localhost:5173"


def preflight_headers(origin: str, method: str, headers: str) -> dict[str, str]:
    return {
        "Origin": origin,
        "Access-Control-Request-Method": method,
        "Access-Control-Request-Headers": headers,
    }


def test_due_review_preflight_allows_configured_frontend_origin() -> None:
    with TestClient(create_app()) as client:
        response = client.options(
            "/v1/reviews/due?target_language=en&limit=10",
            headers=preflight_headers(LOCAL_ORIGIN, "GET", "authorization"),
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == LOCAL_ORIGIN
    assert "GET" in response.headers["access-control-allow-methods"]
    assert "authorization" in response.headers["access-control-allow-headers"].lower()
    assert response.headers["access-control-max-age"] == "600"


def test_review_submission_preflight_allows_protocol_headers() -> None:
    with TestClient(create_app()) as client:
        response = client.options(
            "/v1/reviews",
            headers=preflight_headers(
                LOCAL_ORIGIN,
                "POST",
                "authorization, content-type, idempotency-key",
            ),
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == LOCAL_ORIGIN
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed_headers
    assert "content-type" in allowed_headers
    assert "idempotency-key" in allowed_headers


def test_management_mutation_preflights_allow_patch_and_delete() -> None:
    with TestClient(create_app()) as client:
        patch = client.options(
            "/v1/cards/20000000-0000-0000-0000-000000000001",
            headers=preflight_headers(
                LOCAL_ORIGIN,
                "PATCH",
                "authorization, content-type",
            ),
        )
        delete = client.options(
            "/v1/cards/20000000-0000-0000-0000-000000000001",
            headers=preflight_headers(LOCAL_ORIGIN, "DELETE", "authorization"),
        )

    assert patch.status_code == delete.status_code == 200
    allowed_methods = patch.headers["access-control-allow-methods"]
    assert "PATCH" in allowed_methods
    assert "DELETE" in allowed_methods


def test_preflight_rejects_unconfigured_origin() -> None:
    with TestClient(create_app()) as client:
        response = client.options(
            "/v1/reviews/due?target_language=en&limit=10",
            headers=preflight_headers(
                "https://untrusted.example",
                "GET",
                "authorization",
            ),
        )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_preflight_rejects_unapproved_method_and_header() -> None:
    with TestClient(create_app()) as client:
        response = client.options(
            "/v1/reviews",
            headers=preflight_headers(LOCAL_ORIGIN, "PUT", "x-unsafe-header"),
        )

    assert response.status_code == 400


def test_actual_error_response_exposes_request_id_to_allowed_origin() -> None:
    with TestClient(create_app()) as client:
        response = client.get(
            "/v1/reviews/due?target_language=en&limit=10",
            headers={"Origin": LOCAL_ORIGIN},
        )

    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == LOCAL_ORIGIN
    assert response.headers["access-control-expose-headers"] == "X-Request-ID"
    assert response.headers["X-Request-ID"]
