"""Content-safe semantic candidate smoke validation."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

VALIDATOR_PATH = (
    Path(__file__).parents[4] / "deploy" / "cloud-run" / "validate_semantic_smoke.py"
)
REQUEST_ID = "99999999-9999-4999-8999-999999999999"


def load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "semantic_smoke_validator", VALIDATOR_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def valid_response() -> dict[str, object]:
    return {
        "items": [
            {
                "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "distance": 0.08,
                "score": 0.92,
                "term": "private value is never copied to the report",
            },
            {
                "id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                "distance": 0.25,
                "score": 0.75,
                "meaning": "private value is never copied to the report",
            },
        ],
        "index_status": "complete",
        "eligible_count": 596,
        "indexed_count": 596,
    }


def test_valid_response_returns_only_safe_observations() -> None:
    validator = load_validator()
    report = validator.validate(
        valid_response(),
        f"HTTP/2 200\r\nX-Request-ID: {REQUEST_ID}\r\n",
        "200\t1.234567\n",
    )
    assert report == {
        "status_code": 200,
        "request_id": REQUEST_ID,
        "result_count": 2,
        "index_status": "complete",
        "eligible_count": 596,
        "indexed_count": 596,
        "total_seconds": 1.234567,
    }
    assert "term" not in report and "meaning" not in report


@pytest.mark.parametrize(
    "mutate,expected",
    [
        (lambda body: body["items"][0].update({"embedding": [0.1]}), "unsafe"),
        (lambda body: body["items"].reverse(), "stable distance order"),
        (lambda body: body["items"][0].update({"score": 0.5}), "score contract"),
        (lambda body: body.update({"indexed_count": 595}), "complete"),
        (lambda body: body.update({"items": []}), "contract"),
    ],
)
def test_invalid_or_private_response_is_rejected(mutate: object, expected: str) -> None:
    validator = load_validator()
    body = valid_response()
    mutate(body)
    with pytest.raises(ValueError, match=expected):
        validator.validate(
            body,
            f"X-Request-ID: {REQUEST_ID}\r\n",
            "200\t1.0\n",
        )


def test_missing_request_id_and_failed_status_are_rejected() -> None:
    validator = load_validator()
    with pytest.raises(ValueError, match="omitted"):
        validator.validate(valid_response(), "HTTP/2 200\r\n", "200\t1.0\n")
    with pytest.raises(ValueError, match="did not complete"):
        validator.validate(
            valid_response(),
            f"X-Request-ID: {REQUEST_ID}\r\n",
            "503\t1.0\n",
        )
