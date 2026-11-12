"""Offline assistant boundaries; handwritten wire fixtures are not live evidence."""

import time
from copy import deepcopy
from unittest.mock import Mock

import pytest

from app.assistant.loop import run_assistant
from app.assistant.tools import TOOL_SCHEMAS, validate_call
from app.config import Settings
from app.generation import (
    GenerationFailure,
    GenerationRequest,
    GenerationResult,
    GenerationUsage,
    build_vertex_request,
    parse_vertex_response,
)


def settings(**changes):
    return Settings(
        _env_file=None,
        generation_model="fake-v1",
        vertex_project_id="synthetic-project",
        **changes,
    )


def call(name="get_review_stats", **args):
    return {
        "functionCall": {"name": name, "args": args},
        "thoughtSignature": "opaque-signature",
    }


def result(parts):
    return parse_vertex_response(
        {
            "candidates": [
                {"finishReason": "STOP", "content": {"role": "model", "parts": parts}}
            ]
        }
    )


def test_assistant_function_wire_roundtrip_preserves_signature():
    parts = [
        {"text": "private reasoning", "thought": True, "thoughtSignature": "opaque"},
        call(target_language="en"),
    ]
    original = deepcopy(parts)
    parsed = result(parts)
    assert parsed.text == ""
    assert parsed.parts == original
    assert parsed.function_calls == [
        {"name": "get_review_stats", "args": {"target_language": "en"}}
    ]
    contents = [
        {"role": "model", "parts": parsed.parts},
        {
            "role": "user",
            "parts": [
                {
                    "functionResponse": {
                        "name": "get_review_stats",
                        "response": {"total_count": 2},
                    }
                }
            ],
        },
    ]
    request = GenerationRequest(
        system="rules",
        data={},
        contents=contents,
        tools=TOOL_SCHEMAS,
        tools_disabled=True,
    )
    wire = build_vertex_request(request, max_output_tokens=17)
    assert wire["contents"] == contents
    assert wire["tools"] == [{"functionDeclarations": TOOL_SCHEMAS}]
    assert wire["toolConfig"] == {"functionCallingConfig": {"mode": "NONE"}}
    assert wire["generationConfig"]["maxOutputTokens"] == 17
    assert parts == original


@pytest.mark.parametrize(
    "part",
    [
        {"functionCall": {"name": "x", "args": []}},
        {"functionCall": {"name": "x", "id": ""}},
        {"functionCall": {"name": "x", "id": " "}},
        {"functionCall": {"name": "x", "id": None}},
        {"functionCall": {"name": "x", "id": 1}},
        {"functionCall": {"name": "x", "args": {}}, "text": "mixed"},
        {"functionCall": {"name": "x", "args": {}, "owner_id": 1}},
        {"functionCall": {"name": "", "args": {}}},
        {"functionCall": {"name": "x", "args": {}}, "thoughtSignature": 9},
        {"functionResponse": {}},
    ],
)
def test_assistant_parser_rejects_malformed_function_parts(part):
    with pytest.raises(GenerationFailure, match="invalid_response"):
        result([part])


def test_assistant_registry_is_fixed_with_exact_minimal_schemas():
    filters = {
        "deck_id": {"type": "string"},
        "target_language": {"type": "string", "enum": ["en", "ja"]},
    }
    expected = [
        {
            "name": "search_cards",
            "description": "Search owned English cards by meaning.",
            "parameters": {
                "type": "object",
                "properties": {
                    **filters,
                    "target_language": {"type": "string", "enum": ["en"]},
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["query", "target_language"],
            },
        },
        {
            "name": "get_due_cards",
            "description": "Read the first page of owned due cards.",
            "parameters": {
                "type": "object",
                "properties": {**filters, "limit": {"type": "integer"}},
                "required": ["target_language"],
            },
        },
        {
            "name": "get_review_stats",
            "description": "Count owned active and due cards.",
            "parameters": {"type": "object", "properties": filters},
        },
    ]
    assert TOOL_SCHEMAS == expected
    for schema in TOOL_SCHEMAS:
        name = schema["name"]
        with pytest.raises(ValueError):
            validate_call(name, {"owner_id": 2}, settings())
    with pytest.raises(ValueError):
        validate_call("delete_cards", {}, settings())
    assert (
        validate_call(
            "get_due_cards", {"target_language": "ja", "limit": 999}, settings()
        )["limit"]
        == 10
    )
    assert (
        validate_call(
            "search_cards",
            {"query": "hello", "target_language": "en", "limit": -3},
            settings(),
        )["limit"]
        == 1
    )


@pytest.mark.parametrize(
    "field,default,minimum,maximum",
    [
        ("assistant_max_steps", 3, 1, 3),
        ("assistant_timeout_seconds", 25, 1, 120),
        ("assistant_max_output_tokens", 2048, 1, 8192),
        ("assistant_max_messages", 20, 1, 100),
        ("assistant_max_chars", 12000, 1, 100000),
        ("assistant_max_tool_calls", 3, 1, 10),
        ("assistant_tool_limit", 10, 1, 20),
        ("assistant_max_history_card_refs", 40, 0, 200),
    ],
)
def test_assistant_settings_have_bounds_and_env(
    monkeypatch, field, default, minimum, maximum
):
    assert getattr(settings(), field) == default
    for invalid in (minimum - 1, maximum + 1):
        with pytest.raises(ValueError):
            settings(**{field: invalid})
    for valid in (minimum, maximum):
        assert getattr(settings(**{field: valid}), field) == valid
    monkeypatch.setenv(field.upper(), "1")
    assert getattr(settings(), field) == 1


def run(provider, execute=None, **changes):
    return run_assistant(
        messages=[{"role": "user", "content": "PRIVATE_INPUT"}],
        settings=settings(**changes),
        provider=provider,
        execute=execute or Mock(return_value={"total_count": 1}),
        request_id="synthetic-request",
    )


def test_assistant_loop_caps_steps_disables_last_tools_and_logs_privately(capsys):
    provider = Mock()
    provider.generate.return_value = result([call(target_language="en")])
    execute = Mock(return_value={"private": "PRIVATE_CARD"})
    response = run(provider, execute)
    assert response.stop_reason == "max_steps"
    assert response.reply
    assert provider.generate.call_count == 3
    assert execute.call_count == 2
    assert [c.args[0].tools_disabled for c in provider.generate.call_args_list] == [
        False,
        False,
        True,
    ]
    assert "opaque-signature" in str(
        provider.generate.call_args_list[1].args[0].contents
    )
    import json

    logs = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(logs) == 3
    for step, log in enumerate(logs, 1):
        assert set(log) == {
            "event",
            "request_id",
            "step",
            "tool_names",
            "status",
            "duration_ms",
            "usage",
            "model_id",
        }
        assert (
            log["model_id"]
            == provider.generate.call_args_list[step - 1].kwargs["model"]
        )
        assert log["step"] == step
        assert log["request_id"] == "synthetic-request"
        assert "PRIVATE" not in str(log)
    assert "PRIVATE_CARD" not in response.model_dump_json()


def test_assistant_invalid_calls_get_fixed_errors_and_do_not_execute():
    provider = Mock()
    provider.generate.side_effect = [
        result([call("delete_cards"), call(owner_id=9)]),
        result([{"text": "Done"}]),
    ]
    execute = Mock()
    response = run(provider, execute)
    execute.assert_not_called()
    assert response.stop_reason == "completed"
    assert [c.status for c in response.tool_calls] == ["invalid_call", "invalid_call"]
    assert [c.arguments for c in response.tool_calls] == [None, None]
    second = provider.generate.call_args_list[1].args[0]
    assert [
        p["functionResponse"]["response"] for p in second.contents[-1]["parts"]
    ] == [{"error": "invalid_tool_call"}] * 2


def test_assistant_tool_count_cap_and_output_cap():
    provider = Mock()
    provider.generate.side_effect = [result([call()] * 4), result([{"text": "Done"}])]
    execute = Mock(return_value={})
    response = run(provider, execute, assistant_max_output_tokens=7)
    assert execute.call_count == 0
    assert all(c.status == "too_many_calls" for c in response.tool_calls)
    assert all(
        c.kwargs["max_output_tokens"] == 7 for c in provider.generate.call_args_list
    )
    provider.generate.side_effect = None
    provider.generate.return_value = GenerationResult(
        text="bad", usage=GenerationUsage(output_tokens=8)
    )
    with pytest.raises(GenerationFailure, match="truncated_output"):
        run(provider, assistant_max_output_tokens=7)


def test_assistant_total_deadline_discards_late_results(monkeypatch):
    from app.assistant import loop

    now = [0.0]
    monkeypatch.setattr(loop.time, "monotonic", lambda: now[0])
    provider = Mock()

    def late(*args, **kwargs):
        now[0] = 3.0
        return result([{"text": "late"}])

    provider.generate.side_effect = late
    response = run(provider, assistant_timeout_seconds=2)
    assert response.stop_reason == "timeout"
    assert response.reply != "late"
    assert provider.generate.call_args.kwargs["timeout_seconds"] <= 2


def test_assistant_usage_is_summed_and_plain_reply_completes():
    provider = Mock()
    provider.generate.side_effect = [
        GenerationResult(
            text="",
            parts=[call()],
            function_calls=[{"name": "get_review_stats", "args": {}}],
            usage=GenerationUsage(input_tokens=3, output_tokens=2, total_tokens=5),
        ),
        GenerationResult(
            text="Done",
            usage=GenerationUsage(input_tokens=4, output_tokens=1, total_tokens=5),
        ),
    ]
    response = run(provider)
    assert response.reply == "Done"
    assert response.usage.total_tokens == 10
    assert response.usage.input_tokens == 7


def test_assistant_wait_deadline_does_not_wait_for_blocked_provider():
    from threading import Event

    from app.assistant.loop import bounded_call

    started, release, finished = Event(), Event(), Event()

    def blocked():
        started.set()
        release.wait(5)
        finished.set()
        return "discarded"

    try:
        with pytest.raises(GenerationFailure, match="provider_timeout"):
            bounded_call(blocked, 0.03)
        assert started.is_set()
        assert not finished.is_set()
    finally:
        release.set()
        assert finished.wait(2)


def test_assistant_rejects_invalid_argument_types():
    for name, arguments in [
        ("get_due_cards", {"target_language": "en", "limit": True}),
        ("get_due_cards", {"target_language": "en", "limit": "2"}),
        ("get_due_cards", {"target_language": "xx"}),
        ("get_review_stats", {"deck_id": "not-a-uuid"}),
        ("get_review_stats", {"user_id": 1}),
        ("search_cards", {"query": " ", "target_language": "en"}),
    ]:
        with pytest.raises(ValueError):
            validate_call(name, arguments, settings())


def test_assistant_final_wire_thought_only_uses_max_steps_fallback(monkeypatch):
    import requests

    from app.generation import VertexGenerationProvider

    payload = {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {
                    "parts": [
                        {
                            "text": "PRIVATE_REASONING",
                            "thought": True,
                            "thoughtSignature": "opaque",
                        }
                    ]
                },
            }
        ]
    }
    post = Mock(return_value=Mock(json=lambda: payload))
    monkeypatch.setattr(requests, "post", post)
    provider = VertexGenerationProvider()
    monkeypatch.setattr(provider, "_access_token", lambda: "synthetic-token")
    execute = Mock()
    try:
        response = run(provider, execute, assistant_max_steps=1)
        assert response.stop_reason == "max_steps"
        assert "PRIVATE_REASONING" not in response.reply
        execute.assert_not_called()
        assert (
            post.call_args.kwargs["json"]["toolConfig"]["functionCallingConfig"]["mode"]
            == "NONE"
        )
        with pytest.raises(GenerationFailure, match="invalid_response"):
            parse_vertex_response(payload)
    finally:
        provider.close()


def test_assistant_replays_signed_stats_call_with_omitted_args():
    stats = {"functionCall": {"name": "get_review_stats"}, "thoughtSignature": "opaque"}
    provider = Mock()
    provider.generate.side_effect = [result([stats]), result([{"text": "Done"}])]
    execute = Mock(return_value={"total_count": 1})

    response = run(provider, execute)

    assert response.reply == "Done"
    assert execute.call_args.args[:2] == ("get_review_stats", {})
    assert provider.generate.call_args.args[0].contents[1] == {
        "role": "model",
        "parts": [stats],
    }
    assert stats["functionCall"] == {"name": "get_review_stats"}


def test_assistant_replies_to_identified_calls_with_matching_ids():
    stats = call()
    stats["functionCall"]["id"] = "first-call"
    invalid_stats = call(owner_id=1)
    invalid_stats["functionCall"]["id"] = "second-call"
    parts = [stats, invalid_stats]
    provider = Mock()
    provider.generate.side_effect = [result(parts), result([{"text": "Done"}])]
    execute = Mock(return_value={"total_count": 1})

    response = run(provider, execute)

    assert response.reply == "Done"
    execute.assert_called_once()
    wire = provider.generate.call_args.args[0].contents
    assert wire[-2] == {"role": "model", "parts": parts}
    assert wire[-1] == {
        "role": "user",
        "parts": [
            {
                "functionResponse": {
                    "id": "first-call",
                    "name": "get_review_stats",
                    "response": {"total_count": 1},
                }
            },
            {
                "functionResponse": {
                    "id": "second-call",
                    "name": "get_review_stats",
                    "response": {"error": "invalid_tool_call"},
                }
            },
        ],
    }
    assert "first-call" not in response.model_dump_json()
    assert "second-call" not in response.model_dump_json()


@pytest.mark.parametrize("credential_seconds", [1.5, 3])
def test_assistant_generation_http_obeys_deadline_after_credentials(
    monkeypatch, credential_seconds
):
    import time

    import requests

    from app.generation import VertexGenerationProvider

    now = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])

    def access_token():
        now[0] += credential_seconds
        return "synthetic-token"

    provider = VertexGenerationProvider()
    monkeypatch.setattr(provider, "_access_token", access_token)
    post = Mock(
        return_value=Mock(
            json=lambda: {
                "candidates": [
                    {"finishReason": "STOP", "content": {"parts": [{"text": "Done"}]}}
                ]
            }
        )
    )
    monkeypatch.setattr(requests, "post", post)
    try:
        response = run(provider, assistant_timeout_seconds=2)
    finally:
        provider.close()

    if credential_seconds >= 2:
        assert response.stop_reason == "timeout"
        post.assert_not_called()
    else:
        assert response.reply == "Done"
        assert post.call_args.kwargs["timeout"] == pytest.approx(0.5)


@pytest.mark.parametrize("credential_seconds", [1.5, 3])
def test_assistant_embedding_http_obeys_deadline_after_credentials(
    monkeypatch, credential_seconds
):
    import time
    from types import SimpleNamespace

    import requests

    from app.assistant.tools import SessionTools
    from app.embeddings import VertexEmbeddingProvider

    now = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])

    def access_token():
        now[0] += credential_seconds
        return "synthetic-token"

    embedding = VertexEmbeddingProvider()
    monkeypatch.setattr(embedding, "_access_token", access_token)
    post = Mock(side_effect=requests.Timeout)
    monkeypatch.setattr(requests, "post", post)
    provider = Mock()
    provider.generate.side_effect = [
        result([call("search_cards", query="harbor", target_language="en")]),
        result([{"text": "Done"}]),
    ]
    session = Mock()
    session.execute.return_value.mappings.return_value.one.return_value = (
        SimpleNamespace(eligible_count=1, indexed_count=1)
    )
    options = settings(assistant_timeout_seconds=2)
    execute = SessionTools(session, 1, options, embedding)

    try:
        response = run(provider, execute, assistant_timeout_seconds=2)
    finally:
        embedding.close()

    if credential_seconds >= 2:
        assert response.stop_reason == "timeout"
        post.assert_not_called()
        assert provider.generate.call_count == 1
    else:
        assert post.call_args.kwargs["timeout"] == pytest.approx(0.5)


def test_disconnected_tool_does_not_start_sql_after_statement_budget(monkeypatch):
    from threading import Event
    from unittest.mock import Mock

    from app.assistant import tools

    disconnected = Event()
    session = Mock()

    def execute(statement, *args):
        if "statement_timeout" in str(statement):
            disconnected.set()

    session.execute.side_effect = execute
    stats = Mock()
    monkeypatch.setattr(tools, "get_review_stats", stats)
    execute_tool = tools.SessionTools(
        session, 1, None, None, cancelled=disconnected.is_set
    )
    with pytest.raises(GenerationFailure, match="provider_timeout"):
        execute_tool("get_review_stats", {}, time.monotonic() + 5)
    stats.assert_not_called()
    session.rollback.assert_called_once()


def test_assistant_sse_heartbeat_settings_have_bounds_and_env(monkeypatch):
    assert settings().assistant_sse_heartbeat_seconds == 15
    for valid in (0, 1, 60):
        assert (
            settings(
                assistant_sse_heartbeat_seconds=valid
            ).assistant_sse_heartbeat_seconds
            == valid
        )
    for invalid in (-1, 61):
        with pytest.raises(ValueError):
            settings(assistant_sse_heartbeat_seconds=invalid)
    for value in ("0", "1", "60"):
        monkeypatch.setenv("ASSISTANT_SSE_HEARTBEAT_SECONDS", value)
        assert settings().assistant_sse_heartbeat_seconds == int(value)
