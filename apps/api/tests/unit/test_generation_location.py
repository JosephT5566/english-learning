"""Synthetic generation-location contracts; global routing is not live-verified."""

from unittest.mock import Mock

import pytest
import requests
from pydantic import ValidationError

from app import generation
from app.config import Settings
from app.embeddings import VertexEmbeddingProvider
from app.generation import GenerationFailure, GenerationResult, VertexGenerationProvider
from app.semantic_text import DIMENSIONS
from tests.unit.test_embedding_provider import FakeResponse
from tests.unit.test_extraction_evaluation import evaluator
from tests.unit.test_generation import request, sample


@pytest.mark.parametrize("region", ["us-central1", "asia-northeast1"])
def test_unset_generation_location_falls_back_to_embedding_region(region):
    settings = Settings(_env_file=None, vertex_location=region)
    assert settings.generation_location is None
    assert settings.effective_generation_location == region


@pytest.mark.parametrize("location", ["global", "europe-west4"])
def test_generation_location_environment_is_independent(monkeypatch, location):
    monkeypatch.setenv("GENERATION_LOCATION", location)
    settings = Settings(_env_file=None, vertex_location="us-central1")
    assert settings.generation_location == location
    assert settings.effective_generation_location == location
    assert settings.vertex_location == "us-central1"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "GLOBAL",
        "global/other",
        "https://example.invalid",
        "us-central",
        "global?token=PRIVATE",
        " global ",
    ],
)
def test_generation_location_rejects_invalid_values(value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, generation_location=value)


def test_embedding_location_still_rejects_global():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, vertex_location="global")


@pytest.mark.parametrize(
    "location,host",
    [
        ("global", "aiplatform.googleapis.com"),
        ("asia-northeast1", "asia-northeast1-aiplatform.googleapis.com"),
    ],
)
def test_generation_url_uses_selected_location(location, host):
    assert (
        generation.build_generation_url(
            project="synthetic-project", location=location, model="synthetic-model"
        )
        == f"https://{host}/v1/projects/synthetic-project/locations/{location}/publishers/google/models/synthetic-model:generateContent"
    )


def test_provider_uses_global_url_without_changing_request_contract(monkeypatch):
    response = requests.Response()
    response.status_code = 200
    import json

    response._content = json.dumps(sample()).encode()
    post = Mock(return_value=response)
    monkeypatch.setattr(requests, "post", post)
    provider = VertexGenerationProvider()
    monkeypatch.setattr(provider, "_access_token", lambda: "synthetic-token")
    try:
        result = provider.generate(
            request(),
            model="synthetic-model",
            project="synthetic-project",
            location="global",
            timeout_seconds=13,
            max_output_tokens=99,
        )
        assert result.model == "synthetic-v1"
        assert (
            post.call_args.args[0]
            == "https://aiplatform.googleapis.com/v1/projects/synthetic-project/locations/global/publishers/google/models/synthetic-model:generateContent"
        )
        assert post.call_args.kwargs["timeout"] == 13
    finally:
        provider.close()


def test_embedding_keeps_regional_url_with_generation_global(monkeypatch):
    settings = Settings(
        _env_file=None, generation_location="global", vertex_location="us-central1"
    )
    post = Mock(return_value=FakeResponse([1.0] * DIMENSIONS))
    monkeypatch.setattr(requests, "post", post)
    provider = VertexEmbeddingProvider()
    monkeypatch.setattr(provider, "_access_token", lambda: "synthetic-token")
    try:
        provider.query_embedding(
            "synthetic", project="synthetic-project", location=settings.vertex_location
        )
        assert (
            post.call_args.args[0]
            == "https://us-central1-aiplatform.googleapis.com/v1/projects/synthetic-project/locations/us-central1/publishers/google/models/gemini-embedding-001:predict"
        )
    finally:
        provider.close()


@pytest.mark.parametrize(
    "status,code",
    [
        (400, "invalid_response"),
        (404, "invalid_response"),
        (401, "provider_auth_error"),
        (429, "provider_rate_limited"),
        (503, "provider_unavailable"),
    ],
)
def test_http_failure_preserves_code_with_safe_status(monkeypatch, status, code):
    response = requests.Response()
    response.status_code = status
    response._content = b"PRIVATE_PROVIDER_BODY"
    post = Mock(return_value=response)
    monkeypatch.setattr(requests, "post", post)
    provider = VertexGenerationProvider()
    monkeypatch.setattr(provider, "_access_token", lambda: "synthetic-token")
    try:
        with pytest.raises(GenerationFailure) as captured:
            provider.generate(
                request(),
                model="synthetic-model",
                project="synthetic-project",
                location="global",
                timeout_seconds=30,
                max_output_tokens=100,
            )
        assert captured.value.code == code
        assert captured.value.http_status == status
        assert str(captured.value) == code
        assert post.call_count == 1
    finally:
        provider.close()


@pytest.mark.parametrize("status", ["PRIVATE", True, {}, 99, 600])
def test_failure_diagnostic_discards_non_status_values(status):
    assert GenerationFailure("invalid_response", http_status=status).http_status is None


@pytest.mark.parametrize("location", [None, "global", "europe-west4"])
def test_fake_vertex_evaluation_reports_effective_location_and_http_status(
    monkeypatch, location
):
    module = evaluator()
    settings = Settings(
        _env_file=None,
        vertex_location="asia-northeast1",
        generation_location=location,
        generation_model="synthetic-model",
        vertex_project_id="synthetic-project",
    )
    monkeypatch.setattr(module, "require_vertex_opt_in", lambda _: settings)
    provider = Mock()
    provider.generate.side_effect = [
        GenerationFailure("invalid_response", http_status=400),
        GenerationFailure("invalid_response", http_status=404),
        GenerationResult(
            text='{"cards":[{"term":"harbor","meaning":"shelter"}]}',
            model="synthetic-model",
        ),
    ]
    monkeypatch.setattr(module, "VertexGenerationProvider", lambda: provider)
    monkeypatch.setattr(
        requests, "post", lambda *a, **kw: pytest.fail("network forbidden")
    )
    cases = [
        {
            "id": str(index),
            "kind": "article",
            "input": {"material": "harbor"},
            "expected_terms": ["harbor"],
            "reviewed_by": None,
            "reviewed_on": None,
        }
        for index in range(3)
    ]
    report = module.run_vertex(cases, model_query_date="2026-11-05")
    effective = location or "asia-northeast1"
    assert report["location"] == effective
    assert [score["provider_http_status"] for score in report["cases"]] == [
        400,
        404,
        None,
    ]
    assert [score["provider_failure"] for score in report["cases"]] == [
        "invalid_response",
        "invalid_response",
        None,
    ]
    assert all(
        call.kwargs["location"] == effective
        for call in provider.generate.call_args_list
    )
    assert "PRIVATE" not in str(report)
    provider.close.assert_called_once()
