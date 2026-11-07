"""Lazy Vertex generation transport with bounded, non-disclosing failures.

REST request/response formats and the schema subset have NOT been verified against
Vertex. A maintainer must run the manual real-model evaluation before deployment.
"""

import json
import threading
import time
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Annotated, Protocol

import google.auth
import requests
from google.auth.credentials import Credentials, TokenState
from google.auth.transport.requests import Request as AuthRequest
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class GenerationFailure(Exception):
    """A safe provider failure code; never retain provider messages."""

    def __init__(self, code: str, *, http_status: int | None = None):
        self.code = code
        # Only a bounded HTTP status may cross into internal logs/eval reports.
        self.http_status = (
            http_status
            if type(http_status) is int and 100 <= http_status <= 599
            else None
        )
        super().__init__(code)


TokenCount = Annotated[int, Field(strict=True, ge=0)]


class GenerationUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_tokens: TokenCount | None = None
    output_tokens: TokenCount | None = None
    total_tokens: TokenCount | None = None


@dataclass(frozen=True)
class GenerationRequest:
    """General generation input; structured output is optional, not a protocol limit."""

    system: str
    data: dict
    response_schema: dict | None = None
    contents: list[dict] | None = None
    tools: list[dict] | None = None
    tools_disabled: bool = False


@dataclass(frozen=True)
class GenerationResult:
    text: str
    model: str | None = None
    usage: GenerationUsage | None = None
    parts: list[dict] = field(default_factory=list)
    function_calls: list[dict] = field(default_factory=list)


class GenerationProvider(Protocol):
    def generate(
        self,
        request: GenerationRequest,
        *,
        model: str,
        project: str,
        location: str,
        timeout_seconds: float,
        max_output_tokens: int,
        deadline: float | None = None,
    ) -> GenerationResult: ...

    def close(self) -> None: ...


def vertex_response_schema(schema: dict) -> dict:
    """Resolve refs and project onto the generation provider schema subset.

    The maintainer's 2026-11-05 gemini-3.8-flash/global Vertex bisect rejected
    array cardinality keywords together; omit both minItems and maxItems.
    Other retained keywords were present in one accepted request, not verified
    across all outputs/models. Drop extra-property rules, conditionals, defaults
    and annotations. Full CardDrafts server validation enforces 1-20 cards and
    all other constraints; provider schema acceptance is not output validation.
    """
    definitions = schema.get("$defs", {})
    supported = {
        "type",
        "description",
        "enum",
        "format",
        "minimum",
        "maximum",
        "minLength",
        "maxLength",
        "required",
    }

    def convert(node: dict) -> dict:
        if "$ref" in node:
            return convert(definitions[node["$ref"].removeprefix("#/$defs/")])
        if "anyOf" in node:
            choices = node["anyOf"]
            non_null = [choice for choice in choices if choice.get("type") != "null"]
            if len(non_null) != 1 or len(choices) != 2:
                raise ValueError("unsupported schema union")
            return {**convert(non_null[0]), "nullable": True}
        result = {key: value for key, value in node.items() if key in supported}
        if "properties" in node:
            result["properties"] = {
                key: convert(value) for key, value in node["properties"].items()
            }
        if "items" in node:
            result["items"] = convert(node["items"])
        return result

    return convert(schema)


def build_generation_url(*, project: str, location: str, model: str) -> str:
    """Build generation-only routing; the global Vertex URL is unverified live.

    Global host/path format comes from prior knowledge, not online documentation
    or a successful model call. Regional embedding routing is intentionally separate.
    """
    host = (
        "aiplatform.googleapis.com"
        if location == "global"
        else f"{location}-aiplatform.googleapis.com"
    )
    return (
        f"https://{host}/v1/projects/{project}/locations/{location}"
        f"/publishers/google/models/{model}:generateContent"
    )


def build_vertex_request(request: GenerationRequest, *, max_output_tokens: int) -> dict:
    """Build the unverified REST payload separately from transport and parsing."""
    config: dict = {"maxOutputTokens": max_output_tokens}
    if request.response_schema is not None:
        config.update(
            responseMimeType="application/json", responseSchema=request.response_schema
        )
    payload = {
        "systemInstruction": {"parts": [{"text": request.system}]},
        "contents": [
            {
                "role": "user",
                "parts": [{"text": json.dumps(request.data, ensure_ascii=False)}],
            }
        ],
        "generationConfig": config,
    }
    if request.contents is not None:
        payload["contents"] = deepcopy(request.contents)
    if request.tools is not None:
        payload["tools"] = [{"functionDeclarations": deepcopy(request.tools)}]
    if request.tools_disabled:
        # NONE is explicit even with declarations retained. Unverified on real Vertex.
        payload["toolConfig"] = {"functionCallingConfig": {"mode": "NONE"}}
    return payload


# Allowlist based on the review-cited Vertex Content REST reference (unverified;
# online documentation and live API validation were prohibited for this task).
# Unknown keys fail closed, including mixed text/tool or text/media content.
TEXT_PART_KEYS = frozenset({"text", "thought", "thoughtSignature"})


def parse_vertex_response(
    payload: object, *, allow_empty: bool = False
) -> GenerationResult:
    """Parse handwritten response contracts, NOT a verified live Vertex contract."""
    try:
        candidates = payload["candidates"]
        if len(candidates) != 1:
            raise GenerationFailure("invalid_response")
        candidate = candidates[0]
        if candidate.get("finishReason") == "MAX_TOKENS":
            raise GenerationFailure("truncated_output")
        if candidate.get("finishReason") != "STOP":
            raise GenerationFailure("invalid_response")
        parts = candidate["content"]["parts"]
        if not isinstance(parts, list) or not parts:
            raise GenerationFailure("invalid_response")
        final_text = []
        function_calls = []
        for part in parts:
            if isinstance(part, dict) and "functionCall" in part:
                function = part["functionCall"]
                if (
                    not set(part) <= {"functionCall", "thoughtSignature", "thought"}
                    or not isinstance(function, dict)
                    or not set(function) <= {"name", "args", "id"}
                    or not isinstance(function.get("name"), str)
                    or not function["name"].strip()
                    or not isinstance(function.get("args", {}), dict)
                    or (
                        "id" in function
                        and (
                            not isinstance(function["id"], str)
                            or not function["id"].strip()
                        )
                    )
                    or ("thought" in part and not isinstance(part["thought"], bool))
                    or (
                        "thoughtSignature" in part
                        and not isinstance(part["thoughtSignature"], str)
                    )
                ):
                    raise GenerationFailure("invalid_response")
                call = deepcopy(function)
                call.setdefault("args", {})
                function_calls.append(call)
                continue
            if (
                not isinstance(part, dict)
                or not set(part) <= TEXT_PART_KEYS
                or not isinstance(part.get("text"), str)
                or ("thought" in part and not isinstance(part["thought"], bool))
                or (
                    "thoughtSignature" in part
                    and not isinstance(part["thoughtSignature"], str)
                )
            ):
                raise GenerationFailure("invalid_response")
            # Validate even excluded thoughts so they cannot hide non-text content.
            # Signatures are opaque metadata and are never part of the answer.
            if not part.get("thought", False):
                final_text.append(part["text"])
        content = "".join(final_text)
        if not content and not function_calls and not allow_empty:
            raise GenerationFailure("invalid_response")
        model = payload.get("modelVersion")
        if model is not None and (not isinstance(model, str) or not model.strip()):
            raise GenerationFailure("invalid_response")
        metadata = payload.get("usageMetadata")
        usage = None
        if metadata is not None:
            usage = GenerationUsage(
                input_tokens=metadata.get("promptTokenCount"),
                output_tokens=metadata.get("candidatesTokenCount"),
                total_tokens=metadata.get("totalTokenCount"),
            )
        # Preserve full model parts including opaque thoughtSignature for replay.
        # Gemini multi-turn signature requirements are unverified; real-model eval is needed.
        return GenerationResult(
            text=content,
            model=model,
            usage=usage,
            parts=deepcopy(parts),
            function_calls=function_calls,
        )
    except GenerationFailure:
        raise
    except (
        KeyError,
        IndexError,
        TypeError,
        ValueError,
        AttributeError,
        ValidationError,
    ):
        raise GenerationFailure("invalid_response") from None


class VertexGenerationProvider:
    """Own lazy ADC credentials and release the refresh transport at shutdown."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._credentials: Credentials | None = None
        self._auth_request: AuthRequest | None = None
        self._closed = False

    def _access_token(self) -> str:
        with self._lock:
            if self._closed:
                raise GenerationFailure("provider_unavailable")
            try:
                if self._credentials is None:
                    self._credentials, _ = google.auth.default(
                        scopes=["https://www.googleapis.com/auth/cloud-platform"]
                    )
                if self._credentials.token_state is not TokenState.FRESH:
                    if self._auth_request is None:
                        self._auth_request = AuthRequest()
                    self._credentials.refresh(self._auth_request)
                token = self._credentials.token
                if not isinstance(token, str) or not token:
                    raise google.auth.exceptions.RefreshError("Missing access token")
                return token
            except google.auth.exceptions.GoogleAuthError:
                self._credentials = None
                raise GenerationFailure("provider_auth_error") from None

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._credentials = None
            if self._auth_request is not None:
                self._auth_request.session.close()

    def generate(
        self,
        request: GenerationRequest,
        *,
        model: str,
        project: str,
        location: str,
        timeout_seconds: float,
        max_output_tokens: int,
        deadline: float | None = None,
    ) -> GenerationResult:
        token = self._access_token()
        try:
            url = build_generation_url(project=project, location=location, model=model)
            payload = build_vertex_request(request, max_output_tokens=max_output_tokens)
            if deadline is not None:
                timeout_seconds = min(timeout_seconds, deadline - time.monotonic())
                if timeout_seconds <= 0:
                    raise GenerationFailure("provider_timeout")
            response = requests.post(
                url,
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            result = parse_vertex_response(
                response.json(),
                # A fully validated final NONE response with only thought parts
                # must reach the assistant fallback, not bypass part validation.
                allow_empty=request.tools is not None and request.tools_disabled,
            )
            if result.function_calls and request.tools is None:
                raise GenerationFailure("invalid_response")
            return result
        except (
            requests.exceptions.JSONDecodeError,
            requests.exceptions.ContentDecodingError,
            requests.exceptions.ChunkedEncodingError,
        ):
            # Body format/framing failures are invalid output, not retryable outages.
            # JSONDecodeError is also a RequestException, so this must precede it.
            raise GenerationFailure("invalid_response") from None
        except requests.Timeout:
            raise GenerationFailure("provider_timeout") from None
        except requests.HTTPError as error:
            status = error.response.status_code if error.response is not None else None
            if status == 401:
                with self._lock:
                    if (
                        self._credentials is not None
                        and self._credentials.token == token
                    ):
                        self._credentials.token = None
            code = "invalid_response"
            if status in {401, 403}:
                code = "provider_auth_error"
            elif status == 429:
                code = "provider_rate_limited"
            elif status and status >= 500:
                code = "provider_unavailable"
            raise GenerationFailure(code, http_status=status) from None
        except requests.RequestException:
            raise GenerationFailure("provider_unavailable") from None
        except (ValueError, TypeError):
            raise GenerationFailure("invalid_response") from None
