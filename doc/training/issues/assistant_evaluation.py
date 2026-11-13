"""Shared cap validation and descriptive metrics for offline assistant evaluations."""

from math import ceil, floor

from app.config import Settings


def override_max_steps(settings, max_steps):
    if max_steps is None:
        return settings
    if max_steps < 1:
        raise ValueError("max_steps must be positive")
    # Revalidate the frozen configuration against the production range, 1..5.
    return Settings(
        _env_file=None,
        **{**settings.model_dump(), "assistant_max_steps": max_steps},
    )


def comparison_summary(scores):
    latencies = sorted(s["latency_ms"] for s in scores)

    def percentile(p):
        if not latencies:
            return None
        rank = (len(latencies) - 1) * p
        low, high = floor(rank), ceil(rank)
        return round(
            latencies[low] + (latencies[high] - latencies[low]) * (rank - low), 3
        )

    return {
        "completed_count": sum(s["stop_reason"] == "completed" for s in scores),
        "max_steps_count": sum(s["stop_reason"] == "max_steps" for s in scores),
        "timeout_count": sum(s["stop_reason"] == "timeout" for s in scores),
        "latency_percentile_method": (
            "linear interpolation at (n-1)*p on sorted latency_ms, p in [0,1]"
        ),
        "latency_p50_ms": percentile(0.5),
        "latency_p95_ms": percentile(0.95),
        "usage": {
            key: sum((s["usage"] or {}).get(key) or 0 for s in scores)
            for key in ("input_tokens", "output_tokens", "total_tokens")
        },
    }
