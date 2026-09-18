"""Bounded operational events for the local CSV import commands."""

import json

_OUTCOMES = {
    "completed",
    "rejected",
    "passed",
    "reconciliation_failed",
    "validation_error",
    "database_error",
    "configuration_error",
    "io_error",
    "import_error",
    "unexpected_error",
}


def emit_import_event(
    *,
    operation: str,
    outcome: str,
    phase: str,
    database_committed: bool,
    reports_written: int,
    replayed: bool,
) -> None:
    """Log command state without source data, identities, paths, or hashes."""

    event = {
        "event": "import_command_completed",
        "operation": operation if operation in {"dry_run", "confirmed"} else "unknown",
        "outcome": outcome if outcome in _OUTCOMES else "unexpected_error",
        "phase": phase
        if phase in {"validation", "database", "reconciliation", "report", "done"}
        else "unknown",
        "database_committed": database_committed,
        "reports_written": reports_written if reports_written in {0, 1, 2} else 0,
        "replayed": replayed,
    }
    try:
        print(json.dumps(event, separators=(",", ":")), flush=True)
    except OSError:
        pass
