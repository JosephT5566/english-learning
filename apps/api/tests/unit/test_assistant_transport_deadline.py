"""Exercise SSE cancellation through the application's real middleware stack."""

import asyncio
import json
import time
from types import SimpleNamespace

import pytest
from fastapi import Request

from app.assistant.sse import (
    TERMINAL_SEND_GRACE_SECONDS,
    AssistantSSE,
    stream_events,
)
from app.config import Settings
from app.main import create_app


@pytest.mark.parametrize("mode", ["heartbeat", "disabled", "delta", "part"])
def test_app_transport_write_keeps_terminal_event_within_deadline(mode):
    async def scenario():
        app = create_app()
        settings = Settings(
            _env_file=None,
            assistant_sse_heartbeat_seconds=1 if mode == "heartbeat" else 0,
            assistant_timeout_seconds=2,
        )
        app.state.settings = settings
        incoming = asyncio.Queue()
        messages = []
        blocked = asyncio.Event()
        write_cancelled = asyncio.Event()
        upstream_closed = asyncio.Event()
        started = time.monotonic()
        deadline = started + settings.assistant_timeout_seconds

        def prepare(cancelled):
            time.sleep(1.2 if mode != "delta" else 0)
            return SimpleNamespace(
                request=object(),
                totals={},
                tool_calls=[],
                step=1,
                started=started,
                **(
                    {
                        "parts": [
                            {
                                "id": "p1",
                                "type": "card_list",
                                "payload": {"purpose": "due", "items": []},
                            }
                        ]
                    }
                    if mode == "part"
                    else {}
                ),
            )

        async def upstream(*args, **kwargs):
            try:
                yield SimpleNamespace(text="first", usage=None)
            finally:
                upstream_closed.set()

        @app.get("/test-assistant-stream")
        async def endpoint(request: Request):
            return AssistantSSE(
                stream_events(
                    prepare,
                    SimpleNamespace(stream=upstream),
                    settings,
                    deadline,
                    str(request.state.request_id),
                    **({"parts_enabled": True} if mode == "part" else {}),
                ),
                deadline=deadline,
                request_id=str(request.state.request_id),
            )

        async def send(message):
            body = message.get("body", b"")
            if (
                body == b": ping\n\n"
                or body.startswith(b"event: delta")
                and mode == "delta"
                or body.startswith(b"event: part")
                and mode == "part"
            ):
                blocked.set()
                try:
                    # Release only after the deadline, unless the actual writer is cancelled.
                    await asyncio.sleep(max(0, deadline + 0.25 - time.monotonic()))
                except asyncio.CancelledError:
                    write_cancelled.set()
                    raise
            messages.append((time.monotonic(), message.copy()))

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/test-assistant-stream",
            "raw_path": b"/test-assistant-stream",
            "query_string": b"",
            "root_path": "",
            "headers": [(b"origin", b"http://localhost:5173")],
            "client": ("127.0.0.1", 12345),
            "server": ("test", 80),
        }
        # No lifespan: the synthetic route uses neither SQL nor a model provider.
        await asyncio.wait_for(app(scope, incoming.get, send), 3)
        bodies = [message.get("body", b"") for _, message in messages]
        terminal = [
            body
            for body in bodies
            if body.startswith((b"event: done\n", b"event: error\n"))
        ]
        assert len(terminal) == 1, bodies
        payload = json.loads(terminal[0].split(b"data: ", 1)[1])
        assert payload["stop_reason"] == (
            "timeout" if mode in ("delta", "part") else "completed"
        )
        assert messages[-1][1] == {
            "type": "http.response.body",
            "body": b"",
            "more_body": False,
        }
        assert messages[-1][0] <= deadline + TERMINAL_SEND_GRACE_SECONDS + 0.1
        if mode == "part":
            assert not upstream_closed.is_set()
        else:
            assert upstream_closed.is_set()
        assert b"x-request-id" in dict(messages[0][1]["headers"])
        if mode == "disabled":
            assert not blocked.is_set()
        else:
            assert blocked.is_set()
            assert write_cancelled.is_set()
            assert b": ping\n\n" not in bodies

    asyncio.run(scenario())
