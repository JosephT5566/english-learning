"""Exercise issue #71's evaluator with synthetic providers only."""

import asyncio
import runpy
import time
from pathlib import Path

import pytest

from app.config import Settings
from app.generation import GenerationFailure, GenerationResult, GenerationStreamChunk

EVALUATOR = Path(__file__).resolve().parents[4] / "doc/training/issues/71/evaluate.py"


@pytest.fixture
def evaluator():
    return runpy.run_path(str(EVALUATOR))


class Provider:
    def __init__(self, decision):
        self.decision = decision
        self.calls = []

    def generate(self, request, **options):
        phase = "decision" if request.response_schema else "planning"
        self.calls.append((phase, request, options))
        if phase == "decision":
            if isinstance(self.decision, Exception):
                raise self.decision
            return GenerationResult(text=self.decision)
        return GenerationResult(text="planning")

    async def stream(self, request, **options):
        self.calls.append(("answer", request, options))
        yield GenerationStreamChunk(text="A synthetic answer.")


def run_case(evaluator, provider, *, case_id="no-tool", group="routed"):
    settings = Settings(
        _env_file=None,
        vertex_project_id="synthetic-project",
        generation_location="global",
    )
    case = next(case for case in evaluator["load_cases"]() if case["id"] == case_id)
    return asyncio.run(
        evaluator["evaluate_case"](case, group, provider, settings, "small", "large")
    )


@pytest.mark.parametrize(
    "decision,expected,route",
    [
        ('{"tier":"small"}', "small", "small"),
        ('{"tier":"large"}', "large", "large"),
        ("invalid", "large", "fallback"),
        ('{"tier":"small","owner_id":99,"tool":"delete_cards"}', "large", "fallback"),
    ],
)
def test_routing_stays_within_model_and_tool_budget(
    evaluator, decision, expected, route
):
    provider = Provider(decision)
    report = run_case(evaluator, provider, case_id="routing-injection")
    assert report["route"] == route
    assert [phase for phase, _, _ in provider.calls] == [
        "decision",
        "planning",
        "answer",
    ]
    assert [options["model"] for _, _, options in provider.calls] == [
        "small",
        expected,
        expected,
    ]
    assert len({options["deadline"] for _, _, options in provider.calls}) == 1
    assert provider.calls[0][1].tools is None
    assert "Ignore" in str(provider.calls[0][1].data)
    assert provider.calls[-1][1].tools_disabled
    assert report["tool_results"] == []


def test_provider_timeout_stops_without_answer_dispatch(evaluator):
    provider = Provider(GenerationFailure("provider_timeout"))
    report = run_case(evaluator, provider)
    assert report["stop_reason"] == "timeout"
    assert [phase for phase, _, _ in provider.calls] == ["decision"]


def test_local_deadline_does_not_admit_late_answer(evaluator):
    class LateDecision(Provider):
        def generate(self, request, **options):
            self.calls.append(("decision", request, options))
            while time.monotonic() < options["deadline"]:
                time.sleep(0.001)
            return GenerationResult(text='{"tier":"small"}')

    provider = LateDecision(None)
    settings = Settings(
        _env_file=None,
        vertex_project_id="synthetic-project",
        assistant_timeout_seconds=1,
    )
    case = next(case for case in evaluator["load_cases"]() if case["id"] == "no-tool")
    report = asyncio.run(
        evaluator["evaluate_case"](case, "routed", provider, settings, "small", "large")
    )
    assert report["stop_reason"] == "timeout"
    assert [phase for phase, _, _ in provider.calls] == ["decision"]


def test_replay_reports_lost_sequential_tool_step_and_cost_coverage(evaluator):
    report = asyncio.run(evaluator["run_replay"]())
    assert report["provisional"]
    assert set(report["groups"]) == {"small", "large", "routed"}
    assert all(
        group["trials"] == len(evaluator["load_cases"]())
        for group in report["groups"].values()
    )
    pairs = {(row["group"], row["id"]): row for row in report["cases"]}
    assert pairs["routed", "two-tools"]["planning_budget_affected"]
    assert not pairs["small", "two-tools"]["planning_budget_affected"]
    assert all(len(row["calls"]) <= 3 for row in report["cases"])
    assert pairs["routed", "no-tool"]["calls"][0]["usage"]["input_tokens"] == 0
    assert pairs["routed", "no-tool"]["calls"][-1]["usage"]["input_tokens"] is None
    assert (
        report["groups"]["routed"]["cost_coverage"]["estimated_calls"]
        < report["groups"]["routed"]["cost_coverage"]["calls"]
    )


def test_error_report_distinguishes_executed_tools_from_missing_summaries(evaluator):
    class FailingAnswer(Provider):
        def generate(self, request, **options):
            if any(turn["role"] == "model" for turn in request.contents):
                return GenerationResult(text="planning")
            call = {"name": "get_review_stats", "args": {"target_language": "en"}}
            return GenerationResult(
                text="", parts=[{"functionCall": call}], function_calls=[call]
            )

        async def stream(self, request, **options):
            yield GenerationStreamChunk(text="partial")
            raise GenerationFailure("invalid_response")

    report = run_case(evaluator, FailingAnswer(None), case_id="stats", group="small")
    assert report["stop_reason"] == "error"
    assert report["tool_calls"] is None
    assert report["security"]["denied_attempts"] is None
    assert report["tool_scores_source"] == "executed"
    assert report["tool_scores"]["tool_selection_correct"]
    assert report["tool_results"][0]["name"] == "get_review_stats"


def test_comparison_modes_pin_protocol_despite_app_environment(evaluator, monkeypatch):
    protocol = {
        "assistant_max_steps": (1, 3),
        "assistant_timeout_seconds": (1, 60),
        "assistant_max_output_tokens": (12, 2048),
        "assistant_max_tool_calls": (1, 3),
        "assistant_tool_limit": (1, 10),
        "generation_timeout_seconds": (1, 30),
    }
    for name, (ambient, _) in protocol.items():
        monkeypatch.setenv(name.upper(), str(ambient))
    monkeypatch.setenv("GENERATION_LOCATION", "us-central1")
    monkeypatch.setenv("ENABLE_ISSUE71_VERTEX_EVAL", "1")
    monkeypatch.setenv("VERTEX_PROJECT_ID", "synthetic-live-project")

    async def capture(mode, settings, provider_factory):
        return mode, settings

    class NoNetworkProvider:
        def close(self):
            pass

    namespace = evaluator["run_replay"].__globals__
    monkeypatch.setitem(namespace, "run_comparison", capture)
    monkeypatch.setitem(namespace, "VertexGenerationProvider", NoNetworkProvider)
    for entrypoint, mode, project in (
        ("run_replay", "replay", "synthetic-project"),
        ("run_vertex", "vertex", "synthetic-live-project"),
    ):
        observed_mode, settings = asyncio.run(evaluator[entrypoint]())
        assert observed_mode == mode
        assert settings.vertex_project_id == project
        assert settings.effective_generation_location == "global"
        assert {name: getattr(settings, name) for name in protocol} == {
            name: expected for name, (_, expected) in protocol.items()
        }
