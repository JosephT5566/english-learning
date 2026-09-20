"""Check the Issue #38 offline relevance metric, without provider calls."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).parents[4]
    / "doc"
    / "training"
    / "issues"
    / "issue-38"
    / "evaluate.py"
)
spec = importlib.util.spec_from_file_location("issue_38_evaluate", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_perfect_and_reversed_ranking() -> None:
    relevance = {"c1": 2, "c2": 1, "c3": 0}
    assert module.ndcg_at_k(["c1", "c2", "c3"], relevance) == 1
    assert module.strong_recall_at_k(["c3", "c2", "c1"], relevance, 2) == 0
    assert module.ndcg_at_k(["c3", "c2", "c1"], relevance) < 1


def test_unknown_or_duplicate_results_are_rejected() -> None:
    labels = {
        "version": "test",
        "cards": [{"id": "c1"}, {"id": "c2"}],
        "queries": [{"text": "q", "relevance": {"c1": 2}}],
    }
    with pytest.raises(ValueError, match="duplicate or unknown"):
        module.evaluate(labels, {"q": ["c1", "c1"]})
    with pytest.raises(ValueError, match="duplicate or unknown"):
        module.evaluate(labels, {"q": ["other"]})


def test_synthetic_fixture_and_lexical_baseline() -> None:
    labels = json.loads(SCRIPT.with_name("relevance.json").read_text(encoding="utf-8"))
    rankings = {
        item["text"]: module.lexical_baseline(labels["cards"], item["text"])
        for item in labels["queries"]
    }
    report = module.evaluate(labels, rankings)
    assert report["query_count"] == 7
    assert report["macro_ndcg_at_5"] == 0.5655
    assert report["macro_strong_recall_at_5"] == 0.6429
