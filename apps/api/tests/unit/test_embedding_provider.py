"""Synthetic provider lifecycle and contract checks with no ADC or network access."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event
from unittest.mock import Mock

import google.auth
import pytest
import requests
from fastapi.testclient import TestClient
from google.auth import _helpers
from google.auth.credentials import Credentials
from google.auth.exceptions import DefaultCredentialsError, RefreshError

from app import health, main
from app.embeddings import EmbeddingFailure, VertexEmbeddingProvider
from app.semantic_text import DIMENSIONS

PROJECT = {"project": "synthetic-project", "location": "us-central1"}


class FakeCredentials(Credentials):
    def __init__(self) -> None:
        super().__init__()
        self.refreshes = 0
        self.fail_refresh = False

    def refresh(self, _request: object) -> None:
        self.refreshes += 1
        if self.fail_refresh:
            raise RefreshError("sensitive auth detail")
        self.token = f"synthetic-token-{self.refreshes}"
        self.expiry = _helpers.utcnow() + timedelta(hours=1)


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


@pytest.fixture
def credentials(monkeypatch: pytest.MonkeyPatch) -> FakeCredentials:
    credentials = FakeCredentials()
    monkeypatch.setattr(google.auth, "default", lambda **_: (credentials, None))
    monkeypatch.setattr(
        requests, "post", lambda *_args, **_kwargs: FakeResponse([1.0] * DIMENSIONS)
    )
    return credentials


@pytest.fixture
def provider() -> Iterator[VertexEmbeddingProvider]:
    provider = VertexEmbeddingProvider()
    yield provider
    provider.close()


@pytest.mark.parametrize(
    "method,task",
    [
        ("document_embedding", "RETRIEVAL_DOCUMENT"),
        ("query_embedding", "RETRIEVAL_QUERY"),
    ],
)
def test_request_preserves_model_payload_timeout_and_token(
    monkeypatch: pytest.MonkeyPatch,
    credentials: FakeCredentials,
    provider: VertexEmbeddingProvider,
    method: str,
    task: str,
) -> None:
    observed = {}

    def post(url: str, **kwargs: object) -> FakeResponse:
        observed.update({"url": url, **kwargs})
        return FakeResponse([1.0] * DIMENSIONS)

    monkeypatch.setattr(requests, "post", post)
    result = getattr(provider, method)("synthetic content", **PROJECT)
    assert len(result) == DIMENSIONS
    assert observed["url"] == (
        "https://us-central1-aiplatform.googleapis.com/v1/projects/synthetic-project"
        "/locations/us-central1/publishers/google/models/gemini-embedding-001:predict"
    )
    assert observed["json"] == {
        "instances": [{"content": "synthetic content", "task_type": task}],
        "parameters": {"autoTruncate": False, "outputDimensionality": DIMENSIONS},
    }
    assert observed["headers"] == {"Authorization": "Bearer synthetic-token-1"}
    assert observed["timeout"] == 8
    assert credentials.refreshes == 1


def test_repeated_requests_discover_once_and_reuse_fresh_token(
    monkeypatch: pytest.MonkeyPatch, provider: VertexEmbeddingProvider
) -> None:
    credentials = FakeCredentials()
    credentials.refresh(None)
    discover = Mock(return_value=(credentials, None))
    post = Mock(return_value=FakeResponse([1.0] * DIMENSIONS))
    monkeypatch.setattr(google.auth, "default", discover)
    monkeypatch.setattr(requests, "post", post)
    provider.document_embedding("first", **PROJECT)
    provider.query_embedding("second", **PROJECT)
    discover.assert_called_once_with(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    assert credentials.refreshes == 1
    assert post.call_count == 2


@pytest.mark.parametrize("seconds_to_expiry", [60, -1])
def test_concurrent_first_use_and_expiry_refresh_once_with_independent_predictions(
    monkeypatch: pytest.MonkeyPatch,
    provider: VertexEmbeddingProvider,
    seconds_to_expiry: int,
) -> None:
    credentials = FakeCredentials()
    discover = Mock(return_value=(credentials, None))
    monkeypatch.setattr(google.auth, "default", discover)
    predictions = Barrier(6)
    headers = []

    def post(_url: str, **kwargs: object) -> FakeResponse:
        predictions.wait(timeout=5)
        headers.append(kwargs["headers"]["Authorization"])
        return FakeResponse([1.0] * DIMENSIONS)

    monkeypatch.setattr(requests, "post", post)

    def wave() -> None:
        start = Barrier(6)

        def embed(_index: int) -> list[float]:
            start.wait(timeout=5)
            return provider.document_embedding("synthetic", **PROJECT)

        with ThreadPoolExecutor(max_workers=6) as pool:
            assert all(
                len(vector) == DIMENSIONS for vector in pool.map(embed, range(6))
            )

    wave()
    assert discover.call_count == 1
    assert credentials.refreshes == 1
    assert headers == ["Bearer synthetic-token-1"] * 6
    credentials.expiry = _helpers.utcnow() + timedelta(seconds=seconds_to_expiry)
    headers.clear()
    wave()
    assert discover.call_count == 1
    assert credentials.refreshes == 2
    assert headers == ["Bearer synthetic-token-2"] * 6


def test_in_flight_prediction_keeps_its_token_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    credentials: FakeCredentials,
    provider: VertexEmbeddingProvider,
) -> None:
    entered, release = Event(), Event()
    headers = {}

    def post(_url: str, **kwargs: object) -> FakeResponse:
        content = kwargs["json"]["instances"][0]["content"]
        if content == "first":
            entered.set()
            assert release.wait(timeout=5)
        headers[content] = kwargs["headers"]["Authorization"]
        return FakeResponse([1.0] * DIMENSIONS)

    monkeypatch.setattr(requests, "post", post)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(provider.document_embedding, "first", **PROJECT)
        try:
            assert entered.wait(timeout=5)
            credentials.expiry = _helpers.utcnow() - timedelta(seconds=1)
            provider.query_embedding("second", **PROJECT)
        finally:
            release.set()
        assert len(first.result(timeout=5)) == DIMENSIONS
    assert headers == {
        "first": "Bearer synthetic-token-1",
        "second": "Bearer synthetic-token-2",
    }


@pytest.mark.parametrize("failure", ["discovery", "refresh"])
def test_auth_failure_is_safe_and_next_call_recovers(
    monkeypatch: pytest.MonkeyPatch, provider: VertexEmbeddingProvider, failure: str
) -> None:
    credentials = FakeCredentials()
    discover = Mock(return_value=(credentials, None))
    if failure == "discovery":
        discover.side_effect = [
            DefaultCredentialsError("sensitive ADC detail"),
            (credentials, None),
        ]
    else:
        credentials.fail_refresh = True
    monkeypatch.setattr(google.auth, "default", discover)
    post = Mock(return_value=FakeResponse([1.0] * DIMENSIONS))
    monkeypatch.setattr(requests, "post", post)
    with pytest.raises(EmbeddingFailure, match="^provider_auth_error$"):
        provider.document_embedding("synthetic", **PROJECT)
    post.assert_not_called()
    credentials.fail_refresh = False
    assert len(provider.query_embedding("synthetic", **PROJECT)) == DIMENSIONS
    assert discover.call_count == 2
    assert post.call_count == 1


@pytest.mark.parametrize("status,refreshes", [(401, 2), (403, 1)])
def test_rejected_token_refreshes_only_on_next_call_after_401(
    monkeypatch: pytest.MonkeyPatch,
    credentials: FakeCredentials,
    provider: VertexEmbeddingProvider,
    status: int,
    refreshes: int,
) -> None:
    rejected = requests.Response()
    rejected.status_code = status
    post = Mock(side_effect=[rejected, FakeResponse([1.0] * DIMENSIONS)])
    monkeypatch.setattr(requests, "post", post)

    with pytest.raises(EmbeddingFailure, match="^provider_http_error$"):
        provider.document_embedding("first", **PROJECT)
    assert post.call_count == 1
    assert credentials.refreshes == 1

    assert len(provider.query_embedding("second", **PROJECT)) == DIMENSIONS
    assert post.call_count == 2
    assert credentials.refreshes == refreshes
    assert post.call_args.kwargs["headers"] == {
        "Authorization": f"Bearer synthetic-token-{refreshes}"
    }


def test_delayed_401_does_not_invalidate_newer_token(
    monkeypatch: pytest.MonkeyPatch,
    credentials: FakeCredentials,
    provider: VertexEmbeddingProvider,
) -> None:
    entered, release = Event(), Event()
    headers = {}

    def post(_url: str, **kwargs: object) -> FakeResponse | requests.Response:
        content = kwargs["json"]["instances"][0]["content"]
        headers[content] = kwargs["headers"]["Authorization"]
        if content == "first":
            entered.set()
            assert release.wait(timeout=5)
            rejected = requests.Response()
            rejected.status_code = 401
            return rejected
        return FakeResponse([1.0] * DIMENSIONS)

    monkeypatch.setattr(requests, "post", post)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(provider.document_embedding, "first", **PROJECT)
        try:
            assert entered.wait(timeout=5)
            credentials.expiry = _helpers.utcnow() - timedelta(seconds=1)
            assert len(provider.query_embedding("second", **PROJECT)) == DIMENSIONS
        finally:
            release.set()
        with pytest.raises(EmbeddingFailure, match="^provider_http_error$"):
            first.result(timeout=5)

    assert len(provider.query_embedding("third", **PROJECT)) == DIMENSIONS
    assert credentials.refreshes == 2
    assert headers == {
        "first": "Bearer synthetic-token-1",
        "second": "Bearer synthetic-token-2",
        "third": "Bearer synthetic-token-2",
    }


def test_providers_have_independent_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credentials = [FakeCredentials(), FakeCredentials()]
    discover = Mock(side_effect=[(credential, None) for credential in credentials])
    monkeypatch.setattr(google.auth, "default", discover)
    monkeypatch.setattr(
        requests, "post", lambda *_args, **_kwargs: FakeResponse([1.0] * DIMENSIONS)
    )
    first, second = VertexEmbeddingProvider(), VertexEmbeddingProvider()
    try:
        first.document_embedding("first", **PROJECT)
        second.query_embedding("second", **PROJECT)
        first.query_embedding("third", **PROJECT)
        assert discover.call_count == 2
        assert [credential.refreshes for credential in credentials] == [1, 1]
    finally:
        first.close()
        second.close()


def test_close_releases_auth_transport_and_rejects_further_use(
    monkeypatch: pytest.MonkeyPatch,
    credentials: FakeCredentials,
    provider: VertexEmbeddingProvider,
) -> None:
    close = Mock()
    monkeypatch.setattr(requests.Session, "close", close)
    provider.document_embedding("synthetic", **PROJECT)
    provider.close()
    close.assert_called_once_with()
    with pytest.raises(EmbeddingFailure, match="^provider_unavailable$"):
        provider.query_embedding("synthetic", **PROJECT)
    provider.close()
    close.assert_called_once_with()
    assert credentials.refreshes == 1


@pytest.mark.parametrize("configured", [False, True])
def test_app_lifespan_and_health_are_lazy_and_close_owned_provider(
    monkeypatch: pytest.MonkeyPatch, configured: bool
) -> None:
    if configured:
        monkeypatch.setenv("VERTEX_PROJECT_ID", "synthetic-project")
    else:
        monkeypatch.delenv("VERTEX_PROJECT_ID", raising=False)
    discover = Mock(side_effect=AssertionError("ADC must remain lazy"))
    monkeypatch.setattr(google.auth, "default", discover)
    monkeypatch.setattr(health, "check_database_readiness", lambda _engine: True)
    providers = []
    closed = []

    class ObservedProvider(VertexEmbeddingProvider):
        def __init__(self) -> None:
            super().__init__()
            providers.append(self)

        def close(self) -> None:
            closed.append(self)
            super().close()

    monkeypatch.setattr(main, "VertexEmbeddingProvider", ObservedProvider)
    app = main.create_app()
    assert providers == []
    for _ in range(2):
        with TestClient(app) as client:
            assert client.get("/health/live").status_code == 200
            assert client.get("/health/ready").status_code == 200
            assert app.state.embedding_provider is providers[-1]
        assert closed[-1] is providers[-1]
    assert len(providers) == len(closed) == 2
    assert providers[0] is not providers[1]
    discover.assert_not_called()


@pytest.mark.parametrize(
    "response,code",
    [
        (FakeResponse([1.0] * (DIMENSIONS - 1)), "invalid_dimension"),
        (FakeResponse([float("nan")] * DIMENSIONS), "invalid_value"),
        (FakeResponse([0.0] * DIMENSIONS), "zero_vector"),
        (FakeResponse([1.0] * DIMENSIONS, truncated=True), "truncated_input"),
    ],
)
def test_provider_rejects_invalid_results(
    monkeypatch: pytest.MonkeyPatch,
    credentials: FakeCredentials,
    provider: VertexEmbeddingProvider,
    response: FakeResponse,
    code: str,
) -> None:
    monkeypatch.setattr(requests, "post", lambda *_args, **_kwargs: response)
    with pytest.raises(EmbeddingFailure) as error:
        provider.document_embedding("synthetic", **PROJECT)
    assert error.value.code == code


@pytest.mark.parametrize(
    "failure,code",
    [
        (requests.Timeout("sensitive detail"), "provider_timeout"),
        (requests.ConnectionError("sensitive detail"), "provider_http_error"),
    ],
)
def test_transport_failure_maps_to_safe_code(
    monkeypatch: pytest.MonkeyPatch,
    credentials: FakeCredentials,
    provider: VertexEmbeddingProvider,
    failure: Exception,
    code: str,
) -> None:
    monkeypatch.setattr(requests, "post", Mock(side_effect=failure))
    with pytest.raises(EmbeddingFailure) as error:
        provider.document_embedding("synthetic", **PROJECT)
    assert error.value.code == code
