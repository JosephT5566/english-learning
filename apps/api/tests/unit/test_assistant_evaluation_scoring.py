"""Offline scoring contracts. Evaluation assets live outside pytest collection."""

import importlib.util
import json
from pathlib import Path

import pytest

DIRECTORY = Path(__file__).resolve().parents[4] / "doc/training/issues/70"


def evaluator():
    spec = importlib.util.spec_from_file_location(
        "issue70_evaluate", DIRECTORY / "evaluate.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_assistant_eval_scores_ordered_tools_and_key_arguments():
    score = evaluator().score_calls(
        [
            {
                "name": "search_cards",
                "arguments": {"query": "harbor", "target_language": "en", "limit": 5},
                "status": "ok",
            }
        ],
        [
            {
                "name": "search_cards",
                "arguments": {"query": "harbor", "target_language": "en"},
            }
        ],
    )
    assert score == {"tool_selection_correct": True, "arguments_correct": True}
    assert evaluator().score_calls([], []) == {
        "tool_selection_correct": True,
        "arguments_correct": True,
    }
    wrong = evaluator().score_calls(
        [
            {
                "name": "get_due_cards",
                "arguments": {"target_language": "ja"},
                "status": "ok",
            }
        ],
        [{"name": "get_due_cards", "arguments": {"target_language": "en"}}],
    )
    assert wrong == {"tool_selection_correct": True, "arguments_correct": False}
    assert (
        evaluator().score_calls([], [{"name": "get_review_stats", "arguments": {}}])[
            "tool_selection_correct"
        ]
        is False
    )
    assert (
        evaluator().score_calls(
            [{"name": "get_review_stats", "arguments": {}, "status": "invalid_call"}],
            [{"name": "get_review_stats", "arguments": {}}],
        )["arguments_correct"]
        is False
    )


def test_assistant_eval_offline_replay_is_provisional(monkeypatch):
    import requests

    monkeypatch.setattr(
        requests, "post", lambda *a, **kw: pytest.fail("Network is prohibited")
    )
    module = evaluator()
    cases = json.loads((DIRECTORY / "cases.json").read_text())
    assert len(cases) == 8
    assert all(c["reviewed_by"] is None and c["reviewed_on"] is None for c in cases)
    report = module.run_replay(cases)
    assert report["provisional"] is True
    assert report["model_versions"] == ["scripted-v1"]
    assert report["executed_on"]
    assert report["summary"]["tool_selection_accuracy"] == 1
    assert report["summary"]["arguments_accuracy"] == 1
    assert report["summary"]["average_steps"] > 0
    assert all("latency_ms" in c and "usage" in c for c in report["cases"])
    security = [c for c in report["cases"] if c["security_result"] is not None]
    assert len(security) == 2
    assert all(c["security_result"]["boundary_pass"] for c in security)
    assert any("invalid_call" in str(c["security_result"]) for c in security)


def test_assistant_eval_vertex_requires_flag_environment_and_explicit_model(
    monkeypatch,
):
    module = evaluator()
    monkeypatch.delenv("ENABLE_ISSUE70_VERTEX_EVAL", raising=False)
    with pytest.raises(ValueError, match="ENABLE_ISSUE70_VERTEX_EVAL"):
        module.require_vertex_opt_in(None)
    monkeypatch.setenv("ENABLE_ISSUE70_VERTEX_EVAL", "1")
    with pytest.raises(ValueError, match="model-query-date"):
        module.require_vertex_opt_in(None)


@pytest.mark.parametrize(
    "kind,code", [("no_tool", "provider_unavailable"), ("foreign", "provider_timeout")]
)
def test_assistant_eval_failed_cases_never_count_as_success(kind, code):
    from unittest.mock import Mock

    from app.config import Settings
    from app.generation import GenerationFailure

    module = evaluator()
    provider = Mock(steps=1, versions=set())
    provider.generate.side_effect = GenerationFailure(code)
    case = {
        "id": "failure",
        "kind": kind,
        "messages": [{"role": "user", "content": "synthetic"}],
        "expected_calls": [],
    }
    score = module.evaluate_case(case, provider, Settings(_env_file=None))
    assert score["tool_selection_correct"] is False
    assert score["arguments_correct"] is False
    if kind == "foreign":
        assert score["security_result"]["boundary_pass"] is False


def sse_evaluator(monkeypatch):
    import sys

    module = evaluator()
    monkeypatch.setitem(sys.modules, "evaluate", module)
    spec = importlib.util.spec_from_file_location(
        "issue70_evaluate_sse", DIRECTORY / "evaluate_sse.py"
    )
    stream = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stream)
    return stream


def resolve(value):
    import asyncio
    import inspect

    return asyncio.run(value) if inspect.isawaitable(value) else value


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("cap", [3, 4, 5])
def test_issue70_cap_replay_summary_without_network(monkeypatch, stream, cap):
    import socket

    import requests

    module = sse_evaluator(monkeypatch) if stream else evaluator()

    def forbidden(*args, **kwargs):
        pytest.fail("Replay must not construct Vertex or use network")

    monkeypatch.setattr(module, "VertexGenerationProvider", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    observed_caps = []
    original_run = module.run_assistant

    def run(**kwargs):
        observed_caps.append(kwargs["settings"].assistant_max_steps)
        return original_run(**kwargs)

    monkeypatch.setattr(module, "run_assistant", run)
    cases = json.loads((DIRECTORY / "cases.json").read_text())
    report = resolve(module.run_replay(cases, max_steps=cap))
    assert observed_caps == [cap] * 8
    assert report["max_steps"] == cap
    assert report["configured_model"] == "scripted-v1"
    assert report["location"] and report["executed_on"]
    assert report["model_query_date"] is None
    assert report["provisional"] is True
    summary = report["summary"]
    assert summary["completed_count"] == 8
    assert summary["max_steps_count"] == summary["timeout_count"] == 0
    assert summary["tool_selection_correct_count"] == 8
    assert summary["arguments_correct_count"] == 8
    assert summary["tool_selection_accuracy"] == summary["arguments_accuracy"] == 1
    assert summary["latency_p95_ms"] >= summary["latency_p50_ms"] >= 0
    assert summary["latency_percentile_method"] == (
        "linear interpolation at (n-1)*p on sorted latency_ms, p in [0,1]"
    )
    assert summary["usage"] == {
        key: sum((c["usage"] or {}).get(key) or 0 for c in report["cases"])
        for key in ("input_tokens", "output_tokens", "total_tokens")
    }
    assert summary["usage"]["total_tokens"] > 0
    if stream:
        assert all(c["terminal"]["event"] == "done" for c in report["cases"])
        assert all(c["delta_count"] > 0 for c in report["cases"])
        assert all(
            c["stop_reason"] == c["terminal"]["data"]["stop_reason"]
            for c in report["cases"]
        )
    with pytest.raises(ValueError, match="positive"):
        resolve(module.run_replay(cases, max_steps=0))
    with pytest.raises(ValueError):
        resolve(module.run_replay(cases, max_steps=6))


@pytest.mark.parametrize("stream", [False, True])
def test_issue70_cli_max_steps_defaults_to_replay(monkeypatch, tmp_path, stream):
    import sys

    module = sse_evaluator(monkeypatch) if stream else evaluator()
    path = tmp_path / "report.json"
    monkeypatch.setattr(
        sys, "argv", ["evaluate", "--max-steps", "4", "--output", str(path)]
    )
    module.main()
    report = json.loads(path.read_text())
    assert report["mode"] == "replay" and report["max_steps"] == 4


@pytest.mark.parametrize("stream", [False, True])
def test_issue70_vertex_refuses_before_provider_construction(monkeypatch, stream):
    module = sse_evaluator(monkeypatch) if stream else evaluator()
    gate = evaluator()
    # SSE's imported gate reads this same os module; no actual opt-in is set.
    environment = {}
    monkeypatch.setattr(gate.os, "getenv", environment.get)
    monkeypatch.setattr(
        module, "VertexGenerationProvider", lambda: pytest.fail("Vertex constructed")
    )
    with pytest.raises(ValueError, match="ENABLE_ISSUE70_VERTEX_EVAL"):
        resolve(module.run_vertex([], None, max_steps=4))
    environment["ENABLE_ISSUE70_VERTEX_EVAL"] = "1"
    with pytest.raises(ValueError, match="model-query-date"):
        resolve(module.run_vertex([], None, max_steps=4))
    with pytest.raises(ValueError):
        resolve(module.run_vertex([], "not-a-date", max_steps=4))
    for model, project in [
        (None, None),
        ("synthetic-v1", None),
        (None, "synthetic-project"),
    ]:
        monkeypatch.delenv("GENERATION_MODEL", raising=False)
        monkeypatch.delenv("VERTEX_PROJECT_ID", raising=False)
        if model:
            monkeypatch.setenv("GENERATION_MODEL", model)
        if project:
            monkeypatch.setenv("VERTEX_PROJECT_ID", project)
        with pytest.raises(ValueError, match="GENERATION_MODEL and VERTEX_PROJECT_ID"):
            resolve(module.run_vertex([], "2026-11-13", max_steps=4))


def test_comparison_summary_linear_percentiles_null_usage_and_stop_counts():
    module = evaluator()
    scores = [
        {"latency_ms": latency, "stop_reason": reason, "usage": usage}
        for latency, reason, usage in [
            (
                10,
                "completed",
                {"input_tokens": 4, "output_tokens": None, "total_tokens": 4},
            ),
            (20, "max_steps", None),
            (
                30,
                "timeout",
                {"input_tokens": None, "output_tokens": 2, "total_tokens": 2},
            ),
            (40, None, None),
        ]
    ]
    summary = module.comparison_summary(scores)
    assert (
        summary["completed_count"]
        == summary["max_steps_count"]
        == summary["timeout_count"]
        == 1
    )
    assert summary["latency_p50_ms"] == 25
    assert summary["latency_p95_ms"] == 38.5
    assert summary["usage"] == {
        "input_tokens": 4,
        "output_tokens": 2,
        "total_tokens": 6,
    }
    empty = module.comparison_summary([])
    assert empty["latency_p50_ms"] is empty["latency_p95_ms"] is None
    assert empty["usage"] == {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
