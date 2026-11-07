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
