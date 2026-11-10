"""Opt-in assistant SSE evaluation using Vertex and the synthetic issue #70 corpus."""

import argparse
import asyncio
import json
import time
from contextlib import aclosing
from datetime import UTC, datetime
from pathlib import Path

from evaluate import (
    DIRECTORY,
    ObservedProvider,
    SyntheticTools,
    require_vertex_opt_in,
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
        event, data = frame.splitlines()[:2]
        elapsed = round((time.monotonic() - started) * 1000, 3)
        if event == "event: delta":
            deltas.append(elapsed)
        else:
            terminal = {
                "event": event.removeprefix("event: "),
                "elapsed_ms": elapsed,
                "data": json.loads(data.removeprefix("data: ")),
            }

    return {
        "id": case["id"],
        "model_versions": sorted(observed.versions),
        "steps": observed.steps,
        "delta_count": len(deltas),
        "first_delta_ms": deltas[0] if deltas else None,
        "last_delta_ms": deltas[-1] if deltas else None,
        "terminal": terminal,
        "synthetic_tool_results": tools.results,
    }


async def evaluate(settings):
    cases = json.loads((DIRECTORY / "cases.json").read_text())
    provider = VertexGenerationProvider()
    try:
        return [await evaluate_case(case, provider, settings) for case in cases]
    finally:
        provider.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-query-date", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    settings = require_vertex_opt_in(args.model_query_date)
    report = {
        "provisional": True,
        "executed_on": datetime.now(UTC).isoformat(),
        "model_query_date": args.model_query_date,
        "configured_model": settings.generation_model,
        "location": settings.effective_generation_location,
        "cases": asyncio.run(evaluate(settings)),
    }
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
