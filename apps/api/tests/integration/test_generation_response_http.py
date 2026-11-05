"""Actual adapter and endpoint with synthetic requests.Response objects; no network."""

import json
import os
from unittest.mock import Mock

import pytest
import requests
from urllib3.exceptions import DecodeError, ProtocolError

from app.writes import CardDrafts
from tests.integration.test_auth_and_authorization import FIXTURE_DECK_ID, bearer
from tests.integration.test_auth_and_authorization import (
    api_client as owned_client_fixture,
)
from tests.integration.test_card_drafts import counts

api_client = owned_client_fixture
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1",
        reason="PostgreSQL tests are opt-in",
    ),
]
PATH = f"/v1/decks/{FIXTURE_DECK_ID}/card-drafts/extract"


@pytest.fixture
def http_provider(api_client, monkeypatch):
    api_client.app.state.settings = api_client.app.state.settings.model_copy(
        update={
            "generation_model": "synthetic-v1",
            "vertex_project_id": "synthetic-project",
        }
    )
    monkeypatch.setattr(
        api_client.app.state.generation_provider,
        "_access_token",
        lambda: "synthetic-token",
    )


def test_signed_final_text_reaches_endpoint_as_valid_cards(
    api_client, http_provider, monkeypatch, migrated_database_engine
):
    card = {"term": "harbor", "meaning": "shelter"}
    response = requests.Response()
    response.status_code = 200
    response._content = json.dumps(
        {
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {
                        "parts": [
                            {"text": "PRIVATE_THOUGHT", "thought": True},
                            {
                                "text": json.dumps({"cards": [card]}),
                                "thoughtSignature": "synthetic-signature",
                            },
                        ]
                    },
                }
            ],
            "modelVersion": "synthetic-v1",
        }
    ).encode()
    post = Mock(return_value=response)
    monkeypatch.setattr(requests, "post", post)
    before = counts(migrated_database_engine)
    result = api_client.post(
        PATH, headers=bearer("fixture-token"), json={"material": "synthetic material"}
    )
    assert result.status_code == 200
    assert (
        CardDrafts.model_validate({"cards": result.json()["cards"]}).cards[0].term
        == "harbor"
    )
    assert "PRIVATE_THOUGHT" not in result.text
    assert "synthetic-signature" not in result.text
    assert post.call_count == 1
    assert counts(migrated_database_engine) == before


@pytest.mark.parametrize(
    "body_failure", ["json", "content_decoding", "chunked_encoding"]
)
def test_malformed_provider_body_is_502_nonretryable(
    api_client, http_provider, monkeypatch, body_failure, migrated_database_engine
):
    response = requests.Response()
    response.status_code = 200
    if body_failure == "json":
        response._content = b"not json PRIVATE_PROVIDER_BODY"
    else:
        response.raw = Mock()
        response.raw.stream.side_effect = (
            DecodeError if body_failure == "content_decoding" else ProtocolError
        )("PRIVATE_PROVIDER_BODY")
    post = Mock(return_value=response)
    monkeypatch.setattr(requests, "post", post)
    before = counts(migrated_database_engine)
    result = api_client.post(
        PATH, headers=bearer("fixture-token"), json={"material": "synthetic material"}
    )
    assert result.status_code == 502
    assert result.json()["error"]["code"] == "generation_invalid_response"
    assert result.json()["error"]["retryable"] is False
    assert "PRIVATE_PROVIDER_BODY" not in result.text
    assert post.call_count == 1
    assert counts(migrated_database_engine) == before
