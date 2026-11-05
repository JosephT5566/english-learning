"""Fake provider HTTP checks for location selection and private diagnostics."""

import json
import os
from unittest.mock import Mock

import pytest
import requests

from tests.integration.test_auth_and_authorization import FIXTURE_DECK_ID, bearer
from tests.integration.test_auth_and_authorization import (
    api_client as owned_client_fixture,
)
from tests.unit.test_generation import sample

api_client = owned_client_fixture
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1",
        reason="PostgreSQL tests are opt-in",
    ),
]
PATH = f"/v1/decks/{FIXTURE_DECK_ID}/card-drafts/extract"


@pytest.mark.parametrize(
    "location,expected_host",
    [
        (None, "asia-northeast1-aiplatform.googleapis.com"),
        ("global", "aiplatform.googleapis.com"),
        ("europe-west4", "europe-west4-aiplatform.googleapis.com"),
    ],
)
def test_endpoint_uses_generation_location_independently(
    api_client, monkeypatch, location, expected_host
):
    api_client.app.state.settings = api_client.app.state.settings.model_copy(
        update={
            "generation_model": "synthetic-model",
            "vertex_project_id": "synthetic-project",
            "vertex_location": "asia-northeast1",
            "generation_location": location,
        }
    )
    monkeypatch.setattr(
        api_client.app.state.generation_provider,
        "_access_token",
        lambda: "synthetic-token",
    )
    response = requests.Response()
    response.status_code = 200
    response._content = json.dumps(sample()).encode()
    post = Mock(return_value=response)
    monkeypatch.setattr(requests, "post", post)
    result = api_client.post(
        PATH, headers=bearer("fixture-token"), json={"material": "harbor"}
    )
    assert result.status_code == 200
    effective = location or "asia-northeast1"
    assert (
        post.call_args.args[0]
        == f"https://{expected_host}/v1/projects/synthetic-project/locations/{effective}/publishers/google/models/synthetic-model:generateContent"
    )
    assert api_client.app.state.settings.vertex_location == "asia-northeast1"


@pytest.mark.parametrize("status", [400, 404])
def test_http_status_is_logged_but_not_exposed_to_client(
    api_client, monkeypatch, capsys, status
):
    api_client.app.state.settings = api_client.app.state.settings.model_copy(
        update={
            "generation_model": "synthetic-model",
            "vertex_project_id": "synthetic-project",
            "generation_location": "global",
        }
    )
    monkeypatch.setattr(
        api_client.app.state.generation_provider,
        "_access_token",
        lambda: "synthetic-token",
    )
    response = requests.Response()
    response.status_code = status
    response._content = b"PRIVATE_BODY"
    post = Mock(return_value=response)
    monkeypatch.setattr(requests, "post", post)
    capsys.readouterr()
    result = api_client.post(
        PATH, headers=bearer("fixture-token"), json={"material": "PRIVATE_MATERIAL"}
    )
    assert result.status_code == 502
    error = result.json()["error"]
    assert error["code"] == "generation_invalid_response"
    assert error["retryable"] is False
    assert set(error) == {"code", "message", "retryable", "request_id"}
    output = capsys.readouterr().out
    events = [json.loads(line) for line in output.splitlines() if line.startswith("{")]
    logs = [
        event for event in events if event.get("event") == "card_extraction_completed"
    ]
    assert len(logs) == 1
    assert logs[0]["http_status"] == status
    assert logs[0]["result_code"] == "generation_invalid_response"
    assert "PRIVATE" not in output
    assert "PRIVATE" not in result.text
    assert post.call_count == 1
