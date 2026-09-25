"""Synthetic provider contract tests with no network or credentials."""

import google.auth
import pytest
import requests
from app.embeddings import (
    EmbeddingFailure,
    vertex_document_embedding,
    vertex_query_embedding,
)
from app.semantic_text import DIMENSIONS


class FakeCredentials:
    token = "synthetic-token"

    def refresh(self, _request: object) -> None:
        return None


class FakeResponse:
    def __init__(self, values: list[float], *, truncated: bool = False):
        self.values = values
        self.truncated = truncated

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "predictions": [
                {
                    "embeddings": {
                        "values": self.values,
                        "statistics": {"truncated": self.truncated, "token_count": 3},
                    }
                }
            ]
        }


def test_document_request_uses_selected_model_task_and_dimension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(google.auth, "default", lambda **_: (FakeCredentials(), None))
    observed = {}

    def post(url: str, **kwargs: object) -> FakeResponse:
        observed.update({"url": url, **kwargs})
        return FakeResponse([1.0] * DIMENSIONS)

    monkeypatch.setattr(requests, "post", post)
    result = vertex_document_embedding(
        "language: en\nterm: example",
        project="synthetic-project",
        location="us-central1",
    )
    assert len(result) == DIMENSIONS
    assert observed["url"].endswith("/models/gemini-embedding-001:predict")
    assert observed["json"] == {
        "instances": [
            {
                "content": "language: en\nterm: example",
                "task_type": "RETRIEVAL_DOCUMENT",
            }
        ],
        "parameters": {"autoTruncate": False, "outputDimensionality": DIMENSIONS},
    }
    assert observed["timeout"] == 8


def test_query_request_uses_retrieval_query_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(google.auth, "default", lambda **_: (FakeCredentials(), None))
    observed = {}

    def post(_url: str, **kwargs: object) -> FakeResponse:
        observed.update(kwargs)
        return FakeResponse([1.0] * DIMENSIONS)

    monkeypatch.setattr(requests, "post", post)
    assert (
        len(
            vertex_query_embedding(
                "a lucky discovery",
                project="synthetic-project",
                location="us-central1",
            )
        )
        == DIMENSIONS
    )
    assert observed["json"]["instances"][0]["task_type"] == "RETRIEVAL_QUERY"


@pytest.mark.parametrize(
    "response,code",
    [
        (FakeResponse([1.0] * (DIMENSIONS - 1)), "invalid_dimension"),
        (FakeResponse([1.0] * DIMENSIONS, truncated=True), "truncated_input"),
    ],
)
def test_provider_rejects_invalid_results(
    monkeypatch: pytest.MonkeyPatch,
    response: FakeResponse,
    code: str,
) -> None:
    monkeypatch.setattr(google.auth, "default", lambda **_: (FakeCredentials(), None))
    monkeypatch.setattr(requests, "post", lambda *_args, **_kwargs: response)
    with pytest.raises(EmbeddingFailure) as error:
        vertex_document_embedding(
            "synthetic", project="synthetic-project", location="us-central1"
        )
    assert error.value.code == code


def test_provider_timeout_maps_to_safe_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(google.auth, "default", lambda **_: (FakeCredentials(), None))

    def timeout(*_args: object, **_kwargs: object) -> None:
        raise requests.Timeout("sensitive transport detail")

    monkeypatch.setattr(requests, "post", timeout)
    with pytest.raises(EmbeddingFailure) as error:
        vertex_document_embedding(
            "synthetic", project="synthetic-project", location="us-central1"
        )
    assert error.value.code == "provider_timeout"
