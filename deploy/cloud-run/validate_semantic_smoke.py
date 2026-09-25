"""Validate a semantic-search smoke response without printing private results."""

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

REQUEST_ID_PATTERN = re.compile(
    r"^x-request-id:\s*([0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})\s*$",
    re.IGNORECASE | re.MULTILINE,
)
FORBIDDEN_KEYS = frozenset({"embedding", "embeddings", "vector", "vectors"})
INDEX_STATUSES = frozenset({"complete", "partial", "empty"})


def _is_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )


def _contains_forbidden_key(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            str(key).casefold() in FORBIDDEN_KEYS or _contains_forbidden_key(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_key(child) for child in value)
    return False


def validate(
    response: object,
    headers: str,
    metrics: str,
    *,
    max_results: int = 5,
) -> dict[str, Any]:
    """Return a content-safe observation or raise ValueError."""

    try:
        status_text, seconds_text = metrics.strip().split("\t", maxsplit=1)
        status_code = int(status_text)
        total_seconds = float(seconds_text)
    except (TypeError, ValueError):
        raise ValueError("semantic smoke metrics were invalid") from None
    if status_code != 200 or not math.isfinite(total_seconds) or total_seconds < 0:
        raise ValueError("semantic smoke request did not complete successfully")

    request_ids = REQUEST_ID_PATTERN.findall(headers)
    if not request_ids:
        raise ValueError("semantic smoke response omitted X-Request-ID")
    request_id = request_ids[-1].lower()

    if not isinstance(response, dict) or _contains_forbidden_key(response):
        raise ValueError("semantic smoke response was unsafe or malformed")
    items = response.get("items")
    index_status = response.get("index_status")
    eligible_count = response.get("eligible_count")
    indexed_count = response.get("indexed_count")
    if (
        not isinstance(items, list)
        or not 1 <= len(items) <= max_results
        or index_status not in INDEX_STATUSES
        or isinstance(eligible_count, bool)
        or not isinstance(eligible_count, int)
        or isinstance(indexed_count, bool)
        or not isinstance(indexed_count, int)
        or not 0 <= indexed_count <= eligible_count
    ):
        raise ValueError("semantic smoke response contract was invalid")
    if index_status == "complete" and indexed_count != eligible_count:
        raise ValueError("complete semantic coverage counts disagreed")
    if index_status == "partial" and not 0 < indexed_count < eligible_count:
        raise ValueError("partial semantic coverage counts disagreed")
    if index_status == "empty" and indexed_count != 0:
        raise ValueError("empty semantic coverage counts disagreed")

    previous: tuple[float, str] | None = None
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("semantic smoke item was invalid")  # noqa: TRY004
        distance = item.get("distance")
        score = item.get("score")
        card_id = item.get("id")
        if (
            not _is_number(distance)
            or not 0 <= float(distance) <= 2
            or not _is_number(score)
            or not -1 <= float(score) <= 1
            or not isinstance(card_id, str)
            or not math.isclose(float(score), 1 - float(distance), abs_tol=1e-6)
        ):
            raise ValueError("semantic smoke item score contract was invalid")
        order = (float(distance), card_id)
        if previous is not None and order < previous:
            raise ValueError("semantic smoke results were not in stable distance order")
        previous = order

    return {
        "status_code": status_code,
        "request_id": request_id,
        "result_count": len(items),
        "index_status": index_status,
        "eligible_count": eligible_count,
        "indexed_count": indexed_count,
        "total_seconds": round(total_seconds, 6),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--response", type=Path, required=True)
    parser.add_argument("--headers", type=Path, required=True)
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    try:
        response = json.loads(args.response.read_text(encoding="utf-8"))
        report = validate(
            response,
            args.headers.read_text(encoding="utf-8"),
            args.metrics.read_text(encoding="utf-8"),
        )
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise SystemExit(f"Semantic search smoke failed: {error}") from None

    args.report.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "Semantic search smoke passed: "
        f"status={report['status_code']} request_id={report['request_id']} "
        f"results={report['result_count']} index_status={report['index_status']} "
        f"eligible={report['eligible_count']} indexed={report['indexed_count']} "
        f"total_seconds={report['total_seconds']:.6f}"
    )


if __name__ == "__main__":
    main()
