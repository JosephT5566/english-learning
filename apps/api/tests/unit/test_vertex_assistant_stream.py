import asyncio
import json
from contextlib import aclosing
from threading import Event

import anyio
import httpx
import pytest

from app.generation import (
    GenerationFailure,
    GenerationRequest,
    VertexGenerationProvider,
)

REQUEST = GenerationRequest(
    system="Test",
    data={},
    contents=[{"role": "user", "parts": [{"text": "Synthetic prompt"}]}],
    tools=[],
    tools_disabled=True,
)
OPTIONS = {
    "model": "model-test",
    "project": "project-test",
    "location": "global",
    "timeout_seconds": 5,
    "max_output_tokens": 20,
}


def event(*, parts=None, finish=None, usage=None):
    candidate = {}
    if parts is not None:
        candidate["content"] = {"role": "model", "parts": parts}
    if finish is not None:
        candidate["finishReason"] = finish
    payload = {"candidates": [candidate], "modelVersion": "model-test"}
    if usage is not None:
        payload["usageMetadata"] = {"candidatesTokenCount": usage}
    return b"data: " + json.dumps(payload).encode() + b"\r\n\r\n"


class ScriptedStream(httpx.AsyncByteStream):
    def __init__(self, first, rest=b""):
        self.first = first
        self.rest = rest
        self.closed = False
        self.release = asyncio.Event()

    async def __aiter__(self):
        yield self.first[:12]
        yield self.first[12:]
        await self.release.wait()
        if self.rest:
            yield self.rest

    async def aclose(self):
        self.closed = True


def provider_for(monkeypatch, stream, status=200):
    async_client = httpx.AsyncClient
    sent = []

    def handle(request):
        sent.append(request)
        return httpx.Response(
            status,
            headers={"Content-Type": "text/event-stream"},
            stream=stream,
        )

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda: async_client(transport=httpx.MockTransport(handle)),
    )
    provider = VertexGenerationProvider()
    monkeypatch.setattr(provider, "_access_token", lambda: "test-token")
    return provider, sent


def test_text_is_available_before_stop_and_private_parts_stay_private(monkeypatch):
    async def run():
        source = ScriptedStream(
            event(
                parts=[
                    {"text": "PRIVATE", "thought": True, "thoughtSignature": "opaque"},
                    {"text": "First"},
                ]
            ),
            event(parts=[{"text": " second"}], finish="STOP", usage=2),
        )
        provider, sent = provider_for(monkeypatch, source)
        async with aclosing(
            provider.stream(
                REQUEST, deadline=asyncio.get_running_loop().time() + 5, **OPTIONS
            )
        ) as chunks:
            first = await anext(chunks)
            assert first.text == "First"
            assert not source.closed
            assert not source.release.is_set()
            source.release.set()
            remaining = [chunk async for chunk in chunks]
        assert "".join(chunk.text for chunk in remaining) == " second"
        assert remaining[-1].usage.output_tokens == 2
        assert source.closed
        assert str(sent[0].url).endswith(":streamGenerateContent?alt=sse")
        assert (
            json.loads(sent[0].content)["toolConfig"]["functionCallingConfig"]["mode"]
            == "NONE"
        )
        assert sent[0].headers["authorization"] == "Bearer test-token"

    asyncio.run(run())


@pytest.mark.parametrize(
    "tail,code",
    [
        (b"", "invalid_response"),
        (b"data: not json\n\n", "invalid_response"),
        (event(parts=[{"functionCall": {"name": "search_cards"}}]), "invalid_response"),
        (event(finish="MAX_TOKENS"), "truncated_output"),
        (event(finish="SAFETY"), "invalid_response"),
        (event(finish="STOP", usage=21), "truncated_output"),
    ],
)
def test_stream_rejects_invalid_finish_and_tool_parts(monkeypatch, tail, code):
    async def run():
        source = ScriptedStream(event(parts=[{"text": "first"}]), tail)
        source.release.set()
        provider, _ = provider_for(monkeypatch, source)
        with pytest.raises(GenerationFailure) as caught:
            async for _ in provider.stream(
                REQUEST, deadline=asyncio.get_running_loop().time() + 5, **OPTIONS
            ):
                pass
        assert caught.value.code == code
        assert source.closed

    asyncio.run(run())


def test_cancelled_stream_closes_blocked_http_body(monkeypatch):
    async def run():
        source = ScriptedStream(event(parts=[{"text": "first"}]))
        provider, _ = provider_for(monkeypatch, source)
        first_seen = asyncio.Event()

        async def consume():
            async with aclosing(
                provider.stream(
                    REQUEST, deadline=asyncio.get_running_loop().time() + 5, **OPTIONS
                )
            ) as chunks:
                async for chunk in chunks:
                    assert chunk.text == "first"
                    first_seen.set()

        task = asyncio.create_task(consume())
        try:
            await asyncio.wait_for(first_seen.wait(), timeout=1)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert source.closed

    asyncio.run(run())


def test_cancelled_sync_planning_during_credentials_never_posts(monkeypatch):
    cancelled = Event()
    provider = VertexGenerationProvider()

    def get_token():
        cancelled.set()
        return "test-token"

    def post(*args, **kwargs):
        pytest.fail("Vertex POST started after the caller cancelled")

    monkeypatch.setattr(provider, "_access_token", get_token)
    monkeypatch.setattr("app.generation.requests.post", post)
    with pytest.raises(GenerationFailure) as caught:
        provider.generate(REQUEST, cancelled=cancelled.is_set, **OPTIONS)
    assert caught.value.code == "provider_timeout"


def test_stream_rechecks_deadline_before_reading_next_event(monkeypatch):
    async def run():
        from types import SimpleNamespace

        clock = SimpleNamespace(monotonic=lambda: 100.0)
        monkeypatch.setattr("app.generation.time", clock)
        source = ScriptedStream(event(parts=[{"text": "first"}]))
        provider, _ = provider_for(monkeypatch, source)
        async with aclosing(
            provider.stream(REQUEST, deadline=104.0, **OPTIONS)
        ) as chunks:
            assert (await anext(chunks)).text == "first"
            clock.monotonic = lambda: 104.0
            with pytest.raises(GenerationFailure) as caught:
                await anext(chunks)
            assert caught.value.code == "provider_timeout"
        assert source.closed

    asyncio.run(run())


def test_cancelled_stream_during_credentials_never_posts(monkeypatch):
    async def run():
        source = ScriptedStream(b"")
        provider, sent = provider_for(monkeypatch, source)
        loop = asyncio.get_running_loop()
        started = asyncio.Event()
        release = Event()

        def get_token():
            loop.call_soon_threadsafe(started.set)
            assert release.wait(5)
            return "test-token"

        monkeypatch.setattr(provider, "_access_token", get_token)
        async with aclosing(
            provider.stream(REQUEST, deadline=loop.time() + 5, **OPTIONS)
        ) as chunks:
            task = asyncio.create_task(anext(chunks))
            try:
                await asyncio.wait_for(started.wait(), timeout=1)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            finally:
                release.set()
        assert not sent

    asyncio.run(run())


def test_level_cancellation_completes_http_close(monkeypatch):
    class CheckpointClose(ScriptedStream):
        async def aclose(self):
            await asyncio.sleep(0)
            await super().aclose()

    async def run():
        source = CheckpointClose(event(parts=[{"text": "first"}]))
        provider, _ = provider_for(monkeypatch, source)
        first_seen = asyncio.Event()

        async def consume():
            async for chunk in provider.stream(
                REQUEST, deadline=asyncio.get_running_loop().time() + 5, **OPTIONS
            ):
                assert chunk.text == "first"
                first_seen.set()

        async with anyio.create_task_group() as group:
            group.start_soon(consume)
            await asyncio.wait_for(first_seen.wait(), 1)
            group.cancel_scope.cancel()
        assert source.closed

    asyncio.run(run())
