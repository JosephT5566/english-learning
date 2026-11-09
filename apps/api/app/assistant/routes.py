"""Authenticated text-only assistant endpoint; no conversation persistence."""

import time
from threading import Lock
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.assistant.loop import (
    FALLBACK,
    AssistantResponse,
    bounded_call,
    emit_run_completed,
    generation_error,
    run_assistant,
)
from app.assistant.sse import AssistantSSE, stream_events
from app.assistant.tools import (
    AssistantDeadlineExceeded,
    SessionTools,
    check_budget,
    set_query_budget,
)
from app.auth import CurrentUserDependency
from app.database import bind_owner
from app.errors import ApiError
from app.genai_consent import require_genai_consent
from app.generation import GenerationFailure
from app.reads import SessionDependency, _reject_unknown_filters

router = APIRouter(prefix="/v1/assistant")


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    role: Literal["user", "assistant"]
    content: Annotated[str, StringConstraints(min_length=1, max_length=100000)]


class AssistantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    messages: Annotated[list[Message], Field(min_length=1, max_length=100)]


def _validate_request(request, payload):
    _reject_unknown_filters(request, set())
    settings = request.app.state.settings
    if (
        len(payload.messages) > settings.assistant_max_messages
        or sum(len(m.content) for m in payload.messages) > settings.assistant_max_chars
    ):
        raise ApiError(
            status_code=422,
            code="input_too_large",
            message="Assistant input exceeds configured limits.",
        )

    return settings


def _consent_then_release(session, owner_id, deadline, *, cancelled=None):
    try:
        set_query_budget(session, deadline, cancelled=cancelled)
        require_genai_consent(session, owner_id)
        session.commit()
    except SQLAlchemyError as error:
        if getattr(getattr(error, "orig", None), "sqlstate", None) == "57014":
            raise AssistantDeadlineExceeded() from None
        raise
    check_budget(deadline, cancelled)


def _require_configuration(settings):
    if not settings.generation_model or not settings.vertex_project_id:
        raise ApiError(
            status_code=503,
            code="generation_not_configured",
            message="Learning assistant generation is not configured.",
        )


@router.post("/messages", response_model=AssistantResponse)
def assistant_messages(
    user: CurrentUserDependency,
    session: SessionDependency,
    request: Request,
    payload: Annotated[AssistantRequest, Body()],
):
    settings = _validate_request(request, payload)

    # Auth and request validation retain their existing framework boundaries.
    # One deadline then covers consent, pool/SQL waits, tools and generation.
    owner_id = user.id
    messages = [m.model_dump() for m in payload.messages]
    factory = request.app.state.database_session_factory
    provider = request.app.state.generation_provider
    embedding_provider = request.app.state.embedding_provider
    request_id = str(request.state.request_id)
    session.commit()
    deadline = time.monotonic() + settings.assistant_timeout_seconds
    run_lock = Lock()
    run_started_at = None
    run_closed = False

    def orchestrate():
        nonlocal run_started_at
        # The worker exclusively owns this session. Caller timeout never closes a
        # session while another thread is using it. No request-scoped session is
        # captured here; a late worker cleans up its own transaction/connection.
        with factory() as owned_session:
            bind_owner(owned_session, owner_id)

            def consent_then_release():
                _consent_then_release(owned_session, owner_id, deadline)

            consent_then_release()
            _require_configuration(settings)
            # Admission and request completion can race after the caller times out.
            with run_lock:
                started_at = time.monotonic()
                if run_closed or started_at >= deadline:
                    raise AssistantDeadlineExceeded()
                run_started_at = started_at
            return run_assistant(
                messages=messages,
                settings=settings,
                provider=provider,
                execute=SessionTools(
                    owned_session, owner_id, settings, embedding_provider
                ),
                request_id=request_id,
                before_generate=consent_then_release,
                deadline=deadline,
            )

    outcome, error_code = "error", "internal_error"
    try:
        result = bounded_call(orchestrate, deadline - time.monotonic())
        outcome, error_code = result.stop_reason, result._terminal_error_code
        return result
    except GenerationFailure as failure:
        if failure.code == "provider_timeout":
            outcome, error_code = "timeout", None
            return AssistantResponse(
                reply=FALLBACK, tool_calls=[], stop_reason="timeout"
            )
        error = generation_error(failure)
        error_code = error.code
        raise error from None
    except ApiError as error:
        error_code = error.code
        raise
    except SQLAlchemyError as error:
        # The request database dependency sanitizes these exceptions for HTTP.
        error_code = (
            "validation_failed"
            if isinstance(error, IntegrityError)
            else "database_unavailable"
        )
        raise
    finally:
        with run_lock:
            run_closed = True
            started_at = run_started_at
        if started_at is not None:
            emit_run_completed(request_id, "json", started_at, outcome, error_code)


@router.post(
    "/messages/stream",
    response_class=AssistantSSE,
    responses={
        200: {
            "description": (
                "Server-Sent Events. Each data field is JSON. "
                "delta: {text: string}. "
                "done: {tool_calls: ToolCallSummary[], stop_reason: completed | max_steps | timeout, "
                "usage: GenerationUsage | null}. "
                "error: {code: string, message: string, retryable: boolean}. "
                "A connected client receives exactly one terminal done or error event."
            ),
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        },
        401: {"description": "Authentication required before streaming"},
        403: {"description": "GenAI consent required before streaming"},
        503: {"description": "Generation or database unavailable before streaming"},
        504: {"description": "Assistant preflight timed out"},
    },
)
def assistant_stream(
    user: CurrentUserDependency,
    session: SessionDependency,
    request: Request,
    payload: Annotated[AssistantRequest, Body()],
):
    settings = _validate_request(request, payload)
    owner_id = user.id
    messages = [message.model_dump() for message in payload.messages]
    state = request.app.state
    factory = state.database_session_factory
    provider = state.generation_provider
    embedding_provider = state.embedding_provider
    request_id = str(request.state.request_id)
    session.commit()
    deadline = time.monotonic() + settings.assistant_timeout_seconds

    def preflight():
        with factory() as owned_session:
            bind_owner(owned_session, owner_id)
            _consent_then_release(owned_session, owner_id, deadline)

    try:
        bounded_call(preflight, deadline - time.monotonic())
    except GenerationFailure as failure:
        raise generation_error(failure) from None
    _require_configuration(settings)

    def prepare(cancelled):
        with factory() as owned_session:
            bind_owner(owned_session, owner_id)

            def consent_then_release():
                _consent_then_release(
                    owned_session, owner_id, deadline, cancelled=cancelled
                )

            return run_assistant(
                messages=messages,
                settings=settings,
                provider=provider,
                execute=SessionTools(
                    owned_session,
                    owner_id,
                    settings,
                    embedding_provider,
                    cancelled=cancelled,
                ),
                request_id=request_id,
                before_generate=consent_then_release,
                deadline=deadline,
                prepare_final=True,
                cancelled=cancelled,
            )

    return AssistantSSE(
        stream_events(prepare, provider, settings, deadline, request_id),
        deadline=deadline,
        request_id=request_id,
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
