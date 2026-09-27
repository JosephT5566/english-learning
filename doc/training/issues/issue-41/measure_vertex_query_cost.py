"""Measure Vertex usage/latency for the frozen Issue #41 v2 query fixture.

This explicit operator command makes exactly 10 RETRIEVAL_QUERY requests. It prints only aggregate
usage, latency, and published-rate cost; it never prints the access token, query text, or vectors.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

FIXTURE = Path(__file__).with_name("deployed-queries-v2.json")
FIXTURE_SHA256 = "4756caf33424266c5722b344124a5d226427fc065dece6e02c8746fd7e86a5a4"
ISSUE_38_DIR = Path(__file__).parents[1] / "issue-38"
VERTEX_EVALUATOR = ISSUE_38_DIR / "evaluate_vertex.py"
PRICE_USD_PER_MILLION_INPUT_TOKENS = 0.15
PRICE_SOURCE = (
    "https://developers.googleblog.com/en/gemini-embedding-available-gemini-api/"
)
PRICE_ACCESSED = "2026-09-27"


def load_vertex_evaluator() -> ModuleType:
    sys.path.insert(0, str(ISSUE_38_DIR))
    try:
        spec = importlib.util.spec_from_file_location(
            "issue_38_vertex_evaluator", VERTEX_EVALUATOR
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("could not load the checked-in Vertex evaluator")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


def nearest_rank(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return round(ordered[math.ceil(percentile * len(ordered)) - 1], 1)


def measure(
    fixture: dict[str, Any],
    embed: Callable[[str, str], tuple[list[float], int, float]],
) -> dict[str, Any]:
    rows = fixture.get("queries")
    if (
        fixture.get("version") != "issue-41-deployed-en-v2"
        or not isinstance(rows, list)
        or len(rows) != 10
    ):
        raise ValueError("unexpected v2 fixture")
    token_counts: list[int] = []
    latencies_ms: list[float] = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("text"), str):
            raise ValueError("invalid v2 query row")
        _, tokens, latency_ms = embed(row["text"], "RETRIEVAL_QUERY")
        if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 0:
            raise ValueError("provider returned invalid token usage")
        if (
            not isinstance(latency_ms, (int, float))
            or not math.isfinite(latency_ms)
            or latency_ms < 0
        ):
            raise ValueError("provider returned invalid latency")
        token_counts.append(tokens)
        latencies_ms.append(float(latency_ms))
    total_tokens = sum(token_counts)
    return {
        "fixture_version": fixture["version"],
        "fixture_sha256": FIXTURE_SHA256,
        "provider": "vertex-ai",
        "model": "gemini-embedding-001",
        "task_type": "RETRIEVAL_QUERY",
        "request_count": len(token_counts),
        "input_tokens_reported": total_tokens,
        "provider_request_p50_ms": nearest_rank(latencies_ms, 0.50),
        "provider_request_p95_ms": nearest_rank(latencies_ms, 0.95),
        "price_usd_per_million_input_tokens": PRICE_USD_PER_MILLION_INPUT_TOKENS,
        "price_source": PRICE_SOURCE,
        "price_accessed": PRICE_ACCESSED,
        "estimated_input_cost_usd": round(
            total_tokens * PRICE_USD_PER_MILLION_INPUT_TOKENS / 1_000_000, 8
        ),
        "actual_billing_inspected": False,
        "limitations": [
            "Latency is operator-machine-to-Vertex, not Cloud Run end-to-end latency.",
            "Cost is a published-rate estimate; actual billing was not inspected by this script.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", default="us-central1")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,61}[a-z0-9]", args.project):
        parser.error("invalid project ID")
    if not re.fullmatch(r"[a-z]+-[a-z]+[0-9]", args.location):
        parser.error("invalid location")

    raw = FIXTURE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != FIXTURE_SHA256:
        raise SystemExit(
            "v2 fixture changed; review and freeze it before provider calls"
        )
    fixture = json.loads(raw)
    token = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not token:
        raise SystemExit("gcloud returned no access token")

    evaluator = load_vertex_evaluator()

    def embed(content: str, task_type: str) -> tuple[list[float], int, float]:
        return evaluator.request_embedding(
            project=args.project,
            location=args.location,
            token=token,
            content=content,
            task_type=task_type,
        )

    print(json.dumps(measure(fixture, embed), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
