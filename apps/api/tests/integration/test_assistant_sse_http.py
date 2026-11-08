"""Exercise the authenticated SSE route against the restricted PostgreSQL fixture."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.generation import GenerationFailure, GenerationResult
from tests.integration import test_assistant_http_boundaries as shared

api_client = shared.api_client
provider = shared.provider
pytestmark = shared.pytestmark
BODY = shared.BODY
HEADERS = shared.HEADERS
PATH = "/v1/assistant/messages/stream"


@pytest.mark.parametrize(
    ("gate", "status", "code"),
    [
        ("auth", 401, "authentication_required"),
        ("input", 422, "validation_failed"),
        ("consent", 403, "genai_consent_required"),
        ("config", 503, "generation_not_configured"),
    ],
)
def test_sse_http_preflight(api_client, provider, gate, status, code):
    if gate == "consent":
        assert (
            api_client.delete("/v1/me/genai-consent", headers=HEADERS).status_code
            == 200
        )
    if gate == "config":
        api_client.app.state.settings = api_client.app.state.settings.model_copy(
            update={"generation_model": None}
        )
    response = api_client.post(
        PATH,
        headers={} if gate == "auth" else HEADERS,
        json={"messages": []} if gate == "input" else BODY,
    )
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    provider.generate.assert_not_called()
    provider.stream.assert_not_called()


async def start_request(app, *, body_gate=None):
    incoming = asyncio.Queue()
    outgoing = asyncio.Queue()
    incoming.put_nowait(
        {"type": "http.request", "body": json.dumps(BODY).encode(), "more_body": False}
    )
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": PATH,
        "raw_path": PATH.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [
            (b"host", b"testserver"),
            (b"content-type", b"application/json"),
            *[(k.lower().encode(), v.encode()) for k, v in HEADERS.items()],
        ],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
    }

    async def send(message):
        if body_gate is not None and message.get("body"):
            await body_gate.wait()
        await outgoing.put(message)

    task = asyncio.create_task(app(scope, incoming.get, send))
    response = await asyncio.wait_for(outgoing.get(), 5)
    assert response["status"] == 200
    assert dict(response["headers"])[b"content-type"].startswith(b"text/event-stream")
    return task, incoming, outgoing


async def read_event(outgoing):
    response = await asyncio.wait_for(outgoing.get(), 5)
    assert response["type"] == "http.response.body"
    event, data = response["body"].decode().strip().splitlines()
    return event.removeprefix("event: "), json.loads(data.removeprefix("data: "))


@pytest.mark.parametrize("disconnect", [False, True])
def test_sse_delivers_text_before_upstream_finishes(api_client, provider, disconnect):
    async def scenario():
        release = asyncio.Event()
        closed = asyncio.Event()

        async def upstream(request, **options):
            assert request.tools_disabled
            try:
                yield SimpleNamespace(text="first", usage=None)
                await release.wait()
                yield SimpleNamespace(text=" second", usage=None)
            finally:
                closed.set()

        provider.generate.return_value = GenerationResult(text="planning text")
        provider.stream = upstream
        task, incoming, outgoing = await start_request(api_client.app)
        assert await read_event(outgoing) == ("delta", {"text": "first"})
        assert not closed.is_set()
        if disconnect:
            incoming.put_nowait({"type": "http.disconnect"})
        else:
            release.set()
            assert await read_event(outgoing) == ("delta", {"text": " second"})
            event, data = await read_event(outgoing)
            assert event == "done"
            assert data == {"tool_calls": [], "stop_reason": "completed", "usage": None}
            end = await asyncio.wait_for(outgoing.get(), 5)
            assert not end["more_body"] and not end["body"]
        await asyncio.wait_for(task, 5)
        await asyncio.wait_for(closed.wait(), 5)
        assert provider.generate.call_count == 1

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("failure", "event", "field", "value"),
    [
        ("provider_timeout", "done", "stop_reason", "timeout"),
        ("provider_unavailable", "error", "code", "generation_provider_unavailable"),
    ],
)
def test_sse_failure_after_delta(api_client, provider, failure, event, field, value):
    async def upstream(request, **options):
        yield SimpleNamespace(text="partial", usage=None)
        raise GenerationFailure(failure)

    provider.stream = upstream
    response = api_client.post(PATH, headers=HEADERS, json=BODY)
    frames = response.text.strip().split("\n\n")
    assert len(frames) == 2
    assert frames[0] == 'event: delta\ndata: {"text":"partial"}'
    header, data = frames[1].splitlines()
    assert header == f"event: {event}"
    assert json.loads(data.removeprefix("data: "))[field] == value


def test_sse_tool_rounds_use_rls_release_connections_and_cap_calls(
    api_client, provider
):
    attacker = shared.bearer("attacker-token")
    assert api_client.put("/v1/me/genai-consent", headers=attacker).status_code == 200
    foreign_filters = {"deck_id": shared.FIXTURE_DECK_ID, "target_language": "en"}
    calls = [
        ("search_cards", {**foreign_filters, "query": "harbor"}),
        ("get_due_cards", foreign_filters),
        ("get_review_stats", foreign_filters),
    ]
    checked_out = api_client.app.state.database_engine.pool.checkedout

    def generate(request, **options):
        assert checked_out() == 0
        assert not request.tools_disabled
        result = shared.tool_result(calls)
        return GenerationResult(
            text="PRIVATE_PLANNING",
            parts=result.parts,
            function_calls=result.function_calls,
        )

    async def upstream(request, **options):
        assert checked_out() == 0
        assert request.tools_disabled
        responses = [
            p["functionResponse"]["response"]
            for turn in request.contents
            for p in turn["parts"]
            if "functionResponse" in p
        ]
        assert (
            responses
            == [
                {"error": "tool_unavailable"},
                {"error": "tool_unavailable"},
                {"total_count": 0, "due_count": 0},
            ]
            * 2
        )
        yield SimpleNamespace(text="No accessible records.", usage=None)

    provider.generate.side_effect = generate
    provider.stream = upstream
    response = api_client.post(PATH, headers=attacker, json=BODY)
    assert response.status_code == 200
    assert provider.generate.call_count == 2
    assert checked_out() == 0
    assert "PRIVATE_PLANNING" not in response.text
    assert "opaque" not in response.text
    assert "total_count" not in response.text
    assert "event: delta" in response.text
    assert response.text.count("event: done") == 1
    assert response.text.count('"status":"ok"') == 2
    api_client.app.state.embedding_provider.query_embedding.assert_not_called()
    with api_client.app.state.database_session_factory() as session:
        from sqlalchemy import text

        assert (
            session.execute(text("SELECT current_user")).scalar_one() == "app_rls_test"
        )


def test_sse_withdrawal_during_planning_prevents_next_provider_call(
    api_client, provider
):
    def generate(request, **options):
        assert (
            api_client.delete("/v1/me/genai-consent", headers=HEADERS).status_code
            == 200
        )
        return GenerationResult(text="Discarded")

    provider.generate.side_effect = generate
    response = api_client.post(PATH, headers=HEADERS, json=BODY)
    assert response.status_code == 200
    assert response.text.count("event: error") == 1
    assert "genai_consent_required" in response.text
    assert "Discarded" not in response.text
    assert provider.generate.call_count == 1
    provider.stream.assert_not_called()


def test_sse_deadline_before_first_delta_closes_upstream(api_client, provider):
    from threading import Event

    closed = Event()

    async def upstream(request, **options):
        try:
            await asyncio.Event().wait()
            yield SimpleNamespace(text="late", usage=None)
        finally:
            closed.set()

    api_client.app.state.settings = api_client.app.state.settings.model_copy(
        update={"assistant_max_steps": 1, "assistant_timeout_seconds": 1}
    )
    provider.stream = upstream
    response = api_client.post(PATH, headers=HEADERS, json=BODY)
    assert response.status_code == 200
    assert closed.is_set()
    assert response.text.count("event: done") == 1
    assert '"stop_reason":"timeout"' in response.text
    assert "event: delta" not in response.text
    provider.generate.assert_not_called()


def test_sse_disconnect_while_planning_starts_no_more_work(api_client, provider):
    from threading import Event

    started, release, finished = Event(), Event(), Event()
    observed = []

    def generate(request, *, cancelled, **options):
        started.set()
        try:
            assert release.wait(5)
            observed.append(cancelled())
            return shared.tool_result([("get_review_stats", {})])
        finally:
            finished.set()

    async def scenario():
        task, incoming, outgoing = await start_request(api_client.app)
        try:
            assert await asyncio.to_thread(started.wait, 5)
            incoming.put_nowait({"type": "http.disconnect"})
            await asyncio.wait_for(task, 5)
            # Middleware may finish the response with an empty ASGI body message.
            while not outgoing.empty():
                assert not outgoing.get_nowait()["body"]
        finally:
            release.set()
        assert await asyncio.to_thread(finished.wait, 5)

    provider.generate.side_effect = generate
    asyncio.run(scenario())
    assert observed == [True]
    assert provider.generate.call_count == 1
    provider.stream.assert_not_called()


def test_sse_slow_client_cannot_hold_upstream_past_deadline(api_client, provider):
    async def scenario():
        closed = asyncio.Event()
        body_gate = asyncio.Event()

        async def upstream(request, **options):
            try:
                for text in ("first", "second", "third"):
                    yield SimpleNamespace(text=text, usage=None)
                await asyncio.Event().wait()
            finally:
                closed.set()

        api_client.app.state.settings = api_client.app.state.settings.model_copy(
            update={"assistant_max_steps": 1, "assistant_timeout_seconds": 1}
        )
        provider.stream = upstream
        task, _, _ = await start_request(api_client.app, body_gate=body_gate)
        try:
            await asyncio.wait_for(closed.wait(), 2)
        finally:
            body_gate.set()
            await asyncio.wait_for(task, 5)

    asyncio.run(scenario())
