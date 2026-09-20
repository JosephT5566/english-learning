"""Manually run the synthetic Issue #38 Vertex AI retrieval evaluation.

Requires a locally authenticated gcloud CLI and an explicitly selected project:
    python3 evaluate_vertex.py --project PROJECT_ID

This script sends only the checked-in synthetic fixture to Vertex AI. It never prints
access tokens, card text, or embedding values. Importing this module makes no API calls.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from evaluate import evaluate

MODEL = "gemini-embedding-001"
DIMENSIONS = 512
FIXTURE = Path(__file__).with_name("relevance.json")
FIXTURE_SHA256 = "a1d6e3e9a76a2705dd5fc2a869339debf46c32217a22fef35d2a7e6d632811dd"


def validate_vector(values: object) -> list[float]:
    if not isinstance(values, list) or len(values) != DIMENSIONS:
        raise ValueError("provider returned the wrong embedding dimension")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        for value in values
    ):
        raise ValueError("provider returned a non-finite embedding")
    if not any(value != 0 for value in values):
        raise ValueError("provider returned a zero embedding")
    return [float(value) for value in values]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = math.fsum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(math.fsum(value * value for value in left))
    right_norm = math.sqrt(math.fsum(value * value for value in right))
    return numerator / (left_norm * right_norm)


def canonical_card_text(card: dict) -> str:
    fields = {"language": "en", **card}
    return "\n".join(
        f"{field}: {fields[field]}"
        for field in ("language", "term", "meaning", "example_sentence")
        if field in fields
    )


def request_embedding(
    *, project: str, location: str, token: str, content: str, task_type: str
) -> tuple[list[float], int, float]:
    url = (
        f"https://{location}-aiplatform.googleapis.com/v1/projects/{project}"
        f"/locations/{location}/publishers/google/models/{MODEL}:predict"
    )
    body = json.dumps(
        {
            "instances": [{"content": content, "task_type": task_type}],
            "parameters": {"autoTruncate": False, "outputDimensionality": DIMENSIONS},
        }
    ).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    started = time.monotonic()
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"Vertex AI returned HTTP {error.code}") from None
    except URLError as error:
        raise RuntimeError(
            f"Vertex AI transport failed: {type(error.reason).__name__}"
        ) from None
    elapsed_ms = (time.monotonic() - started) * 1000
    try:
        embedding = payload["predictions"][0]["embeddings"]
        stats = embedding["statistics"]
        values = validate_vector(embedding["values"])
        if stats["truncated"] is not False or not isinstance(stats["token_count"], int):
            raise ValueError("provider returned invalid usage or truncated input")
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError("provider returned an unexpected response shape") from error
    return values, stats["token_count"], elapsed_ms


def run_evaluation(labels: dict, embed) -> dict:
    if (
        labels.get("version") != "synthetic-en-v1"
        or len(labels.get("cards", [])) != 10
        or len(labels.get("queries", [])) != 7
    ):
        raise ValueError("unexpected synthetic fixture")
    vectors = {}
    token_counts = []
    latencies_ms = []
    for card in labels["cards"]:
        vector, tokens, latency = embed(canonical_card_text(card), "RETRIEVAL_DOCUMENT")
        vectors[card["id"]] = validate_vector(vector)
        token_counts.append(tokens)
        latencies_ms.append(latency)
    rankings = {}
    for query in labels["queries"]:
        vector, tokens, latency = embed(query["text"], "RETRIEVAL_QUERY")
        query_vector = validate_vector(vector)
        token_counts.append(tokens)
        latencies_ms.append(latency)
        rankings[query["text"]] = sorted(
            vectors,
            key=lambda card_id: (
                -cosine_similarity(query_vector, vectors[card_id]),
                card_id,
            ),
        )
    report = evaluate(labels, rankings)
    ordered = sorted(latencies_ms)
    report["provider"] = "vertex-ai"
    report["model"] = MODEL
    report["dimensions"] = DIMENSIONS
    report["request_count"] = len(token_counts)
    report["input_tokens_reported"] = sum(token_counts)
    report["provider_request_p50_ms"] = round(ordered[len(ordered) // 2], 1)
    report["provider_request_p95_ms"] = round(
        ordered[math.ceil(0.95 * len(ordered)) - 1], 1
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", default="us-central1")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,61}[a-z0-9]", args.project):
        parser.error("invalid project ID")
    if not re.fullmatch(r"[a-z]+-[a-z]+[0-9]", args.location):
        parser.error("invalid location")
    fixture_bytes = FIXTURE.read_bytes()
    if hashlib.sha256(fixture_bytes).hexdigest() != FIXTURE_SHA256:
        raise ValueError(
            "synthetic fixture changed; inspect it before any provider call"
        )
    labels = json.loads(fixture_bytes)
    token = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not token:
        raise RuntimeError("gcloud returned no access token")

    def embed(content: str, task_type: str) -> tuple[list[float], int, float]:
        return request_embedding(
            project=args.project,
            location=args.location,
            token=token,
            content=content,
            task_type=task_type,
        )

    print(json.dumps(run_evaluation(labels, embed), indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
