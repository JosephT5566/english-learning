"""Opaque, query-bound cursor pagination helpers."""

import base64
import hashlib
import json
from datetime import datetime
from uuid import UUID

from app.errors import ApiError

CURSOR_VERSION = 1
MAX_CURSOR_LENGTH = 2048


def _invalid_cursor() -> ApiError:
    return ApiError(
        status_code=400,
        code="invalid_cursor",
        message="The pagination cursor is invalid for this request.",
    )


def query_fingerprint(filters: dict[str, object], limit: int) -> str:
    """Return a stable digest for the normalized query shape."""

    value = json.dumps(
        {"filters": filters, "limit": limit},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def encode_cursor(
    *,
    kind: str,
    fingerprint: str,
    position: dict[str, str],
    snapshot: dict[str, str] | None = None,
) -> str:
    """Encode server cursor state without exposing its representation as a contract."""

    payload: dict[str, object] = {
        "v": CURSOR_VERSION,
        "kind": kind,
        "fingerprint": fingerprint,
        "position": position,
    }
    if snapshot is not None:
        payload["snapshot"] = snapshot
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(encoded).decode().rstrip("=")


def decode_cursor(
    cursor: str,
    *,
    kind: str,
    fingerprint: str,
    position_fields: set[str],
    snapshot_fields: set[str] | None = None,
) -> tuple[dict[str, str], dict[str, str] | None]:
    """Decode and validate a cursor against the complete current query shape."""

    try:
        if not cursor or len(cursor) > MAX_CURSOR_LENGTH:
            raise ValueError
        padding = "=" * (-len(cursor) % 4)
        raw = base64.b64decode(cursor + padding, altchars=b"-_", validate=True)
        payload = json.loads(raw)
        expected_keys = {"v", "kind", "fingerprint", "position"}
        if snapshot_fields is not None:
            expected_keys.add("snapshot")
        if (
            not isinstance(payload, dict)
            or set(payload) != expected_keys
            or payload["v"] != CURSOR_VERSION
            or payload["kind"] != kind
            or payload["fingerprint"] != fingerprint
        ):
            raise ValueError
        position = payload["position"]
        if (
            not isinstance(position, dict)
            or set(position) != position_fields
            or not all(isinstance(value, str) for value in position.values())
        ):
            raise ValueError
        snapshot = payload.get("snapshot")
        if snapshot_fields is not None and (
            not isinstance(snapshot, dict)
            or set(snapshot) != snapshot_fields
            or not all(isinstance(value, str) for value in snapshot.values())
        ):
            raise ValueError
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError):
        raise _invalid_cursor() from None

    return position, snapshot


def parse_cursor_datetime(value: str) -> datetime:
    """Parse one timezone-aware cursor datetime or return the stable cursor error."""

    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError
        return parsed
    except ValueError:
        raise _invalid_cursor() from None


def parse_cursor_uuid(value: str) -> UUID:
    """Parse one cursor UUID or return the stable cursor error."""

    try:
        return UUID(value)
    except (ValueError, AttributeError):
        raise _invalid_cursor() from None


def cursor_datetime(value: datetime) -> str:
    """Serialize a database datetime consistently for a cursor."""

    return value.isoformat()
