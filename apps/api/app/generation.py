"""Lazy Vertex generation transport with bounded, non-disclosing failures.

REST request/response formats and the schema subset have NOT been verified against
Vertex. A maintainer must run the manual real-model evaluation before deployment.
"""

import json
import threading
from dataclasses import dataclass
from typing import Annotated, Protocol

import google.auth
import requests
from google.auth.credentials import Credentials, TokenState
from google.auth.transport.requests import Request as AuthRequest
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class GenerationFailure(Exception):
    """A safe provider failure code; never retain provider messages."""

    def __init__(self, code: str):
        self.code = code
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


@dataclass(frozen=True)
class GenerationResult:
    text: str
    model: str | None = None
    usage: GenerationUsage | None = None


class GenerationProvider(Protocol):
    def generate(
        self,
        request: GenerationRequest,
        *,
        model: str,
        project: str,
        location: str,
        timeout_seconds: int,
        max_output_tokens: int,
    ) -> GenerationResult: ...

    def close(self) -> None: ...


def vertex_response_schema(schema: dict) -> dict:
    """Resolve refs and project onto an explicit, unverified Vertex schema subset.

    Drop additionalProperties, conditionals, defaults and annotation keywords.
    CardDrafts validation remains authoritative for all omitted constraints.
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
        "minItems",
        "maxItems",
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


def build_vertex_request(request: GenerationRequest, *, max_output_tokens: int) -> dict:
    """Build the unverified REST payload separately from transport and parsing."""
    config: dict = {"maxOutputTokens": max_output_tokens}
    if request.response_schema is not None:
        config.update(
            responseMimeType="application/json", responseSchema=request.response_schema
        )
    return {
        "systemInstruction": {"parts": [{"text": request.system}]},
        "contents": [
            {
                "role": "user",
                "parts": [{"text": json.dumps(request.data, ensure_ascii=False)}],
            }
        ],
        "generationConfig": config,
    }


def parse_vertex_response(payload: object) -> GenerationResult:
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
        if not parts or any(
            set(part) != {"text"} or not isinstance(part["text"], str) for part in parts
        ):
            raise GenerationFailure("invalid_response")
        content = "".join(part["text"] for part in parts)
        if not content:
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
        return GenerationResult(text=content, model=model, usage=usage)
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
        timeout_seconds: int,
        max_output_tokens: int,
    ) -> GenerationResult:
        token = self._access_token()
        try:
            response = requests.post(
                f"https://{location}-aiplatform.googleapis.com/v1/projects/{project}/locations/{location}/publishers/google/models/{model}:generateContent",
                headers={"Authorization": f"Bearer {token}"},
                json=build_vertex_request(request, max_output_tokens=max_output_tokens),
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            return parse_vertex_response(response.json())
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
            raise GenerationFailure(code) from None
        except requests.RequestException:
            raise GenerationFailure("provider_unavailable") from None
        except (ValueError, TypeError):
            raise GenerationFailure("invalid_response") from None
