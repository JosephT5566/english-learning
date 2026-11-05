"""Frozen-vector validation, existing scoring, and CI-readable reports. No provider I/O."""

import hashlib
import importlib.util
import json
from datetime import datetime
from pathlib import Path

from app.embeddings import validate_vector
from app.semantic_text import DIMENSIONS, MODEL_VERSION

ROOT = Path(__file__).resolve().parents[4]
LABELS = ROOT / "doc/training/issues/issue-38/relevance.json"
VECTORS = Path(__file__).with_name("fixtures") / "synthetic-en-v1.vectors.json"
REPORT_DIR = ROOT / "apps/api/retrieval-eval-report"
THRESHOLD = 0.75
FIX_COMMAND = (
    "python3 doc/training/issues/issue-38/evaluate_vertex.py --project <ID> "
    "--dump-vectors apps/api/tests/eval/fixtures/synthetic-en-v1.vectors.json"
)

# Import the original scorer directly, without copying its metric or importing a provider runner.
_spec = importlib.util.spec_from_file_location(
    "issue38_scorer", LABELS.with_name("evaluate.py")
)
_scorer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_scorer)
evaluate = _scorer.evaluate


def initial_report(labels: dict) -> dict:
    return {
        "threshold": THRESHOLD,
        "macro_ndcg_at_5": None,
        "fixture_sha_status": "not checked",
        "relevance_sha256": hashlib.sha256(LABELS.read_bytes()).hexdigest(),
        "per_query": [
            {"query": query["text"], "ndcg_at_5": None} for query in labels["queries"]
        ],
        "below_threshold": [],
        "fix_command": FIX_COMMAND,
        "error": None,
    }


def load_vectors(labels: dict, report: dict, path: Path = VECTORS) -> dict:
    if not path.is_file():
        report["fixture_sha_status"] = "unavailable: vector fixture missing"
        raise AssertionError(
            f"Missing frozen vector fixture: {path}. Run from repository root:\n{FIX_COMMAND}\nThen commit the fixture before merging."
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    actual_sha = payload.get("relevance_sha256")
    report["fixture_relevance_sha256"] = actual_sha
    report["fixture_sha_status"] = (
        "match" if actual_sha == report["relevance_sha256"] else "MISMATCH"
    )
    assert report["fixture_sha_status"] == "match", (
        "relevance.json SHA-256 does not match the frozen vector fixture"
    )
    assert payload["schema_version"] == 1, "unsupported vector fixture schema"
    assert payload["model"] == "gemini-embedding-001", "unexpected embedding model"
    assert payload["dim"] == DIMENSIONS, "unexpected embedding dimension"
    assert payload["model_version"] == MODEL_VERSION, (
        "stale MODEL_VERSION; regenerate vectors"
    )
    assert datetime.fromisoformat(payload["created_at"]).utcoffset() is not None, (
        "creation time must include timezone"
    )
    assert set(payload["cards"]) == {card["id"] for card in labels["cards"]}
    assert set(payload["queries"]) == {query["text"] for query in labels["queries"]}
    for vectors in (payload["cards"], payload["queries"]):
        for key, vector in vectors.items():
            vectors[key] = validate_vector(vector)
    return payload


def score_rankings(labels: dict, rankings: dict, report: dict) -> None:
    report.update(evaluate(labels, rankings))
    report["below_threshold"] = [
        row["query"] for row in report["per_query"] if row["ndcg_at_5"] < THRESHOLD
    ]


def write_report(report: dict, directory: Path = REPORT_DIR) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    score = report["macro_ndcg_at_5"]
    rows = [
        "# Retrieval evaluation",
        "",
        f"Macro nDCG@5: {score if score is not None else 'unavailable'}; required >= {THRESHOLD}.",
        f"Fixture SHA status: {report['fixture_sha_status']}.",
        f"relevance.json SHA-256: {report['relevance_sha256']}.",
        "",
        "| Query | nDCG@5 | Below 0.75 |",
        "| --- | --- | --- |",
    ]
    for row in report["per_query"]:
        score = row["ndcg_at_5"]
        below = "unavailable" if score is None else str(score < THRESHOLD).lower()
        rows.append(
            f"| {row['query']} | {score if score is not None else 'unavailable'} | {below} |"
        )
    rows.extend(
        [
            "",
            "Queries below threshold: "
            + (", ".join(report["below_threshold"]) or "none measured"),
            "",
        ]
    )
    if report["error"]:
        rows.extend(["Failure:", "", str(report["error"]), ""])
    rows.extend(
        [
            "To generate or replace the synthetic fixture, run from repository root:",
            "",
            "```sh",
            report["fix_command"],
            "```",
            "",
            "Commit the fixture before merging. Never adjust relevance labels to fit results.",
            "",
        ]
    )
    (directory / "report.md").write_text("\n".join(rows), encoding="utf-8")
