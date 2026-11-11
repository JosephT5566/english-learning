"""Exercise the authenticated SSE route against the restricted PostgreSQL fixture."""

import asyncio
import json
from itertools import pairwise
from types import SimpleNamespace

import pytest

from app.generation import GenerationFailure, GenerationResult, GenerationUsage
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
def test_sse_http_preflight(api_client, provider, gate, status, code, capsys):
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
    assert not shared.log_events(capsys.readouterr().out, "assistant_run_completed")


async def start_request(app, *, body_gate=None, response_headers=None):
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
    headers = dict(response["headers"])
    assert headers[b"content-type"].startswith(b"text/event-stream")
    if response_headers is not None:
        response_headers.update(headers)
    return task, incoming, outgoing


async def read_event(outgoing):
    response = await asyncio.wait_for(outgoing.get(), 5)
    assert response["type"] == "http.response.body"
    event, data = response["body"].decode().strip().splitlines()
    return event.removeprefix("event: "), json.loads(data.removeprefix("data: "))


@pytest.mark.parametrize("disconnect", [False, True])
def test_sse_delivers_text_before_upstream_finishes(
    api_client, provider, disconnect, capsys
):
    response_headers = {}

    async def scenario():
        release = asyncio.Event()
        closed = asyncio.Event()

        async def upstream(request, **options):
            assert request.tools_disabled
            try:
                yield SimpleNamespace(
                    text="first", usage=GenerationUsage(output_tokens=0)
                )
                await release.wait()
                yield SimpleNamespace(text=" second", usage=None)
            finally:
                closed.set()

        provider.generate.return_value = GenerationResult(text="planning text")
        provider.stream = upstream
        task, incoming, outgoing = await start_request(
            api_client.app, response_headers=response_headers
        )
        assert await read_event(outgoing) == ("delta", {"text": "first"})
        assert not closed.is_set()
        if disconnect:
            incoming.put_nowait({"type": "http.disconnect"})
        else:
            release.set()
            assert await read_event(outgoing) == ("delta", {"text": " second"})
            event, data = await read_event(outgoing)
            assert event == "done"
            assert data == {
                "tool_calls": [],
                "stop_reason": "completed",
                "usage": {
                    "input_tokens": None,
                    "output_tokens": 0,
                    "total_tokens": None,
                },
            }
            end = await asyncio.wait_for(outgoing.get(), 5)
            assert not end["more_body"] and not end["body"]
        await asyncio.wait_for(task, 5)
        await asyncio.wait_for(closed.wait(), 5)
        assert provider.generate.call_count == 1

    capsys.readouterr()
    asyncio.run(scenario())
    output = capsys.readouterr().out
    request_id = response_headers[b"x-request-id"].decode()
    shared.assert_run_event(
        output, request_id, "sse", "disconnected" if disconnect else "completed"
    )
    steps = shared.log_events(output, "assistant_step")
    assert [step["step"] for step in steps] == [1, 2]
    assert all(
        step["model_id"] == "fake-v1" and step["request_id"] == request_id
        for step in steps
    )
    assert steps[1]["usage"] == {
        "input_tokens": None,
        "output_tokens": 0,
        "total_tokens": None,
    }
    assert "PRIVATE_" not in output


def test_sse_step_log_preserves_split_usage(api_client, provider, capsys):
    async def upstream(request, **options):
        yield SimpleNamespace(text="first", usage=GenerationUsage(input_tokens=0))
        yield SimpleNamespace(text=" second", usage=GenerationUsage(output_tokens=2))

    provider.generate.return_value = GenerationResult(text="planning text")
    provider.stream = upstream
    response = api_client.post(PATH, headers=HEADERS, json=BODY)

    assert response.status_code == 200
    event, data = response.text.strip().split("\n\n")[-1].splitlines()
    assert event == "event: done"
    assert json.loads(data.removeprefix("data: "))["usage"] == {
        "input_tokens": None,
        "output_tokens": 2,
        "total_tokens": None,
    }
    steps = shared.log_events(capsys.readouterr().out, "assistant_step")
    assert [step["step"] for step in steps] == [1, 2]
    assert steps[-1]["request_id"] == response.headers["X-Request-ID"]
    assert steps[-1]["usage"] == {
        "input_tokens": 0,
        "output_tokens": 2,
        "total_tokens": None,
    }


@pytest.mark.parametrize(
    ("failure", "event", "field", "value"),
    [
        ("provider_timeout", "done", "stop_reason", "timeout"),
        ("provider_unavailable", "error", "code", "generation_provider_unavailable"),
    ],
)
def test_sse_failure_after_delta(
    api_client, provider, failure, event, field, value, capsys
):
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
    shared.assert_run_event(
        capsys.readouterr().out,
        response.headers["X-Request-ID"],
        "sse",
        "timeout" if event == "done" else "error",
        f"generation_{failure}",
    )


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


@pytest.mark.parametrize("path", [shared.PATH, PATH])
def test_assistant_logging_sink_failure_keeps_response(
    api_client, provider, monkeypatch, path
):
    from app import request_context

    async def upstream(request, **options):
        yield SimpleNamespace(text="finished", usage=None)

    provider.stream = upstream
    attempted = []

    def fail_assistant_log(value, **options):
        event = json.loads(value)["event"]
        attempted.append(event)
        raise OSError("PRIVATE_LOG_SINK")

    monkeypatch.setattr(request_context, "print", fail_assistant_log, raising=False)
    response = api_client.post(path, headers=HEADERS, json=BODY)
    assert response.status_code == 200
    if path == PATH:
        assert response.text.count("event: done") == 1
        assert '"stop_reason":"completed"' in response.text
    else:
        assert response.json()["stop_reason"] == "completed"
    assert attempted.count("assistant_run_completed") == 1


@pytest.mark.parametrize("stage", ["planning", "tool"])
def test_sse_early_provider_timeout_logs_stable_code(
    api_client, provider, capsys, monkeypatch, stage
):
    if stage == "planning":
        provider.generate.side_effect = GenerationFailure("provider_timeout")
    else:
        from app.assistant import tools

        def timeout(*args, **kwargs):
            raise GenerationFailure("provider_timeout")

        provider.generate.return_value = shared.tool_result([("get_review_stats", {})])
        monkeypatch.setattr(tools, "get_review_stats", timeout)

    response = api_client.post(PATH, headers=HEADERS, json=BODY)
    assert response.status_code == 200
    event, data = response.text.strip().splitlines()
    assert event == "event: done"
    assert json.loads(data.removeprefix("data: ")) == {
        "tool_calls": [],
        "stop_reason": "timeout",
        "usage": None,
    }
    provider.stream.assert_not_called()
    shared.assert_run_event(
        capsys.readouterr().out,
        response.headers["X-Request-ID"],
        "sse",
        "timeout",
        "generation_provider_timeout",
    )


class HeartbeatHarness:
    """Run the real response with fake planning, upstream and ASGI transport."""

    def __init__(self, *, interval=1, timeout=None, delay=2.6, mode="delta"):
        import time
        from threading import Event

        from app.assistant.loop import AssistantResponse
        from app.assistant.sse import AssistantSSE, stream_events
        from app.config import Settings

        changes = {"assistant_sse_heartbeat_seconds": interval}
        if timeout is not None:
            changes["assistant_timeout_seconds"] = timeout
        self.settings = Settings(_env_file=None, **changes)
        self.release = Event()
        self.finished = Event()
        self.observed = []
        self.messages = []
        self.incoming = asyncio.Queue()
        self.body_gate = None
        self.sending = False
        self.closed = False
        self.started = time.monotonic()
        self.deadline = self.started + self.settings.assistant_timeout_seconds

        def prepare(cancelled):
            try:
                self.release.wait(delay)
                self.observed.append(cancelled())
                if mode == "error":
                    raise GenerationFailure("invalid_response")
                if mode == "done":
                    return AssistantResponse(
                        reply="", tool_calls=[], stop_reason="max_steps"
                    )
                return SimpleNamespace(
                    request=object(),
                    totals={},
                    tool_calls=[],
                    step=1,
                    started=self.started,
                )
            finally:
                self.prepared_at = time.monotonic()
                self.finished.set()

        async def upstream(*args, **kwargs):
            try:
                if mode == "slow_first":
                    await asyncio.sleep(2.2)
                yield SimpleNamespace(text="first", usage=None)
                if mode == "slow_second":
                    await asyncio.sleep(2.2)
                    yield SimpleNamespace(text="second", usage=None)
            finally:
                self.closed = True

        self.response = AssistantSSE(
            stream_events(
                prepare,
                SimpleNamespace(stream=upstream),
                self.settings,
                self.deadline,
                "heartbeat-test",
            ),
            deadline=self.deadline,
            request_id="heartbeat-test",
        )
        self.task = None

    async def send(self, message):
        import time

        assert not self.sending, "ASGI sends must not overlap"
        self.sending = True
        try:
            if self.body_gate is not None and message.get("body"):
                await self.body_gate.wait()
            self.messages.append((time.monotonic(), message.copy()))
        finally:
            self.sending = False

    def start(self):
        self.task = asyncio.create_task(self.response({}, self.incoming.get, self.send))

    async def finish(self, limit=8):
        try:
            await asyncio.wait_for(self.task, limit)
        finally:
            self.release.set()
            assert await asyncio.to_thread(self.finished.wait, 2)

    def bodies(self):
        return [
            (stamp, message["body"])
            for stamp, message in self.messages
            if message.get("body")
        ]

    def events(self):
        return [body for _, body in self.bodies() if not body.startswith(b":")]

    def pings(self):
        return [stamp for stamp, body in self.bodies() if body == b": ping\n\n"]


@pytest.mark.parametrize("mode", ["delta", "error"])
def test_sse_heartbeat_during_slow_prepare(mode):
    async def scenario():
        active = HeartbeatHarness(mode=mode)
        active.start()
        await active.finish()
        disabled = HeartbeatHarness(interval=0, mode=mode)
        disabled.start()
        await disabled.finish()
        assert len(active.pings()) >= 2
        stamps = [active.messages[0][0], *active.pings()]
        assert all(right - left >= 0.98 for left, right in pairwise(stamps))
        bodies = [body for _, body in active.bodies()]
        assert bodies[: len(active.pings())] == [b": ping\n\n"] * len(active.pings())
        assert active.events() == disabled.events()
        assert (
            sum(
                body.startswith((b"event: done", b"event: error"))
                for body in active.events()
            )
            == 1
        )
        assert all(
            message["more_body"]
            for _, message in active.messages
            if message.get("body")
        )

    asyncio.run(scenario())


def test_sse_heartbeat_disabled_when_zero():
    async def scenario():
        harness = HeartbeatHarness(interval=0)
        harness.start()
        await harness.finish()
        assert not harness.pings()
        assert harness.bodies()[0][1] == b'event: delta\ndata: {"text":"first"}\n\n'

    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["slow_second", "done", "error", "slow_first"])
def test_sse_no_heartbeat_after_first_event(mode):
    async def scenario():
        harness = HeartbeatHarness(mode=mode)
        harness.start()
        await harness.finish()
        count = len(harness.messages)
        await asyncio.sleep(2.2 if mode in ("done", "error") else 0)
        assert len(harness.messages) == count
        assert len(harness.pings()) >= 2
        assert all(stamp < harness.prepared_at for stamp in harness.pings())
        if mode in ("done", "error"):
            assert len(harness.events()) == 1
            assert harness.messages[-2][1]["body"] == harness.events()[0]
        first = next(
            index
            for index, (_, body) in enumerate(harness.bodies())
            if body.startswith(b"event:")
        )
        assert all(not body.startswith(b":") for _, body in harness.bodies()[first:])
        assert harness.events()[0].startswith(
            b"event: "
            + (b"done" if mode == "done" else b"error" if mode == "error" else b"delta")
        )
        assert harness.messages[-1][1] == {
            "type": "http.response.body",
            "body": b"",
            "more_body": False,
        }

    asyncio.run(scenario())


def test_sse_no_heartbeat_when_prepare_is_fast():
    async def scenario():
        harness = HeartbeatHarness(interval=15, delay=0)
        harness.start()
        await harness.finish()
        assert harness.settings.assistant_sse_heartbeat_seconds == 15
        assert [body for _, body in harness.bodies()] == [
            b'event: delta\ndata: {"text":"first"}\n\n',
            b'event: done\ndata: {"tool_calls":[],"stop_reason":"completed","usage":null}\n\n',
        ]

    asyncio.run(scenario())


def test_sse_heartbeat_stops_at_deadline():
    async def scenario():
        harness = HeartbeatHarness(timeout=1, delay=60)
        harness.start()
        await harness.finish(limit=2)
        assert harness.messages[-1][0] - harness.started < 2
        assert all(stamp < harness.deadline for stamp in harness.pings())
        assert harness.events() == [
            b'event: done\ndata: {"tool_calls":[],"stop_reason":"timeout","usage":null}\n\n'
        ]
        assert harness.observed == [True]

    asyncio.run(scenario())


def test_sse_default_deadline_times_out_before_cloud_run_cap():
    async def scenario():
        harness = HeartbeatHarness(delay=120)
        harness.start()
        await harness.finish(limit=29.5)
        assert harness.settings.assistant_timeout_seconds == 25
        assert 25 <= harness.messages[-1][0] - harness.started < 30
        assert harness.events() == [
            b'event: done\ndata: {"tool_calls":[],"stop_reason":"timeout","usage":null}\n\n'
        ]

    asyncio.run(scenario())


def test_sse_disconnect_stops_heartbeat():
    async def scenario():
        import time

        before = asyncio.all_tasks()
        harness = HeartbeatHarness(delay=60)
        harness.start()
        try:
            await asyncio.sleep(1.2)
            assert harness.pings()
        finally:
            disconnected = time.monotonic()
            harness.incoming.put_nowait({"type": "http.disconnect"})
            await harness.finish()
        assert harness.observed == [True]
        assert all(stamp < disconnected for stamp, _ in harness.bodies())
        assert asyncio.all_tasks() <= before

    asyncio.run(scenario())


def test_sse_heartbeat_backpressure_stops_at_deadline():
    async def scenario():
        harness = HeartbeatHarness(timeout=2, delay=60)
        harness.body_gate = asyncio.Event()
        harness.start()
        await harness.finish(limit=3)
        assert not harness.bodies()
        assert harness.observed == [True]
        assert not harness.closed
        assert harness.messages[-1][0] - harness.started < 3

    asyncio.run(scenario())


def test_sse_heartbeat_blocked_send_stops_when_prepare_finishes():
    async def scenario():
        harness = HeartbeatHarness(delay=1.2)
        harness.body_gate = asyncio.Event()
        harness.start()
        try:
            assert await asyncio.to_thread(harness.finished.wait, 2)
            await asyncio.sleep(0.1)
        finally:
            harness.body_gate.set()
            await harness.finish()
        assert not harness.pings()
        assert harness.events()[0] == b'event: delta\ndata: {"text":"first"}\n\n'

    asyncio.run(scenario())


def test_sse_parts_legacy_bytes_and_negotiated_due(api_client, provider, monkeypatch):
    from app.assistant import loop

    # Make wire comparisons independent of machine timing while preserving the field.
    monkeypatch.setattr(loop, "round", lambda value: 0, raising=False)
    api_client.app.state.settings = api_client.app.state.settings.model_copy(
        update={"assistant_max_steps": 2, "assistant_sse_heartbeat_seconds": 0}
    )
    provider.generate.return_value = shared.tool_result(
        [("get_due_cards", {"target_language": "en"})]
    )

    async def upstream(request, **options):
        yield SimpleNamespace(text="Review harbor.", usage=None)

    provider.stream = upstream
    baseline = api_client.post(PATH, headers=HEADERS, json=BODY)
    assert baseline.status_code == 200
    assert b"event: part" not in baseline.content
    for capabilities in ([], ["future.x"]):
        response = api_client.post(
            PATH, headers=HEADERS, json={**BODY, "capabilities": capabilities}
        )
        assert response.status_code == 200
        assert response.content == baseline.content
    response = api_client.post(
        PATH, headers=HEADERS, json={**BODY, "capabilities": ["parts.v1"]}
    )
    assert response.status_code == 200
    frames = response.content.split(b"\n\n")
    assert frames[0].startswith(b"event: part\n")
    part = json.loads(frames[0].split(b"data: ")[1])
    assert part["id"] == "p1"
    assert part["type"] == "card_list"
    assert part["payload"]["purpose"] == "due"
    assert part["payload"]["items"]
    assert all(
        set(item) == {"id", "deck_id", "term", "meaning"}
        for item in part["payload"]["items"]
    )
    assert b"\n\n".join(frames[1:]) == baseline.content
    done = json.loads(baseline.content.split(b"event: done\ndata: ")[1])
    assert set(done) == {"tool_calls", "stop_reason", "usage"}
    assert done["stop_reason"] == "completed"


def test_sse_legacy_due_wire_regression(api_client, provider, monkeypatch):
    from app.assistant import loop

    monkeypatch.setattr(loop, "round", lambda value: 0, raising=False)
    api_client.app.state.settings = api_client.app.state.settings.model_copy(
        update={"assistant_max_steps": 2, "assistant_sse_heartbeat_seconds": 0}
    )
    provider.generate.return_value = shared.tool_result(
        [("get_due_cards", {"target_language": "en"})]
    )

    async def upstream(request, **options):
        yield SimpleNamespace(text="Review harbor.", usage=None)

    provider.stream = upstream
    response = api_client.post(PATH, headers=HEADERS, json=BODY)
    assert response.status_code == 200
    assert response.content == (
        b'event: delta\ndata: {"text":"Review harbor."}\n\n'
        b'event: done\ndata: {"tool_calls":[{"name":"get_due_cards","arguments":{"target_language":"en","limit":5},"status":"ok","duration_ms":0}],"stop_reason":"completed","usage":null}\n\n'
    )


@pytest.mark.parametrize("disconnect", [False, True])
def test_sse_http_blocked_part_deadline_and_disconnect(
    api_client, provider, disconnect
):
    import time
    from unittest.mock import Mock

    from app.assistant.sse import TERMINAL_SEND_GRACE_SECONDS

    api_client.app.state.settings = api_client.app.state.settings.model_copy(
        update={
            "assistant_max_steps": 2,
            "assistant_timeout_seconds": 1,
            "assistant_sse_heartbeat_seconds": 0,
        }
    )
    provider.generate.return_value = shared.tool_result(
        [("get_due_cards", {"target_language": "en"})]
    )
    provider.stream = Mock()

    async def scenario():
        incoming = asyncio.Queue()
        incoming.put_nowait(
            {
                "type": "http.request",
                "body": json.dumps({**BODY, "capabilities": ["parts.v1"]}).encode(),
                "more_body": False,
            }
        )
        messages = []
        blocked = asyncio.Event()
        write_cancelled = asyncio.Event()
        started = time.monotonic()

        async def send(message):
            if message.get("body", b"").startswith(b"event: part"):
                blocked.set()
                if disconnect:
                    incoming.put_nowait({"type": "http.disconnect"})
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    write_cancelled.set()
                    raise
            messages.append(message.copy())

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
        await asyncio.wait_for(api_client.app(scope, incoming.get, send), 2)
        assert blocked.is_set()
        assert write_cancelled.is_set()
        assert time.monotonic() - started <= 1 + TERMINAL_SEND_GRACE_SECONDS + 0.2
        bodies = [m["body"] for m in messages if m["type"] == "http.response.body"]
        assert not any(b"event: part" in body for body in bodies)
        if not disconnect:
            assert len(bodies) == 2
            assert bodies[0].startswith(b"event: done\n")
            assert json.loads(bodies[0].split(b"data: ")[1])["stop_reason"] == "timeout"
            assert messages[-1] == {
                "type": "http.response.body",
                "body": b"",
                "more_body": False,
            }
        provider.stream.assert_not_called()

    asyncio.run(scenario())
