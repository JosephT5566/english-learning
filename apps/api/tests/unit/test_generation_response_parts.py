"""Review-derived response fixtures only; no live Vertex compatibility claim."""

from unittest.mock import Mock

import pytest
import requests
from urllib3.exceptions import DecodeError, ProtocolError

from app.generation import (
    GenerationFailure,
    VertexGenerationProvider,
    parse_vertex_response,
)
from tests.unit.test_generation import request, sample

ANSWER = '{"cards":[{"term":"harbor","meaning":"shelter"}]}'
OPTIONS = {
    "model": "synthetic-v1",
    "project": "synthetic-project",
    "location": "us-central1",
    "timeout_seconds": 30,
    "max_output_tokens": 8192,
}


def response_parts(parts):
    return sample(candidates=[{"finishReason": "STOP", "content": {"parts": parts}}])


@pytest.mark.parametrize(
    "metadata",
    [
        {"thoughtSignature": "synthetic-signature"},
        {"thought": False, "thoughtSignature": "synthetic-signature"},
    ],
)
def test_final_text_accepts_review_documented_metadata(metadata):
    result = parse_vertex_response(response_parts([{"text": ANSWER, **metadata}]))
    assert result.text == ANSWER
    assert result.model == "synthetic-v1"
    assert result.usage.total_tokens == 23


def test_only_final_text_parts_are_combined_in_order():
    result = parse_vertex_response(
        response_parts(
            [
                {
                    "text": "PRIVATE_THOUGHT not JSON",
                    "thought": True,
                    "thoughtSignature": "hidden",
                },
                {"text": ANSWER[:20], "thoughtSignature": "first"},
                {"text": "PRIVATE_THOUGHT more reasoning", "thought": True},
                {"text": ANSWER[20:], "thought": False, "thoughtSignature": "last"},
            ]
        )
    )
    assert result.text == ANSWER
    assert "PRIVATE_THOUGHT" not in result.text


@pytest.mark.parametrize(
    "key",
    [
        "functionCall",
        "functionResponse",
        "inlineData",
        "fileData",
        "executableCode",
        "codeExecutionResult",
        "unknownMetadata",
    ],
)
@pytest.mark.parametrize("with_text", [False, True])
def test_non_text_content_and_unknown_keys_are_rejected(key, with_text):
    part = {key: {"synthetic": "PRIVATE_CONTENT"}}
    if with_text:
        part["text"] = ANSWER
    with pytest.raises(GenerationFailure, match="^invalid_response$"):
        parse_vertex_response(response_parts([part]))


@pytest.mark.parametrize(
    "parts",
    [
        [{"text": "reasoning only", "thought": True}],
        [{"text": "", "thoughtSignature": "synthetic"}],
        [{"text": None, "thought": True}],
        [{"text": 1, "thoughtSignature": "synthetic"}],
        [{"text": ANSWER, "thought": "true"}],
        [{"text": ANSWER, "thought": 1}],
        [{"text": ANSWER, "thoughtSignature": {}}],
        [{"text": ANSWER, "thoughtSignature": None}],
        [{"text": ANSWER}, {"text": "reasoning", "thought": True, "functionCall": {}}],
        [],
    ],
)
def test_missing_final_answer_or_malformed_text_metadata_is_rejected(parts):
    with pytest.raises(GenerationFailure, match="^invalid_response$"):
        parse_vertex_response(response_parts(parts))


@pytest.mark.parametrize(
    "candidate_change",
    [
        {"finishReason": "SAFETY"},
        {"finishReason": None},
    ],
)
def test_metadata_does_not_relax_finish_reason(candidate_change):
    candidate = {
        "finishReason": "STOP",
        "content": {"parts": [{"text": ANSWER, "thoughtSignature": "synthetic"}]},
        **candidate_change,
    }
    with pytest.raises(GenerationFailure, match="^invalid_response$"):
        parse_vertex_response(sample(candidates=[candidate]))


def test_multiple_candidates_still_rejected():
    candidate = {"finishReason": "STOP", "content": {"parts": [{"text": ANSWER}]}}
    with pytest.raises(GenerationFailure, match="^invalid_response$"):
        parse_vertex_response(sample(candidates=[candidate, candidate]))


def test_real_requests_json_decode_error_is_invalid_response(monkeypatch):
    response = requests.Response()
    response.status_code = 200
    response._content = b"not json PRIVATE_BODY"
    with pytest.raises(requests.exceptions.JSONDecodeError) as error:
        response.json()
    assert isinstance(error.value, requests.RequestException)
    assert isinstance(error.value, ValueError)
    post = Mock(return_value=response)
    monkeypatch.setattr(requests, "post", post)
    provider = VertexGenerationProvider()
    monkeypatch.setattr(provider, "_access_token", lambda: "synthetic-token")
    try:
        with pytest.raises(GenerationFailure, match="^invalid_response$") as failure:
            provider.generate(request(), **OPTIONS)
        assert "PRIVATE_BODY" not in str(failure.value)
        assert post.call_count == 1
    finally:
        provider.close()


@pytest.mark.parametrize(
    "read_error,expected_exception",
    [
        (DecodeError, requests.exceptions.ContentDecodingError),
        (ProtocolError, requests.exceptions.ChunkedEncodingError),
    ],
)
def test_body_decoding_or_chunk_failure_is_invalid_response(
    monkeypatch, read_error, expected_exception
):
    response = requests.Response()
    response.status_code = 200
    response.raw = Mock()
    response.raw.stream.side_effect = read_error("PRIVATE_BODY")
    with pytest.raises(expected_exception):
        response.json()
    post = Mock(return_value=response)
    monkeypatch.setattr(requests, "post", post)
    provider = VertexGenerationProvider()
    monkeypatch.setattr(provider, "_access_token", lambda: "synthetic-token")
    try:
        with pytest.raises(GenerationFailure, match="^invalid_response$") as failure:
            provider.generate(request(), **OPTIONS)
        assert "PRIVATE_BODY" not in str(failure.value)
        assert post.call_count == 1
    finally:
        provider.close()
