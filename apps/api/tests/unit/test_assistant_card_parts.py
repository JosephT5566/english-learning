"""Offline parts contract, loop and bounded ASGI transport with scripted providers."""

import asyncio
import inspect
import json
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from app.assistant.loop import AssistantResponse, run_assistant
from app.assistant.sse import AssistantSSE, stream_events
from app.config import Settings
from app.generation import GenerationFailure, parse_vertex_response

ITEM = {"id": "card", "deck_id": "deck", "term": "harbor", "meaning": "port"}


@pytest.fixture(autouse=True)
def stable_tool_duration(monkeypatch):
    from app.assistant import loop

    monkeypatch.setattr(loop, "round", lambda value: 0, raising=False)


def settings(**changes):
    return Settings(
        _env_file=None,
        generation_model="fake",
        vertex_project_id="synthetic-project",
        **changes,
    )


def prepared(*, names=("get_due_cards",), timeout=False, execute=None):
    calls = [
        {
            "functionCall": {
                "name": name,
                "args": {
                    "target_language": "en",
                    **({"query": "harbor"} if name == "search_cards" else {}),
                },
            }
        }
        for name in names
    ]
    result = parse_vertex_response(
        {
            "candidates": [
                {"finishReason": "STOP", "content": {"role": "model", "parts": calls}}
            ]
        }
    )
    provider = Mock()
    provider.generate.side_effect = (
        [result, GenerationFailure("provider_timeout")] if timeout else [result]
    )
    return run_assistant(
        messages=[{"role": "user", "content": "due?"}],
        settings=settings(assistant_max_steps=3 if timeout else 2),
        provider=provider,
        execute=execute or (lambda *args: {"items": [{**ITEM, "note": "private"}]}),
        request_id="parts",
        prepare_final=True,
    )


def events(prepare, provider, config, deadline, enabled):
    # Exercise old transport behavior for red-first frame assertions, before the flag exists.
    options = (
        {"parts_enabled": enabled}
        if "parts_enabled" in inspect.signature(stream_events).parameters
        else {}
    )
    return stream_events(prepare, provider, config, deadline, "parts", **options)


async def capture(
    *,
    enabled=True,
    timeout=False,
    slow=False,
    blocked=None,
    disconnect=False,
    names=("get_due_cards",),
):
    result = prepared(timeout=timeout, names=names)
    opened = False
    messages = []
    incoming = asyncio.Queue()
    config = settings(assistant_sse_heartbeat_seconds=1 if slow else 0)
    deadline = time.monotonic() + (0.15 if blocked else 4)

    def prepare(cancelled):
        if slow:
            time.sleep(1.2)
        return result

    async def upstream(*args, **kwargs):
        nonlocal opened
        opened = True
        yield SimpleNamespace(text="answer", usage=None)

    async def send(message):
        body = message.get("body", b"")
        if body.startswith(b"event: part") and blocked:
            blocked.set()
            if disconnect:
                incoming.put_nowait({"type": "http.disconnect"})
            await asyncio.Event().wait()
        messages.append(message.copy())

    response = AssistantSSE(
        events(prepare, SimpleNamespace(stream=upstream), config, deadline, enabled),
        deadline=deadline,
        request_id="parts",
    )
    await asyncio.wait_for(response({}, incoming.get, send), 5)
    return (
        [m["body"] for m in messages if m["type"] == "http.response.body"],
        opened,
        deadline,
    )


def test_parts_precede_delta_and_do_not_change_done():
    async def scenario():
        active, _, _ = await capture()
        baseline, _, _ = await capture(enabled=False)
        assert active[0].startswith(b"event: part\n")
        assert active[1:] == baseline
        assert json.loads(active[0].split(b"data: ")[1]) == {
            "id": "p1",
            "type": "card_list",
            "payload": {"purpose": "due", "items": [ITEM]},
        }

    asyncio.run(scenario())


def test_parts_call_order_and_allowlist():
    result = prepared(names=("search_cards", "get_review_stats", "get_due_cards"))
    parts = getattr(result, "parts", [])
    assert [p["id"] for p in parts] == ["p1", "p2"]
    assert [p["payload"]["purpose"] for p in parts] == ["search", "due"]
    assert all(p["payload"]["items"] == [ITEM] for p in parts)


@pytest.mark.parametrize(
    "name,purpose", [("get_due_cards", "due"), ("search_cards", "search")]
)
def test_builder_allowlist_and_suppression(name, purpose):
    output = {
        "items": [
            {
                **ITEM,
                "note": "private",
                "reading": "x",
                "pronunciation": "x",
                "romanization": "x",
                "part_of_speech": "x",
                "score": 1,
                "distance": 0,
            }
        ]
    }
    expected = {
        "id": "p1",
        "type": "card_list",
        "payload": {"purpose": purpose, "items": [ITEM]},
    }
    pending = prepared(names=(name,), execute=lambda *args: output)
    assert getattr(pending, "parts", []) == [expected]
    from app.assistant.parts import build_part

    assert build_part(name, output, "ok", 1) == expected
    assert build_part("get_review_stats", output, "ok", 1) is None
    assert build_part(name, {"items": []}, "ok", 1) is None
    for status in (
        "invalid_call",
        "too_many_calls",
        "tool_unavailable",
        "tools_disabled",
        "timeout",
    ):
        assert build_part(name, output, status, 1) is None


def test_timeout_response_carries_private_parts_before_done():
    result = prepared(timeout=True)
    assert isinstance(result, AssistantResponse)
    assert set(result.model_dump()) == {"reply", "tool_calls", "stop_reason", "usage"}

    async def scenario():
        active, opened, _ = await capture(timeout=True)
        baseline, _, _ = await capture(timeout=True, enabled=False)
        assert active[0].startswith(b"event: part\n")
        assert active[1:] == baseline
        assert not opened
        assert b'"stop_reason":"timeout"' in active[-2]

    asyncio.run(scenario())


def test_parts_stop_heartbeats_before_first_part():
    async def scenario():
        bodies, _, _ = await capture(slow=True)
        assert bodies[0] == b": ping\n\n"
        first = next(
            i for i, body in enumerate(bodies) if body.startswith(b"event: part")
        )
        assert all(body == b": ping\n\n" for body in bodies[:first])
        assert b": ping\n\n" not in bodies[first:]

    asyncio.run(scenario())


@pytest.mark.parametrize("disconnect", [False, True])
def test_blocked_part_never_opens_provider_or_sends_late_part(disconnect):
    async def scenario():
        blocked = asyncio.Event()
        bodies, opened, deadline = await capture(blocked=blocked, disconnect=disconnect)
        assert blocked.is_set()
        assert not opened
        assert time.monotonic() <= deadline + 0.2
        if not disconnect:
            assert len(bodies) == 2
            assert bodies[0].startswith(b"event: done\n")
            assert b'"stop_reason":"timeout"' in bodies[0]
            assert bodies[-1] == b""

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "capabilities", [["x"] * 9, [1], ["Upper"], ["x" * 33], [""], "parts.v1", None]
)
def test_stream_capability_validation_before_streaming(monkeypatch, capabilities):
    from fastapi.testclient import TestClient

    from app.assistant import routes
    from app.auth import current_user
    from app.database import database_session
    from app.main import create_app

    app = create_app()
    app.state.settings = settings()
    app.state.database_session_factory = MagicMock()
    app.state.generation_provider = Mock()
    app.state.embedding_provider = Mock()
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=1)
    app.dependency_overrides[database_session] = lambda: Mock()
    monkeypatch.setattr(routes, "bind_owner", lambda *args: None)
    monkeypatch.setattr(routes, "_consent_then_release", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        routes,
        "run_assistant",
        lambda **kwargs: AssistantResponse(
            reply="", tool_calls=[], stop_reason="timeout"
        ),
    )
    body = {"messages": [{"role": "user", "content": "hello"}]}
    client = TestClient(
        app
    )  # No lifespan, database, token verifier or external provider.
    valid = client.post(
        "/v1/assistant/messages/stream", json={**body, "capabilities": ["future.x"]}
    )
    assert valid.status_code == 200
    response = client.post(
        "/v1/assistant/messages/stream", json={**body, "capabilities": capabilities}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"
    assert "text/event-stream" not in response.headers["content-type"]
    rejected = client.post("/v1/assistant/messages", json={**body, "capabilities": []})
    assert rejected.status_code == 422
    app.state.generation_provider.generate.assert_not_called()
    app.state.generation_provider.stream.assert_not_called()


@pytest.mark.parametrize(
    "names,purposes",
    [
        (("search_cards",), ["search"]),
        (("get_due_cards", "search_cards"), ["due", "search"]),
    ],
)
def test_parts_search_and_multiple_calls_emitted_in_order(names, purposes):
    async def scenario():
        bodies, _, _ = await capture(names=names)
        parts = [
            json.loads(body.split(b"data: ")[1])
            for body in bodies
            if body.startswith(b"event: part")
        ]
        assert [part["payload"]["purpose"] for part in parts] == purposes
        assert [part["id"] for part in parts] == [
            f"p{i}" for i in range(1, len(parts) + 1)
        ]
        assert all(part["payload"]["items"] == [ITEM] for part in parts)
        assert bodies[len(parts)].startswith(b"event: delta")
        assert (
            sum(body.startswith((b"event: done", b"event: error")) for body in bodies)
            == 1
        )

    asyncio.run(scenario())


@pytest.mark.parametrize("field", ["id", "deck_id", "term", "meaning"])
def test_incomplete_tool_output_keeps_original_model_context_without_part(field):
    item = {key: value for key, value in ITEM.items() if key != field}
    pending = prepared(execute=lambda *args: {"items": [item]})
    assert pending.parts == []
    assert pending.request.contents[-1]["parts"][0]["functionResponse"]["response"] == {
        "items": [item]
    }
