"""Authenticated text-only assistant endpoint; no conversation persistence."""

import time
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy.exc import SQLAlchemyError

from app.assistant.loop import FALLBACK, AssistantResponse, bounded_call, run_assistant
from app.assistant.tools import SessionTools, set_query_budget
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


@router.post("/messages", response_model=AssistantResponse)
def assistant_messages(
    user: CurrentUserDependency,
    session: SessionDependency,
    request: Request,
    payload: Annotated[AssistantRequest, Body()],
):
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

    def orchestrate():
        # The worker exclusively owns this session. Caller timeout never closes a
        # session while another thread is using it. No request-scoped session is
        # captured here; a late worker cleans up its own transaction/connection.
        with factory() as owned_session:
            bind_owner(owned_session, owner_id)

            def consent_then_release():
                try:
                    set_query_budget(owned_session, deadline)
                    require_genai_consent(owned_session, owner_id)
                    owned_session.commit()
                except SQLAlchemyError as error:
                    if (
                        getattr(getattr(error, "orig", None), "sqlstate", None)
                        == "57014"
                    ):
                        raise GenerationFailure("provider_timeout") from None
                    raise
                if time.monotonic() >= deadline:
                    raise GenerationFailure("provider_timeout")

            consent_then_release()
            if not settings.generation_model or not settings.vertex_project_id:
                raise ApiError(
                    status_code=503,
                    code="generation_not_configured",
                    message="Learning assistant generation is not configured.",
                )
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

    try:
        return bounded_call(orchestrate, deadline - time.monotonic())
    except GenerationFailure as failure:
        if failure.code == "provider_timeout":
            return AssistantResponse(
                reply=FALLBACK, tool_calls=[], stop_reason="timeout"
            )
        statuses = {
            "provider_rate_limited": 503,
            "provider_unavailable": 503,
            "provider_auth_error": 503,
            "invalid_response": 502,
            "truncated_output": 502,
        }
        code = failure.code if failure.code in statuses else "invalid_response"
        raise ApiError(
            status_code=statuses[code],
            code=f"generation_{code}",
            message="Learning assistant generation failed.",
            retryable=code in {"provider_rate_limited", "provider_unavailable"},
        ) from None
