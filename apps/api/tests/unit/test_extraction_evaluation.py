"""Load evaluation tooling from its repository path; no CI network/model dependency."""

import importlib.util
import json
from pathlib import Path

import pytest

from app.generation import GenerationResult, GenerationUsage

ROOT = Path(__file__).resolve().parents[4]
EVALUATION = ROOT / "doc/training/issues/72"


def evaluator():
    spec = importlib.util.spec_from_file_location(
        "issue72_evaluate", EVALUATION / "evaluate.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_evaluation_normalization_and_scoring():
    module = evaluator()
    assert module.normalize_term("  ＨＡＲＢＯＲ\t LIGHT  ") == "harbor light"
    case = {
        "id": "synthetic",
        "kind": "injection",
        "input": {"material": "harbor"},
        "expected_terms": ["harbor", "shelter"],
    }
    result = GenerationResult(
        text=json.dumps(
            {
                "cards": [
                    {
                        "term": "HARBOR",
                        "meaning": "shelter",
                        "example_sentence": "A boat waits.",
                        "example_source": "invented",
                        "learned_on": "2026-01-01",
                    },
                    {"term": "extra", "meaning": "more"},
                ]
            }
        ),
        model="fake-v1",
        usage=GenerationUsage(total_tokens=9),
    )
    score = module.score_case(case, result, elapsed_ms=3)
    assert score["schema_pass"] is True
    assert score["recall"] == score["precision"] == 0.5
    assert score["fabricated_example_source_rate"] == 0.5
    assert score["fabricated_learned_on_rate"] == 0.5
    assert score["injection_result"]["schema_pass"] is True
    assert score["latency_ms"] == 3
    assert score["usage"]["total_tokens"] == 9


@pytest.mark.parametrize(
    "text,over_limit",
    [
        ("not json", False),
        (json.dumps({"cards": [{"term": "x" * 256, "meaning": "x"}]}), True),
        (json.dumps({"cards": [{"term": "x", "meaning": "x"}] * 21}), True),
        (json.dumps({"cards": [{"term": "x", "meaning": "x", "owner": 1}]}), False),
    ],
)
def test_evaluation_counts_schema_and_limit_failures(text, over_limit):
    score = evaluator().score_case(
        {
            "id": "test",
            "kind": "injection",
            "input": {"material": "x"},
            "expected_terms": ["x"],
        },
        GenerationResult(text=text),
        elapsed_ms=0,
    )
    assert score["schema_pass"] is False
    assert score["over_limit"] is over_limit
    assert score["injection_result"]["schema_pass"] is False


def test_evaluation_adjustment_preservation_and_provenance():
    module = evaluator()
    original = [
        {"term": "harbor", "meaning": "shelter"},
        {"term": "bank", "meaning": "river edge"},
    ]
    case = {
        "id": "adjust",
        "kind": "adjustment",
        "input": {
            "material": "From Field Notes on 2026-01-01.",
            "drafts": original,
            "instruction": "Change harbor",
        },
        "expected_terms": ["harbor", "bank"],
        "unchanged_terms": ["bank"],
    }
    cards = [
        {
            **original[0],
            "meaning": "port",
            "example_sentence": "A boat waits.",
            "example_source": "Field Notes",
            "learned_on": "2026-01-01",
        },
        original[1],
    ]
    passed = module.score_case(
        case, GenerationResult(text=json.dumps({"cards": cards})), elapsed_ms=0
    )
    assert passed["unchanged_cards_rate"] == 1
    assert (
        passed["fabricated_example_source_rate"]
        == passed["fabricated_learned_on_rate"]
        == 0
    )
    cards[1] = {**cards[1], "meaning": "changed without instruction"}
    failed = module.score_case(
        case, GenerationResult(text=json.dumps({"cards": cards})), elapsed_ms=0
    )
    assert failed["unchanged_cards_rate"] == 0


def test_replay_uses_fake_provider_and_reports_provisional_metadata(monkeypatch):
    import requests

    monkeypatch.setattr(
        requests, "post", lambda *args, **kwargs: pytest.fail("network forbidden")
    )
    module = evaluator()
    cases = json.loads((EVALUATION / "cases.json").read_text())
    recordings = json.loads((EVALUATION / "recordings.json").read_text())
    assert len(cases) == 8
    assert all(
        case["reviewed_by"] is None and case["reviewed_on"] is None for case in cases
    )
    report = module.run_replay(cases, recordings)
    assert report["mode"] == "replay"
    assert report["provisional"] is True
    assert report["executed_on"]
    assert report["model_query_date"] is None
    assert report["model_versions"] == ["synthetic-replay-v1"]
    assert len(report["cases"]) == 8
    assert report["summary"]["schema_pass_rate"] == 0.875
    assert report["summary"]["over_limit_rate"] == 0


def test_real_mode_requires_explicit_opt_in(monkeypatch):
    module = evaluator()
    monkeypatch.delenv("ENABLE_ISSUE72_VERTEX_EVAL", raising=False)
    with pytest.raises(ValueError, match="ENABLE_ISSUE72_VERTEX_EVAL"):
        module.require_vertex_opt_in("2026-11-05")
