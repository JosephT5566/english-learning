"""Offline replay or explicitly opted-in Vertex SSE on the synthetic #70 corpus."""

import argparse
import asyncio
import json
import time
from contextlib import aclosing
from pathlib import Path

from evaluate import (
    DIRECTORY,
    ObservedProvider,
    ReplayProvider,
    SyntheticTools,
    make_report,
    override_max_steps,
    replay_settings,
    require_vertex_opt_in,
    score_calls,
)

# isort: split

from app.assistant.loop import run_assistant
from app.assistant.sse import stream_events
from app.generation import VertexGenerationProvider


class ObservedStream(ObservedProvider):
    async def stream(self, request, **options):
        self.steps += 1
        async with aclosing(self.provider.stream(request, **options)) as chunks:
            async for chunk in chunks:
                if chunk.model:
                    self.versions.add(chunk.model)
                yield chunk


async def evaluate_case(case, provider, settings):
    observed = ObservedStream(provider)
    tools = SyntheticTools()
    started = time.monotonic()
    deadline = started + settings.assistant_timeout_seconds

    def prepare(cancelled):
        return run_assistant(
            messages=case["messages"],
            settings=settings,
            provider=observed,
            execute=tools,
            request_id=case["id"],
            deadline=deadline,
            prepare_final=True,
            cancelled=cancelled,
        )

    deltas = []
    terminal = None
    async for frame in stream_events(prepare, observed, settings, deadline, case["id"]):
        if not hasattr(frame, "name"):
            continue  # Planning heartbeat, not a data event.
        elapsed = round((time.monotonic() - started) * 1000, 3)
        if frame.name == "delta":
            deltas.append(elapsed)
        elif frame.name in {"done", "error"}:
            terminal = {
                "event": frame.name,
                "elapsed_ms": elapsed,
                "data": frame.data,
            }

    body = terminal["data"] if terminal else {}
    permitted = [
        c
        for c in body.get("tool_calls", [])
        if c["status"] in {"ok", "tool_unavailable"}
    ]
    score = score_calls(permitted, case["expected_calls"])
    if body.get("stop_reason") != "completed":
        score = {"tool_selection_correct": False, "arguments_correct": False}
    return {
        "id": case["id"],
        **score,
        "stop_reason": body.get("stop_reason"),
        "usage": body.get("usage"),
        "latency_ms": terminal["elapsed_ms"]
        if terminal
        else round((time.monotonic() - started) * 1000, 3),
        "model_versions": sorted(observed.versions),
        "steps": observed.steps,
        "delta_count": len(deltas),
        "first_delta_ms": deltas[0] if deltas else None,
        "last_delta_ms": deltas[-1] if deltas else None,
        "terminal": terminal,
        "synthetic_tool_results": tools.results,
    }


async def run_replay(cases, max_steps=None):
    settings = replay_settings(max_steps)
    scores = [
        await evaluate_case(case, ReplayProvider(case["script"]), settings)
        for case in cases
    ]
    return make_report(cases, scores, "replay", settings)


async def run_vertex(cases, model_query_date, max_steps=None):
    settings = override_max_steps(require_vertex_opt_in(model_query_date), max_steps)
    provider = VertexGenerationProvider()
    try:
        scores = [await evaluate_case(case, provider, settings) for case in cases]
    finally:
        provider.close()
    return make_report(cases, scores, "vertex", settings, model_query_date)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vertex", action="store_true")
    parser.add_argument("--max-steps", type=int)
    parser.add_argument("--model-query-date")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    cases = json.loads((DIRECTORY / "cases.json").read_text())
    report = asyncio.run(
        run_vertex(cases, args.model_query_date, args.max_steps)
        if args.vertex
        else run_replay(cases, args.max_steps)
    )
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
