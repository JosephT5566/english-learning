"""Run the explicit Issue #41 deployed semantic-search workload.

The runner prints response content only to the local terminal for human grading. Its JSON report
contains query IDs, relevance grades, safe response metadata, and latency observations, but never
the Google ID token, query text, card IDs, terms, meanings, or scores.

Example from the repository root:
    python3 doc/training/issues/issue-41/run_deployed_evaluation.py \
        --base-url https://YOUR-STABLE-API-HOST \
        --report /tmp/issue-41-deployed-report.json

Supply GOOGLE_ID_TOKEN in the environment or enter it at the hidden prompt. Never pass it as a
command-line argument. Each query makes one provider-backed request per repetition.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import math
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

DEFAULT_QUERIES = Path(__file__).with_name("deployed-queries-v2.json")
DEFAULT_REPORT = Path("/tmp/issue-41-deployed-report.json")
REQUEST_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
ALLOWED_TYPES = frozenset(
    {
        "paraphrase",
        "exact",
        "ambiguous",
        "natural_sentence",
        "no_confident_match",
        "near_synonym",
    }
)
PRIVATE_REPORT_KEYS = frozenset(
    {
        "text",
        "query",
        "term",
        "meaning",
        "id",
        "card_id",
        "deck_id",
        "score",
        "distance",
    }
)


def validate_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlsplit(normalized)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("base URL must be one credential-free HTTPS origin")
    return normalized


def load_queries(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    payload = json.loads(raw)
    rows = payload.get("queries") if isinstance(payload, dict) else None
    if (
        not isinstance(payload.get("version"), str)
        or not isinstance(rows, list)
        or len(rows) != 10
    ):
        raise ValueError("query fixture must contain a version and exactly 10 queries")
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise TypeError("each query fixture row must be an object")
        query_id = row.get("id")
        query_type = row.get("type")
        query_text = row.get("text")
        expected = row.get("expected_concepts")
        if (
            not isinstance(query_id, str)
            or not re.fullmatch(r"q[0-9]{2}-[a-z0-9-]+", query_id)
            or query_id in seen
            or query_type not in ALLOWED_TYPES
            or not isinstance(query_text, str)
            or not 2 <= len(query_text.strip()) <= 500
            or not isinstance(expected, list)
            or any(not isinstance(item, str) or not item.strip() for item in expected)
        ):
            raise ValueError("query fixture row is invalid")
        seen.add(query_id)
    return payload, hashlib.sha256(raw).hexdigest()


def _finite_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )


def validate_success(body: object) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise TypeError("response body must be an object")
    items = body.get("items")
    index_status = body.get("index_status")
    eligible = body.get("eligible_count")
    indexed = body.get("indexed_count")
    if (
        not isinstance(items, list)
        or len(items) > 5
        or index_status not in {"complete", "partial", "empty"}
        or isinstance(eligible, bool)
        or not isinstance(eligible, int)
        or isinstance(indexed, bool)
        or not isinstance(indexed, int)
        or not 0 <= indexed <= eligible
    ):
        raise ValueError("semantic response contract was invalid")
    previous: tuple[float, str] | None = None
    for item in items:
        if not isinstance(item, dict):
            raise TypeError("semantic result was invalid")
        card_id = item.get("id")
        distance = item.get("distance")
        score = item.get("score")
        if (
            not isinstance(card_id, str)
            or not _finite_number(distance)
            or not 0 <= float(distance) <= 2
            or not _finite_number(score)
            or not -1 <= float(score) <= 1
            or not math.isclose(float(score), 1 - float(distance), abs_tol=1e-6)
        ):
            raise ValueError("semantic result score contract was invalid")
        order = (float(distance), card_id)
        if previous is not None and order < previous:
            raise ValueError("semantic results were not stably ordered")
        previous = order
    return body


def request_once(
    *,
    base_url: str,
    token: str,
    query: str,
    deck_id: str | None,
    timeout_seconds: float,
    open_url: Callable[..., Any] = urlopen,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    payload: dict[str, Any] = {"query": query, "target_language": "en", "limit": 5}
    if deck_id is not None:
        payload["deck_id"] = deck_id
    request = Request(
        f"{base_url}/v1/cards/semantic-search",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    started = time.monotonic()
    try:
        with open_url(request, timeout=timeout_seconds) as response:
            body = json.load(response)
            status = response.status
            request_id = response.headers.get("X-Request-ID", "").lower()
    except HTTPError as error:
        elapsed_ms = (time.monotonic() - started) * 1000
        request_id = error.headers.get("X-Request-ID", "").lower()
        try:
            error_body = json.load(error)
            safe_code = error_body.get("error", {}).get("code")
        except (AttributeError, json.JSONDecodeError, TypeError):
            safe_code = None
        observation = {
            "status_code": error.code,
            "request_id": request_id
            if REQUEST_ID_PATTERN.fullmatch(request_id)
            else None,
            "total_ms": round(elapsed_ms, 3),
            "error_code": safe_code if isinstance(safe_code, str) else "http_error",
        }
        return observation, None
    except (TimeoutError, URLError):
        elapsed_ms = (time.monotonic() - started) * 1000
        return {
            "status_code": 0,
            "request_id": None,
            "total_ms": round(elapsed_ms, 3),
            "error_code": "transport_error",
        }, None

    elapsed_ms = (time.monotonic() - started) * 1000
    if status != 200 or not REQUEST_ID_PATTERN.fullmatch(request_id):
        raise ValueError("successful response omitted a valid request ID")
    valid = validate_success(body)
    observation = {
        "status_code": status,
        "request_id": request_id,
        "total_ms": round(elapsed_ms, 3),
        "result_count": len(valid["items"]),
        "index_status": valid["index_status"],
        "eligible_count": valid["eligible_count"],
        "indexed_count": valid["indexed_count"],
    }
    return observation, valid


def grading_warning(query_type: str, grades: list[int]) -> str | None:
    if grades and all(grade == 2 for grade in grades):
        return "all returned results were marked strong"
    if query_type == "no_confident_match" and 2 in grades:
        return "a planned no-confident-match query has a strong result"
    return None


def prompt_grades(query_row: dict[str, Any], body: dict[str, Any]) -> list[int]:
    print(f"\n{query_row['id']} ({query_row['type']})")
    print(f"Query: {query_row['text']}")
    print("Expected concepts: " + (", ".join(query_row["expected_concepts"]) or "none"))
    print(
        "2=directly answers the expected concept; 1=related but not a direct answer; 0=not useful"
    )
    print(
        "Ignore the model score when grading. Similar wording alone is not enough for grade 2."
    )
    while True:
        grades: list[int] = []
        for rank, item in enumerate(body["items"], start=1):
            print(
                f"  {rank}. term={item.get('term', '')!r} meaning={item.get('meaning', '')!r} "
                f"score={float(item['score']):.4f}"
            )
            while True:
                answer = input(f"     relevance for rank {rank} [0/1/2]: ").strip()
                if answer in {"0", "1", "2"}:
                    grades.append(int(answer))
                    break
                print("     Enter only 0, 1, or 2.")
        warning = grading_warning(query_row["type"], grades)
        if warning is None:
            return grades
        print(f"Review warning: {warning}.")
        confirmation = input(
            "Type 'confirm' if every grade is intentional, otherwise regrade: "
        )
        if confirmation.strip().casefold() == "confirm":
            return grades


def percentile_nearest_rank(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[math.ceil(percentile * len(ordered)) - 1], 3)


def build_report(
    *,
    fixture: dict[str, Any],
    fixture_sha256: str,
    repetitions: int,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    successful_ms = [
        observation["total_ms"]
        for row in rows
        for observation in row["observations"]
        if observation["status_code"] == 200
    ]
    judged = [row for row in rows if row.get("grades") is not None]
    strong_hits = [2 in row["grades"][:5] for row in judged]
    warning_count = sum(
        grading_warning(row["query_type"], row["grades"]) is not None for row in judged
    )
    return {
        "fixture_version": fixture["version"],
        "fixture_sha256": fixture_sha256,
        "query_count": len(rows),
        "repetitions": repetitions,
        "request_count": sum(len(row["observations"]) for row in rows),
        "successful_request_count": len(successful_ms),
        "end_to_end_p50_ms": percentile_nearest_rank(successful_ms, 0.50),
        "end_to_end_p95_ms": percentile_nearest_rank(successful_ms, 0.95),
        "observed_strong_hit_at_5": (
            round(sum(strong_hits) / len(strong_hits), 4) if strong_hits else None
        ),
        "grading_warning_count": warning_count,
        "queries": rows,
        "limitations": [
            "Human grades cover returned Top-5 items only and cannot produce unbiased nDCG.",
            "End-to-end timings include client network, Cloud Run, one query embedding, and PostgreSQL ranking.",
            "The report intentionally omits query text and result content.",
        ],
    }


def assert_content_safe_report(report: object) -> None:
    def walk(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).casefold() in PRIVATE_REPORT_KEYS:
                    raise ValueError(
                        f"private key {key!r} cannot be written to the report"
                    )
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(report)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", help="Stable credential-free HTTPS API origin")
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--deck-id", help="Optional owned deck UUID filter")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print the query plan without requests",
    )
    args = parser.parse_args()

    try:
        fixture, fixture_sha256 = load_queries(args.queries)
        if not 1 <= args.repetitions <= 10:
            raise ValueError("repetitions must be between 1 and 10")
        if not 1 <= args.timeout_seconds <= 60:
            raise ValueError("timeout must be between 1 and 60 seconds")
        base_url = validate_base_url(args.base_url or input("Stable API base URL: "))
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise SystemExit(f"Invalid evaluation configuration: {error}") from None

    print(f"Fixture: {fixture['version']} sha256={fixture_sha256}")
    print(
        f"Planned provider-backed requests: {len(fixture['queries']) * args.repetitions}"
    )
    for row in fixture["queries"]:
        print(f"- {row['id']} [{row['type']}]: {row['text']}")
        print(
            f"  expected: {', '.join(row['expected_concepts']) or 'no confident match'}"
        )
    if args.dry_run:
        return

    token = (
        os.getenv("GOOGLE_ID_TOKEN")
        or getpass.getpass("Google ID token (hidden): ").strip()
    )
    if not token:
        raise SystemExit("A Google ID token is required.")
    confirmation = (
        input(
            f"Send {len(fixture['queries']) * args.repetitions} provider-backed requests? [yes/no]: "
        )
        .strip()
        .casefold()
    )
    if confirmation != "yes":
        raise SystemExit("Evaluation cancelled before any request.")

    report_rows: list[dict[str, Any]] = []
    for query_row in fixture["queries"]:
        observations: list[dict[str, Any]] = []
        grades: list[int] | None = None
        for repetition in range(1, args.repetitions + 1):
            observation, body = request_once(
                base_url=base_url,
                token=token,
                query=query_row["text"],
                deck_id=args.deck_id,
                timeout_seconds=args.timeout_seconds,
            )
            observation["repetition"] = repetition
            observation["run_class"] = "first" if repetition == 1 else "repeated"
            observations.append(observation)
            print(
                f"{query_row['id']} run={repetition} status={observation['status_code']} "
                f"total_ms={observation['total_ms']} request_id={observation['request_id']}"
            )
            if repetition == 1 and body is not None:
                grades = prompt_grades(query_row, body)
        report_rows.append(
            {
                "query_label": query_row["id"],
                "query_type": query_row["type"],
                "grades": grades,
                "strong_hit_at_5": 2 in grades[:5] if grades is not None else None,
                "best_strong_rank": (
                    grades.index(2) + 1 if grades is not None and 2 in grades else None
                ),
                "observations": observations,
            }
        )

    report = build_report(
        fixture=fixture,
        fixture_sha256=fixture_sha256,
        repetitions=args.repetitions,
        rows=report_rows,
    )
    assert_content_safe_report(report)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"Safe report written to {args.report}: requests={report['request_count']} "
        f"successes={report['successful_request_count']} "
        f"p50_ms={report['end_to_end_p50_ms']} p95_ms={report['end_to_end_p95_ms']} "
        f"observed_strong_hit_at_5={report['observed_strong_hit_at_5']}"
    )


if __name__ == "__main__":
    main()
