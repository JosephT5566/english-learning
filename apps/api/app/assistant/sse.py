"""Stream the tool-disabled answer after the assistant has released its SQL session."""

import asyncio
import json
import time
from contextlib import aclosing, suppress
from dataclasses import dataclass
from threading import Event

import anyio
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import SQLAlchemyError

from app.assistant.loop import (
    FALLBACK,
    AssistantResponse,
    add_usage,
    emit_run_completed,
    emit_step,
    generation_error,
)
from app.assistant.tools import AssistantDeadlineExceeded
from app.errors import ApiError
from app.generation import GenerationFailure, GenerationUsage

TERMINAL_SEND_GRACE_SECONDS = 0.1


@dataclass(frozen=True)
class _Frame:
    name: str
    data: dict
    outcome: str | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class _Heartbeat:
    preparation: asyncio.Task


class AssistantSSE(StreamingResponse):
    media_type = "text/event-stream"

    def __init__(self, content, *, deadline, request_id, headers=None, status_code=200):
        super().__init__(content, headers=headers, status_code=status_code)
        self.deadline = deadline
        self.request_id = request_id
        self.started_at = time.monotonic()
        self.outcome = "disconnected"
        self.error_code = None

    async def __call__(self, scope, receive, send):
        # ASGI 2.4 may report a disconnect only at the next failed send.
        # Listen even while waiting on a silent model or a planning step.
        try:
            async with anyio.create_task_group() as group:

                async def send_events():
                    try:
                        await self.stream_response(send)
                    except OSError:
                        pass
                    finally:
                        group.cancel_scope.cancel()

                group.start_soon(send_events)
                await self.listen_for_disconnect(receive)
                group.cancel_scope.cancel()
        finally:
            emit_run_completed(
                self.request_id, "sse", self.started_at, self.outcome, self.error_code
            )

    async def stream_response(self, send):
        terminal_started = False
        send_timed_out = False
        try:
            await send(
                {
                    "type": "http.response.start",
                    "status": self.status_code,
                    "headers": self.raw_headers,
                }
            )
            async for frame in self.body_iterator:
                terminal_started = (
                    isinstance(frame, _Frame) and frame.outcome is not None
                )
                remaining = self.deadline - time.monotonic()
                if terminal_started:
                    self.outcome = frame.outcome
                    self.error_code = frame.error_code
                    remaining = max(remaining, TERMINAL_SEND_GRACE_SECONDS)
                elif remaining <= 0:
                    raise TimeoutError
                with anyio.fail_after(remaining):
                    await _send_frame(send, frame)
        except TimeoutError:
            send_timed_out = True
            if not terminal_started:
                self.outcome = "timeout"
        finally:
            # Close upstream even when downstream backpressure suspends a yield.
            with anyio.CancelScope(shield=True):
                await self.body_iterator.aclose()

        with anyio.move_on_after(TERMINAL_SEND_GRACE_SECONDS):
            if send_timed_out and not terminal_started:
                await _send_frame(send, _done(_answer([], "timeout", {})))
            await send({"type": "http.response.body", "body": b"", "more_body": False})


async def _send_frame(send, frame):
    if isinstance(frame, _Heartbeat):
        if frame.preparation.done():
            return
        # Preparation completion must also cancel a comment blocked in send().
        with anyio.CancelScope() as scope:

            async def stop_when_prepared():
                await asyncio.wait({frame.preparation})
                scope.cancel()

            watcher = asyncio.create_task(stop_when_prepared())
            try:
                await send(
                    {
                        "type": "http.response.body",
                        "body": b": ping\n\n",
                        "more_body": True,
                    }
                )
            finally:
                watcher.cancel()
                with anyio.CancelScope(shield=True):
                    with suppress(asyncio.CancelledError):
                        await watcher
        return
    data = json.dumps(frame.data, separators=(",", ":"))
    body = f"event: {frame.name}\ndata: {data}\n\n".encode()
    await send({"type": "http.response.body", "body": body, "more_body": True})


def _done(response, error_code=None):
    return _Frame(
        "done",
        response.model_dump(mode="json", exclude={"reply"}),
        response.stop_reason,
        error_code,
    )


def _answer(tool_calls, stop_reason, totals):
    return AssistantResponse(
        reply="",
        tool_calls=tool_calls,
        stop_reason=stop_reason,
        usage=GenerationUsage(**totals) if totals else None,
    )


def _error(error):
    return _Frame(
        "error",
        {"code": error.code, "message": error.message, "retryable": error.retryable},
        "error",
        error.code,
    )


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError
    return remaining


async def stream_events(
    prepare, provider, settings, deadline, request_id, *, parts_enabled=False
):
    cancelled = Event()
    pending = None
    step_usage = None
    logged_usage = {}
    model_id = None
    status = "disconnected"
    try:
        remaining = _remaining(deadline)
        if settings.assistant_sse_heartbeat_seconds:
            preparation = asyncio.create_task(
                asyncio.wait_for(
                    asyncio.to_thread(prepare, cancelled.is_set), timeout=remaining
                )
            )
            try:
                while True:
                    ready, _ = await asyncio.wait(
                        {preparation},
                        timeout=min(
                            settings.assistant_sse_heartbeat_seconds,
                            _remaining(deadline),
                        ),
                    )
                    if ready:
                        break
                    _remaining(deadline)
                    # Yield comments through the same bounded sender as event frames.
                    yield _Heartbeat(preparation)
                result = preparation.result()
            finally:
                preparation.cancel()
                with anyio.CancelScope(shield=True):
                    await asyncio.gather(preparation, return_exceptions=True)
        else:
            result = await asyncio.wait_for(
                asyncio.to_thread(prepare, cancelled.is_set), timeout=remaining
            )
        if isinstance(result, AssistantResponse):
            if parts_enabled:
                for part in result._parts:
                    yield _Frame("part", part)
            yield _done(result, result._terminal_error_code)
            return

        pending = result
        if parts_enabled:
            for part in pending.parts:
                yield _Frame("part", part)
        has_text = False
        model_id = settings.generation_model
        async with aclosing(
            provider.stream(
                pending.request,
                model=model_id,
                project=settings.vertex_project_id,
                location=settings.effective_generation_location,
                timeout_seconds=settings.generation_timeout_seconds,
                max_output_tokens=settings.assistant_max_output_tokens,
                deadline=deadline,
            )
        ) as chunks:
            while True:
                try:
                    chunk = await asyncio.wait_for(anext(chunks), _remaining(deadline))
                except StopAsyncIteration:
                    _remaining(deadline)
                    break
                _remaining(deadline)
                if chunk.usage is not None:
                    step_usage = chunk.usage
                    # Preserve earlier reported counts in logs without changing the SSE payload.
                    logged_usage.update(step_usage.model_dump(exclude_none=True))
                if chunk.text:
                    has_text = has_text or bool(chunk.text.strip())
                    yield _Frame("delta", {"text": chunk.text})

        status = "completed" if has_text else "max_steps"
        if not has_text:
            yield _Frame("delta", {"text": FALLBACK})
        add_usage(pending.totals, step_usage)
        yield _done(_answer(pending.tool_calls, status, pending.totals))
    except (TimeoutError, GenerationFailure) as failure:
        if isinstance(failure, TimeoutError) or failure.code == "provider_timeout":
            status = "timeout"
            cancelled.set()
            error_code = (
                generation_error(failure).code
                if isinstance(failure, GenerationFailure)
                and not isinstance(failure, AssistantDeadlineExceeded)
                and time.monotonic() < deadline
                else None
            )
            if pending is None:
                yield _done(_answer([], status, {}), error_code)
            else:
                add_usage(pending.totals, step_usage)
                yield _done(
                    _answer(pending.tool_calls, status, pending.totals), error_code
                )
        else:
            error = generation_error(failure)
            status = error.code
            yield _error(error)
    except ApiError as error:
        status = error.code
        yield _error(error)
    except SQLAlchemyError:
        status = "database_unavailable"
        yield _error(
            ApiError(
                status_code=503,
                code=status,
                message="The database is temporarily unavailable.",
                retryable=True,
            )
        )
    except Exception:  # noqa: BLE001 - never expose an exception after headers
        status = "internal_error"
        yield _error(
            ApiError(
                status_code=500, code=status, message="An unexpected error occurred."
            )
        )
    finally:
        cancelled.set()
        if pending is not None:
            emit_step(
                request_id,
                pending.step,
                [],
                status,
                pending.started,
                GenerationUsage(**logged_usage) if step_usage is not None else None,
                model_id,
            )
