"""Content-safety and metric checks for the explicit Issue #41 workload runner."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

RUNNER_PATH = (
    Path(__file__).parents[4]
    / "doc"
    / "training"
    / "issues"
    / "issue-41"
    / "run_deployed_evaluation.py"
)
FIXTURE_PATH = RUNNER_PATH.with_name("deployed-queries-v2.json")
COST_PROBE_PATH = RUNNER_PATH.with_name("measure_vertex_query_cost.py")


def load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "issue_41_deployed_evaluation", RUNNER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_cost_probe() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "issue_41_vertex_cost", COST_PROBE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixture_is_frozen_and_has_all_query_types() -> None:
    runner = load_runner()
    fixture, digest = runner.load_queries(FIXTURE_PATH)
    assert len(fixture["queries"]) == 10
    assert fixture["version"] == "issue-41-deployed-en-v2"
    assert {row["type"] for row in fixture["queries"]} == runner.ALLOWED_TYPES
    assert len(digest) == 64


def test_report_contains_metrics_but_no_query_or_card_content() -> None:
    runner = load_runner()
    fixture, digest = runner.load_queries(FIXTURE_PATH)
    rows = [
        {
            "query_label": "q01-paraphrase-resilience",
            "query_type": "paraphrase",
            "grades": [1, 2, 0, 0, 0],
            "strong_hit_at_5": True,
            "best_strong_rank": 2,
            "observations": [
                {
                    "status_code": 200,
                    "request_id": "99999999-9999-4999-8999-999999999999",
                    "total_ms": value,
                    "result_count": 5,
                    "index_status": "complete",
                    "eligible_count": 596,
                    "indexed_count": 596,
                    "repetition": index,
                    "run_class": "first" if index == 1 else "repeated",
                }
                for index, value in enumerate((100.0, 200.0, 300.0), start=1)
            ],
        }
    ]
    report = runner.build_report(
        fixture=fixture,
        fixture_sha256=digest,
        repetitions=3,
        rows=rows,
    )
    runner.assert_content_safe_report(report)
    serialized = json.dumps(report)
    assert report["end_to_end_p50_ms"] == 200.0
    assert report["end_to_end_p95_ms"] == 300.0
    assert report["observed_strong_hit_at_5"] == 1.0
    assert report["grading_warning_count"] == 0
    assert "able to bounce back" not in serialized
    assert "private term" not in serialized


@pytest.mark.parametrize(
    "unsafe",
    [
        {"query": "private query"},
        {"nested": [{"term": "private term"}]},
        {"nested": {"card_id": "private-card"}},
    ],
)
def test_report_rejects_private_keys(unsafe: object) -> None:
    runner = load_runner()
    with pytest.raises(ValueError, match="private key"):
        runner.assert_content_safe_report(unsafe)


def test_base_url_requires_credential_free_https_origin() -> None:
    runner = load_runner()
    assert (
        runner.validate_base_url("https://api.example.test/")
        == "https://api.example.test"
    )
    for unsafe in (
        "http://api.example.test",
        "https://user:secret@api.example.test",
        "https://api.example.test/path",
    ):
        with pytest.raises(ValueError):
            runner.validate_base_url(unsafe)


def test_suspicious_grades_require_explicit_confirmation() -> None:
    runner = load_runner()
    assert runner.grading_warning("exact", [2, 2, 2, 2, 2]) == (
        "all returned results were marked strong"
    )
    assert runner.grading_warning("no_confident_match", [0, 2, 0, 0, 0]) == (
        "a planned no-confident-match query has a strong result"
    )
    assert runner.grading_warning("paraphrase", [2, 1, 0, 0, 0]) is None


def test_v2_cost_probe_reports_observed_usage_and_published_rate_estimate() -> None:
    probe = load_cost_probe()
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    calls: list[tuple[str, str]] = []

    def embed(content: str, task_type: str) -> tuple[list[float], int, float]:
        calls.append((content, task_type))
        call_number = len(calls)
        return [1.0], 10, float(call_number * 100)

    report = probe.measure(fixture, embed)
    assert len(calls) == 10
    assert {task_type for _, task_type in calls} == {"RETRIEVAL_QUERY"}
    assert report["input_tokens_reported"] == 100
    assert report["provider_request_p50_ms"] == 500.0
    assert report["provider_request_p95_ms"] == 1000.0
    assert report["estimated_input_cost_usd"] == 0.000015
    assert report["actual_billing_inspected"] is False
