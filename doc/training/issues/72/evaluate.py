"""Manual extraction evaluation and offline replay; never automatically call Vertex.

Importable by unit tests using a path resolved from __file__, independent of cwd.
This tool contains synthetic content only. It does not load .env files.
"""

import argparse
import json
import os
import sys
import time
import unicodedata
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "apps/api"))

from pydantic import ValidationError

from app.config import Settings
from app.extraction import ExtractionRequest, extraction_prompt
from app.generation import (
    GenerationFailure,
    GenerationRequest,
    GenerationResult,
    GenerationUsage,
    VertexGenerationProvider,
    vertex_response_schema,
)
from app.writes import CardDrafts, CardFields

DIRECTORY = Path(__file__).resolve().parent


def normalize_term(value: str) -> str:
    """NFKC, casefold, trim and collapse Unicode whitespace; retain punctuation."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def score_case(case: dict, result: GenerationResult, *, elapsed_ms: float) -> dict:
    schema_pass, over_limit = True, False
    errors = []
    try:
        CardDrafts.model_validate_json(result.text, strict=True)
    except ValidationError as error:
        schema_pass = False
        errors = [
            item["type"]
            for item in error.errors(include_input=False, include_context=False)
        ]
        over_limit = any(code in {"string_too_long", "too_long"} for code in errors)
    if len(result.text.encode("utf-8")) > 100_000:
        schema_pass = False
        over_limit = True
        errors.append("output_byte_limit")
    try:
        raw = json.loads(result.text)
        cards = raw.get("cards", []) if isinstance(raw, dict) else []
        cards = (
            [card for card in cards if isinstance(card, dict)]
            if isinstance(cards, list)
            else []
        )
    except (ValueError, TypeError):
        cards = []
    actual = {
        normalize_term(card["term"])
        for card in cards
        if isinstance(card.get("term"), str)
    }
    expected = {normalize_term(term) for term in case["expected_terms"]}
    shared = len(actual & expected)
    inputs = case["input"]
    # Provenance is material plus existing drafts, never instruction. Exact source/date
    # containment is a heuristic, not a semantic attribution or correctness judgment.
    provenance = (
        inputs["material"]
        + "\n"
        + json.dumps(inputs.get("drafts", []), ensure_ascii=False)
    )
    fabricated_source = sum(
        bool(card.get("example_source"))
        and str(card["example_source"]) not in provenance
        for card in cards
    )
    fabricated_date = sum(
        bool(card.get("learned_on")) and str(card["learned_on"]) not in provenance
        for card in cards
    )
    unchanged = []
    if case["kind"] == "adjustment":
        for term in case["unchanged_terms"]:
            key = normalize_term(term)
            originals = [
                card for card in inputs["drafts"] if normalize_term(card["term"]) == key
            ]
            matches = [
                card
                for card in cards
                if isinstance(card.get("term"), str)
                and normalize_term(card["term"]) == key
            ]
            same = False
            if len(originals) == len(matches) == 1:
                try:
                    same = (
                        CardFields.model_validate(originals[0]).model_dump()
                        == CardFields.model_validate(matches[0]).model_dump()
                    )
                except ValidationError:
                    pass
            unchanged.append(same)
    return {
        "id": case["id"],
        "kind": case["kind"],
        "schema_pass": schema_pass,
        "schema_error_types": errors,
        "expected_terms": sorted(expected),
        "actual_terms": sorted(actual),
        "recall": ratio(shared, len(expected)) or 0.0,
        "precision": ratio(shared, len(actual)) or 0.0,
        "over_limit": over_limit,
        "fabricated_example_source_rate": ratio(fabricated_source, len(cards)),
        "fabricated_learned_on_rate": ratio(fabricated_date, len(cards)),
        "injection_result": {"schema_pass": schema_pass, "actual_output": result.text}
        if case["kind"] == "injection"
        else None,
        "unchanged_cards_rate": ratio(sum(unchanged), len(unchanged)),
        "latency_ms": elapsed_ms,
        "model_version": result.model,
        "usage": result.usage.model_dump() if result.usage else None,
    }


class ReplayProvider:
    """Scripted provider implementing the generation interface without transport."""

    def __init__(self, recording: dict):
        self.recording = recording

    def generate(self, request: GenerationRequest, **options) -> GenerationResult:
        return GenerationResult(
            text=self.recording["text"],
            model=self.recording["model"],
            usage=GenerationUsage.model_validate(self.recording["usage"])
            if self.recording.get("usage")
            else None,
        )

    def close(self) -> None:
        pass


def generation_input(case: dict) -> GenerationRequest:
    validated = ExtractionRequest.model_validate(case["input"])
    return GenerationRequest(
        system=extraction_prompt("en", "zh-TW"),
        data=validated.model_dump(mode="json", exclude_none=True),
        response_schema=vertex_response_schema(CardDrafts.model_json_schema()),
    )


def make_report(
    cases: list[dict], scores: list[dict], *, mode: str, model_query_date: str | None
) -> dict:
    def average(key):
        values = [score[key] for score in scores if score[key] is not None]
        return sum(values) / len(values) if values else None

    return {
        "mode": mode,
        "provisional": any(
            case["reviewed_by"] is None or case["reviewed_on"] is None for case in cases
        ),
        "executed_on": datetime.now(UTC).isoformat(),
        "model_query_date": model_query_date,
        "model_versions": sorted(
            {score["model_version"] for score in scores if score["model_version"]}
        ),
        "summary": {
            "case_count": len(scores),
            "schema_pass_rate": average("schema_pass"),
            "vocabulary_recall_macro": average("recall"),
            "vocabulary_precision_macro": average("precision"),
            "over_limit_rate": average("over_limit"),
            "fabricated_example_source_rate_macro": average(
                "fabricated_example_source_rate"
            ),
            "fabricated_learned_on_rate_macro": average("fabricated_learned_on_rate"),
            "unchanged_cards_rate_macro": average("unchanged_cards_rate"),
        },
        "cases": scores,
    }


def run_replay(cases: list[dict], recordings: dict) -> dict:
    scores = []
    for case in cases:
        recording = recordings[case["id"]]
        provider = ReplayProvider(recording)
        result = provider.generate(generation_input(case))
        scores.append(score_case(case, result, elapsed_ms=recording["latency_ms"]))
    return make_report(cases, scores, mode="replay", model_query_date=None)


def require_vertex_opt_in(model_query_date: str | None) -> Settings:
    if os.environ.get("ENABLE_ISSUE72_VERTEX_EVAL") != "1":
        raise ValueError(
            "ENABLE_ISSUE72_VERTEX_EVAL=1 is required for real model calls"
        )
    if not model_query_date:
        raise ValueError(
            "--model-query-date is required after checking live model documentation"
        )
    date.fromisoformat(model_query_date)
    settings = Settings(_env_file=None)
    if not settings.generation_model or not settings.vertex_project_id:
        raise ValueError(
            "GENERATION_MODEL and VERTEX_PROJECT_ID must be explicitly set"
        )
    return settings


def run_vertex(cases: list[dict], *, model_query_date: str | None) -> dict:
    settings = require_vertex_opt_in(model_query_date)
    provider = VertexGenerationProvider()
    scores = []
    try:
        for case in cases:
            request = generation_input(case)
            if (
                len(request.data["material"]) > settings.generation_material_max_chars
                or len(request.data.get("instruction", ""))
                > settings.generation_instruction_max_chars
            ):
                raise ValueError("evaluation input exceeds configured limits")
            started = time.perf_counter()
            failure_code = None
            try:
                result = provider.generate(
                    request,
                    model=settings.generation_model,
                    project=settings.vertex_project_id,
                    location=settings.vertex_location,
                    timeout_seconds=settings.generation_timeout_seconds,
                    max_output_tokens=settings.generation_max_output_tokens,
                )
            except GenerationFailure as error:
                failure_code = error.code
                result = GenerationResult(text="", model=settings.generation_model)
            score = score_case(
                case,
                result,
                elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
            )
            score["provider_failure"] = failure_code
            scores.append(score)
    finally:
        provider.close()
    report = make_report(
        cases, scores, mode="vertex", model_query_date=model_query_date
    )
    report["configured_model"] = settings.generation_model
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--vertex",
        action="store_true",
        help="Explicitly enable billed real-model mode; also requires environment opt-in",
    )
    parser.add_argument("--model-query-date")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = json.loads((DIRECTORY / "cases.json").read_text())
    if args.vertex:
        report = run_vertex(cases, model_query_date=args.model_query_date)
    else:
        report = run_replay(
            cases, json.loads((DIRECTORY / "recordings.json").read_text())
        )
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
