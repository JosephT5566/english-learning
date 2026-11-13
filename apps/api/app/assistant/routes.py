"""Authenticated stateless assistant endpoints; no conversation persistence."""

import json
import time
from threading import Lock
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Body, Request
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.assistant.clarification import (
    HistoryClarificationAnswer,
    HistoryClarificationQuestion,
)
from app.assistant.history import resolve_card_refs
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


class HistoryCardRefs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: Literal["card_refs"]
    card_ids: Annotated[list[UUID], Field(min_length=1, max_length=200)]

    @field_validator("card_ids", mode="before")
    @classmethod
    def parse_json_ids(cls, value):
        # FastAPI validates decoded JSON in Python mode; keep UUID strings valid.
        if isinstance(value, list):
            return [UUID(item) if isinstance(item, str) else item for item in value]
        return value

    @field_validator("card_ids")
    @classmethod
    def unique_ids(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("duplicate card ids")
        return value


class HistoryProposalState(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: Literal["proposal_state"]
    proposal_id: UUID
    status: Literal["pending", "committed", "dismissed"]
    created_card_ids: Annotated[list[UUID], Field(max_length=20)] = []

    @field_validator("proposal_id", mode="before")
    @classmethod
    def parse_json_proposal_id(cls, value):
        return UUID(value) if isinstance(value, str) else value

    @field_validator("created_card_ids", mode="before")
    @classmethod
    def parse_json_ids(cls, value):
        if isinstance(value, list):
            return [UUID(item) if isinstance(item, str) else item for item in value]
        return value

    @model_validator(mode="after")
    def valid_created_ids(self):
        if len(self.created_card_ids) != len(set(self.created_card_ids)):
            raise ValueError("duplicate card ids")
        if (self.status == "committed") != bool(self.created_card_ids):
            raise ValueError("only committed proposals require created card ids")
        return self


HistoryPart = Annotated[
    HistoryCardRefs
    | HistoryProposalState
    | HistoryClarificationAnswer
    | HistoryClarificationQuestion,
    Field(discriminator="type"),
]


class StreamMessage(Message):
    parts: list[HistoryPart] = []

    @model_validator(mode="after")
    def assistant_parts_only(self):
        for part in self.parts:
            if (self.role == "user") != isinstance(part, HistoryClarificationAnswer):
                raise ValueError("history part is not allowed on this message role")
        return self


CapabilityToken = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_.-]{0,31}$")]


class AssistantStreamRequest(AssistantRequest):
    messages: Annotated[list[StreamMessage], Field(min_length=1, max_length=100)]
    capabilities: Annotated[list[CapabilityToken], Field(max_length=8)] = []


def _validate_request(request, payload):
    _reject_unknown_filters(request, set())
    settings = request.app.state.settings
    history_parts = [
        m.parts for m in payload.messages if isinstance(m, StreamMessage) and m.parts
    ]
    ref_count = sum(
        len(
            part.card_ids
            if isinstance(part, HistoryCardRefs)
            else part.created_card_ids
            if isinstance(part, HistoryProposalState)
            else []
        )
        for parts in history_parts
        for part in parts
    )
    part_chars = sum(
        len(
            json.dumps(
                [p.model_dump(mode="json") for p in parts],
                separators=(",", ":"),
                ensure_ascii=False,
            )
        )
        for parts in history_parts
    )
    if (
        ref_count > settings.assistant_max_history_card_refs
        or len(payload.messages) > settings.assistant_max_messages
        or sum(len(m.content) for m in payload.messages) + part_chars
        > settings.assistant_max_chars
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
                    owned_session,
                    owner_id,
                    settings,
                    embedding_provider,
                    messages=messages,
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
                "part: {id: string, type: string, payload: object}. "
                "Parts are sent only when the request declares parts.v1, always before "
                "the terminal event. Clients must ignore unknown part types. "
                "done: {tool_calls: ToolCallSummary[], stop_reason: completed | max_steps | timeout, "
                "usage: GenerationUsage | null}. "
                "error: {code: string, message: string, retryable: boolean}. "
                "A connected client receives exactly one terminal done or error event. "
                ": ping comment lines may arrive before the first event and must be ignored."
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
    payload: Annotated[AssistantStreamRequest, Body()],
):
    settings = _validate_request(request, payload)
    owner_id = user.id
    messages = [message.model_dump(mode="json") for message in payload.messages]
    ref_ids = {
        id
        for message in payload.messages
        for part in message.parts
        for id in (
            part.card_ids
            if isinstance(part, HistoryCardRefs)
            else part.created_card_ids
            if isinstance(part, HistoryProposalState)
            else []
        )
    }
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
            resolved_cards = (
                resolve_card_refs(owned_session, owner_id, ref_ids, deadline, cancelled)
                if ref_ids
                else {}
            )
            check_budget(deadline, cancelled)

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
                    messages=messages,
                ),
                request_id=request_id,
                before_generate=consent_then_release,
                deadline=deadline,
                resolved_cards=resolved_cards,
                prepare_final=True,
                cancelled=cancelled,
            )

    return AssistantSSE(
        stream_events(
            prepare,
            provider,
            settings,
            deadline,
            request_id,
            parts_enabled="parts.v1" in payload.capabilities,
        ),
        deadline=deadline,
        request_id=request_id,
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
