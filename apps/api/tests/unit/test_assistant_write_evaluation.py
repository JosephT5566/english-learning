"""Issue 99 evaluator contracts; no model or database traffic."""

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

DIRECTORY = Path(__file__).resolve().parents[4] / "doc/training/issues/99"


def evaluator():
    spec = importlib.util.spec_from_file_location(
        "issue99_evaluate", DIRECTORY / "evaluate.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_scoring_flags_success_na_and_each_mismatch():
    m = evaluator()
    expected = {"status": "ok", "deck_id": "owned", "terms": ["Café", "bank"]}
    outputs = [
        {"name": "propose_cards", "response": {"status": "ok", "deck_id": "owned"}}
    ]
    parts = [
        {
            "type": "card_proposal",
            "payload": {
                "drafts": [
                    {"term": " BANK ", "meaning": "a riverside"},
                    {"term": " CAFE\u0301 ", "meaning": "coffee shop"},
                ]
            },
        }
    ]
    calls = [{"name": "search_cards"}, {"name": "propose_cards"}]
    assert m.intent_correct({"kind": "write"}, calls, outputs)
    assert not m.intent_correct({"kind": "write"}, [], [])
    assert m.intent_correct({"kind": "no_write"}, [], [])
    assert not m.intent_correct({"kind": "no_write"}, calls, outputs)
    injection = {"kind": "injection", "expected": {"allowed_deck_ids": ["owned"]}}
    assert m.intent_correct(injection, calls, outputs)
    assert not m.intent_correct(
        injection,
        calls,
        [{"name": "propose_cards", "response": {"status": "ok", "deck_id": "foreign"}}],
    )
    assert m.intent_correct(
        injection,
        calls,
        [{"name": "propose_cards", "response": {"error": "deck_not_found"}}],
    )
    assert m.deck_match(expected, outputs, parts)
    assert not m.deck_match({**expected, "deck_id": "wrong"}, outputs, parts)
    assert not m.deck_match(expected, [], [])
    assert m.deck_match({}, [], []) is None
    assert m.deck_match({}, outputs, parts) is False
    assert m.term_set_match(expected, parts)
    assert not m.term_set_match({**expected, "terms": ["bank"]}, parts)
    assert not m.term_set_match({**expected, "terms": ["bank", "extra", "Café"]}, parts)
    assert not m.term_set_match(expected, [])
    assert m.meaning_non_empty(expected, parts)
    bad = deepcopy(parts)
    bad[0]["payload"]["drafts"][0]["meaning"] = "  "
    assert not m.meaning_non_empty(expected, bad)
    assert not m.meaning_non_empty(expected, [])
    for status in [
        "needs_deck",
        "deck_archived",
        "deck_not_found",
        "too_many_cards",
        "invalid_call",
    ]:
        result = [
            {
                "name": "propose_cards",
                "response": {"error" if status != "needs_deck" else "status": status},
            }
        ]
        assert m.deck_match({"status": status}, result, [])
        assert not m.deck_match({"status": status}, outputs, parts)
        assert not m.deck_match({"status": status}, result, parts)
        assert m.term_set_match({"status": status}, []) is None
        assert m.meaning_non_empty({"status": status}, []) is None
    assert m.term_set_match({}, []) is None
    assert m.meaning_non_empty({}, []) is None
    assert m.deck_match({"tool": "ask_clarification"}, [], []) is None


@pytest.mark.parametrize(
    "violation", ["write", "foreign", "insert", "update", "delete", "incomplete"]
)
def test_security_flags_fail_independently(violation):
    m = evaluator()
    options = {
        "completed": True,
        "executed_tiers": ["read", "propose"],
        "mutations": [],
        "parts": [],
        "denied_calls": [],
    }
    assert m.security_result(**options)["boundary_pass"]
    if violation == "write":
        options["executed_tiers"].append("write")
    elif violation == "foreign":
        options["parts"] = [{"payload": {"nested": [m.FOREIGN_CARD_ID]}}]
    elif violation == "incomplete":
        options["completed"] = False
    else:
        options["mutations"] = [violation]
    assert not m.security_result(**options)["boundary_pass"]


def test_committed_replay_network_forbidden_and_case_contracts(monkeypatch):
    import requests

    monkeypatch.setattr(
        requests, "post", lambda *a, **kw: pytest.fail("Network forbidden")
    )
    m = evaluator()
    cases = json.loads((DIRECTORY / "cases.json").read_text())
    assert len(cases) == 21
    assert {
        k: sum(c["kind"] == k for c in cases)
        for k in ("write", "no_write", "injection")
    } == {"write": 12, "no_write": 3, "injection": 6}
    assert all(c["reviewed_by"] is None and c["reviewed_on"] is None for c in cases)
    report = m.run_replay(cases)
    assert report["mode"] == "replay" and report["provisional"] is True
    assert report["executed_on"] and report["model_query_date"] is None
    assert report["summary"]["case_count"] == 21
    for score in report["cases"]:
        assert score["security_result"]["boundary_pass"], score
        assert score["reviewed_by"] is None and score["reviewed_on"] is None
        if score["kind"] != "injection":
            for key in m.SCORE_FLAGS:
                assert score[key] is not False, (score["id"], key, score)
        assert score["stop_reason"] == "completed"
        assert score["steps"] > 0 and score["latency_ms"] >= 0
        assert score["usage"] and score["model_versions"] == ["scripted-v1"]
    by_id = {s["id"]: s for s in report["cases"]}
    assert by_id["write-too-many"]["tool_outputs"] == [
        {"name": "propose_cards", "response": {"error": "too_many_cards"}}
    ]
    assert by_id["write-duplicate-existing"]["expectations_match"]
    assert (
        by_id["inject-write-tool"]["security_result"]["denied_calls"][0]["status"]
        == "invalid_call"
    )
    for id in ("write-title-multi", "write-single-omitted-multi"):
        assert "deck_id" not in by_id[id]["attempts"][0]["args"]
    ambiguous = next(c for c in cases if c["id"] == "write-ambiguous-term")
    assert ambiguous["clarification_pending"] is True
    assert len(by_id[ambiguous["id"]]["parts"][0]["payload"]["drafts"]) in (1, 2)
    assert list((DIRECTORY / "results").iterdir()) == [DIRECTORY / "results/.gitkeep"]


@pytest.mark.parametrize("code", ["provider_unavailable", "provider_timeout"])
def test_provider_failure_is_not_security_or_task_success(code):
    from unittest.mock import Mock

    from app.config import Settings
    from app.generation import GenerationFailure

    m = evaluator()
    provider = Mock()
    provider.generate.side_effect = GenerationFailure(code)
    case = {
        "id": "failure",
        "kind": "no_write",
        "messages": [{"role": "user", "content": "hello"}],
        "expected": {},
        "corpus": "multi_active",
        "reviewed_by": None,
        "reviewed_on": None,
    }
    score = m.evaluate_case(case, provider, Settings(_env_file=None))
    assert not score["intent_correct"]
    assert not score["security_result"]["boundary_pass"]
    assert not score["case_pass"]


def test_vertex_refusals_before_provider_construction(monkeypatch):
    m = evaluator()
    monkeypatch.setattr(
        m,
        "VertexGenerationProvider",
        lambda: pytest.fail("Provider must not be constructed"),
    )
    monkeypatch.delenv("ENABLE_ISSUE99_VERTEX_EVAL", raising=False)
    with pytest.raises(ValueError, match="ENABLE_ISSUE99_VERTEX_EVAL"):
        m.run_vertex([], None)
    monkeypatch.setenv("ENABLE_ISSUE99_VERTEX_EVAL", "1")
    with pytest.raises(ValueError, match="model-query-date"):
        m.run_vertex([], None)
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
            m.run_vertex([], "2026-11-13")


def test_max_steps_override_after_settings_construction(monkeypatch):
    m = evaluator()
    observed = []
    original = m.run_assistant

    def run(**kwargs):
        observed.append(kwargs["settings"].assistant_max_steps)
        return original(**kwargs)

    monkeypatch.setattr(m, "run_assistant", run)
    case = json.loads((DIRECTORY / "cases.json").read_text())[0]
    assert m.run_replay([case], max_steps=5)["cases"][0]["case_pass"]
    assert observed == [5]
    with pytest.raises(ValueError, match="positive"):
        m.run_replay([case], max_steps=0)


def test_corpus_owner_boundary_fresh_selection_and_no_mutations():
    from app.assistant.tools import validate_call
    from app.config import Settings

    m = evaluator()
    multi = m.SyntheticTools("multi_active")
    unique = m.SyntheticTools("unique_active")
    settings = Settings(_env_file=None)
    for name, args in [
        ("search_cards", {"query": "harbor", "target_language": "en"}),
        ("get_due_cards", {"target_language": "en"}),
        ("get_review_stats", {}),
    ]:
        foreign = multi(
            name,
            validate_call(name, {**args, "deck_id": m.FOREIGN_DECK_ID}, settings),
            0,
        )
        assert foreign == (
            {"total_count": 0, "due_count": 0}
            if name == "get_review_stats"
            else {"items": []}
        )
    arguments = validate_call(
        "propose_cards",
        {"cards": [{"term": "harbor", "meaning": "a sheltered port"}]},
        settings,
    )
    assert multi("propose_cards", arguments, 0)["status"] == "needs_deck"
    result = unique("propose_cards", arguments, 0)
    assert result["status"] == "ok" and result["deck_id"] == m.ENGLISH_ID
    assert result["warnings"][0]["code"] == "duplicate_term"
    assert len(unique.cards) == len(multi.cards) == 2
    assert unique.mutations == multi.mutations == []
    for id, error in [
        (m.FOREIGN_DECK_ID, "deck_not_found"),
        (m.ARCHIVED_ID, "deck_archived"),
    ]:
        assert multi("propose_cards", {**arguments, "deck_id": id}, 0) == {
            "error": error
        }


def test_report_counts_failure_and_review_provisional_without_vertex():
    from app.config import Settings

    m = evaluator()
    cases = json.loads((DIRECTORY / "cases.json").read_text())[:1]
    report = m.run_replay(cases)
    scores = report["cases"]
    settings = Settings(_env_file=None)
    assert m.make_report(cases, scores, "vertex", settings)["provisional"] is True
    reviewed = [{**cases[0], "reviewed_by": "reviewer", "reviewed_on": "2026-11-13"}]
    assert m.make_report(reviewed, scores, "vertex", settings)["provisional"] is False
    assert m.make_report(reviewed, scores, "replay", settings)["provisional"] is True
    scores[0]["case_pass"] = False
    assert (
        m.make_report(cases, scores, "replay", settings)["summary"]["passed_count"] == 0
    )
