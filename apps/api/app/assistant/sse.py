"""Stream the tool-disabled answer after the assistant has released its SQL session."""

import asyncio
import json
import time
from contextlib import aclosing
from threading import Event

import anyio
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import SQLAlchemyError

from app.assistant.loop import (
    FALLBACK,
    AssistantResponse,
    _emit,
    add_usage,
    generation_error,
)
from app.errors import ApiError
from app.generation import GenerationFailure, GenerationUsage

TERMINAL_SEND_GRACE_SECONDS = 0.1


class AssistantSSE(StreamingResponse):
    media_type = "text/event-stream"

    def __init__(self, content, *, deadline, headers=None, status_code=200):
        super().__init__(content, headers=headers, status_code=status_code)
        self.deadline = deadline

    async def __call__(self, scope, receive, send):
        # ASGI 2.4 may report a disconnect only at the next failed send.
        # Listen even while waiting on a silent model or a planning step.
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
                terminal_started = not frame.startswith("event: delta\n")
                remaining = self.deadline - time.monotonic()
                if terminal_started:
                    remaining = max(remaining, TERMINAL_SEND_GRACE_SECONDS)
                elif remaining <= 0:
                    raise TimeoutError
                with anyio.fail_after(remaining):
                    await _send_frame(send, frame)
        except TimeoutError:
            send_timed_out = True
        finally:
            # Close upstream even when downstream backpressure suspends a yield.
            with anyio.CancelScope(shield=True):
                await self.body_iterator.aclose()

        with anyio.move_on_after(TERMINAL_SEND_GRACE_SECONDS):
            if send_timed_out and not terminal_started:
                await _send_frame(send, _done([], "timeout", {}))
            await send({"type": "http.response.body", "body": b"", "more_body": False})


async def _send_frame(send, frame):
    await send(
        {"type": "http.response.body", "body": frame.encode(), "more_body": True}
    )


def _event(name, data):
    return f"event: {name}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


def _done(tool_calls, stop_reason, totals):
    response = AssistantResponse(
        reply="",
        tool_calls=tool_calls,
        stop_reason=stop_reason,
        usage=GenerationUsage(**totals) if totals else None,
    )
    return _event("done", response.model_dump(mode="json", exclude={"reply"}))


def _error(error):
    return _event(
        "error",
        {"code": error.code, "message": error.message, "retryable": error.retryable},
    )


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError
    return remaining


async def stream_events(prepare, provider, settings, deadline, request_id):
    cancelled = Event()
    pending = None
    step_usage = None
    status = "disconnected"
    try:
        remaining = _remaining(deadline)
        result = await asyncio.wait_for(
            asyncio.to_thread(prepare, cancelled.is_set), timeout=remaining
        )
        if isinstance(result, AssistantResponse):
            yield _event("done", result.model_dump(mode="json", exclude={"reply"}))
            return

        pending = result
        has_text = False
        async with aclosing(
            provider.stream(
                pending.request,
                model=settings.generation_model,
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
                if chunk.text:
                    has_text = has_text or bool(chunk.text.strip())
                    yield _event("delta", {"text": chunk.text})

        status = "completed" if has_text else "max_steps"
        if not has_text:
            yield _event("delta", {"text": FALLBACK})
        add_usage(pending.totals, step_usage)
        yield _done(pending.tool_calls, status, pending.totals)
    except (TimeoutError, GenerationFailure) as failure:
        if isinstance(failure, TimeoutError) or failure.code == "provider_timeout":
            status = "timeout"
            cancelled.set()
            if pending is None:
                yield _done([], status, {})
            else:
                add_usage(pending.totals, step_usage)
                yield _done(pending.tool_calls, status, pending.totals)
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
            _emit(request_id, pending.step, [], status, pending.started, step_usage)
