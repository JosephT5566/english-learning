"""Server count validation stays authoritative after dropping provider array limits."""

import json
import os

import pytest

from app.generation import GenerationResult
from tests.integration.test_auth_and_authorization import FIXTURE_DECK_ID, bearer
from tests.integration.test_auth_and_authorization import (
    api_client as owned_client_fixture,
)
from tests.integration.test_card_drafts import counts
from tests.integration.test_card_extraction import provider as scripted_provider_fixture

api_client = owned_client_fixture
provider = scripted_provider_fixture
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1",
        reason="PostgreSQL tests are opt-in",
    ),
]
PATH = f"/v1/decks/{FIXTURE_DECK_ID}/card-drafts/extract"


@pytest.mark.parametrize("count,status", [(0, 502), (1, 200), (20, 200), (21, 502)])
def test_extraction_count_bounds_survive_provider_schema_projection(
    api_client, provider, migrated_database_engine, count, status
):
    provider.outcome = GenerationResult(
        text=json.dumps({"cards": [{"term": "harbor", "meaning": "shelter"}] * count})
    )
    before = counts(migrated_database_engine)
    response = api_client.post(
        PATH, headers=bearer("fixture-token"), json={"material": "synthetic harbor"}
    )
    assert response.status_code == status
    if status == 502:
        assert response.json()["error"]["code"] == "extraction_invalid_output"
        assert response.json()["error"]["retryable"] is False
        assert "cards" not in response.json()
    else:
        assert len(response.json()["cards"]) == count
    assert len(provider.calls) == 1
    schema_json = json.dumps(provider.calls[0][0].response_schema)
    assert '"minItems"' not in schema_json
    assert '"maxItems"' not in schema_json
    assert counts(migrated_database_engine) == before
