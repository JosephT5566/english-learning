"""Import CLI events describe committed state without private source values."""

import json
from contextlib import nullcontext
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

import app.confirmed_imports as confirmed
import app.imports as dry_run
from app.import_events import emit_import_event


def _events(capsys: pytest.CaptureFixture[str]) -> list[dict[str, object]]:
    captured = capsys.readouterr()
    assert "private-" not in captured.out + captured.err
    return [json.loads(line) for line in captured.out.splitlines()]


def test_event_allowlist_excludes_private_values(
    capsys: pytest.CaptureFixture[str],
) -> None:
    emit_import_event(
        operation="private-source-namespace",
        outcome="private-card-text",
        phase="private-path",
        database_committed=False,
        reports_written=99,
        replayed=False,
    )

    assert _events(capsys) == [
        {
            "event": "import_command_completed",
            "operation": "unknown",
            "outcome": "unexpected_error",
            "phase": "unknown",
            "database_committed": False,
            "reports_written": 0,
            "replayed": False,
        }
    ]


def test_dry_run_report_failure_retains_committed_truth(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class BrokenReport:
        def write_text(self, *_args: object, **_kwargs: object) -> None:
            raise OSError("private-report-path")

    args = SimpleNamespace(
        csv="private-source-path",
        source_namespace="private-source",
        target_language="en",
        snapshot_captured_at=None,
        owner_id=1,
        deck_id=uuid4(),
        report=BrokenReport(),
    )
    monkeypatch.setattr(dry_run, "_parse_cli_args", lambda: args)
    monkeypatch.setattr(
        dry_run,
        "validate_csv_snapshot",
        lambda *_args, **_kwargs: SimpleNamespace(status="completed"),
    )
    monkeypatch.setattr(dry_run, "load_settings", lambda: object())
    monkeypatch.setattr(dry_run, "create_database_engine", lambda _settings: object())
    monkeypatch.setattr(
        dry_run, "create_database_session_factory", lambda _engine: object()
    )
    monkeypatch.setattr(
        dry_run, "database_transaction", lambda _factory: nullcontext(object())
    )
    monkeypatch.setattr(
        dry_run, "persist_dry_run", lambda *_args, **_kwargs: (uuid4(), True)
    )
    monkeypatch.setattr(dry_run, "dispose_database_engine", lambda _engine: None)
    monkeypatch.setattr(dry_run, "report_as_dict", lambda *_args: {})

    assert dry_run.main() == 2
    assert _events(capsys) == [
        {
            "event": "import_command_completed",
            "operation": "dry_run",
            "outcome": "io_error",
            "phase": "report",
            "database_committed": True,
            "reports_written": 0,
            "replayed": True,
        }
    ]

    def fail_before_commit(*_args: object, **_kwargs: object) -> None:
        raise SQLAlchemyError("private-card-text")

    monkeypatch.setattr(dry_run, "persist_dry_run", fail_before_commit)
    assert dry_run.main() == 2
    assert _events(capsys) == [
        {
            "event": "import_command_completed",
            "operation": "dry_run",
            "outcome": "database_error",
            "phase": "database",
            "database_committed": False,
            "reports_written": 0,
            "replayed": False,
        }
    ]


def test_confirmed_reconciliation_failure_retains_committed_truth(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = SimpleNamespace(
        csv="private-source-path",
        source_namespace="private-source",
        target_language="en",
        snapshot_captured_at=None,
        approved_dry_run_id=uuid4(),
        owner_id=1,
        deck_id=uuid4(),
        validator_version="v1",
        report="report-path",
        reconciliation_report="reconciliation-path",
    )
    monkeypatch.setattr(confirmed, "_parse_cli_args", lambda: args)
    monkeypatch.setattr(
        confirmed,
        "read_validated_csv_snapshot",
        lambda *_args, **_kwargs: SimpleNamespace(
            report=SimpleNamespace(source_namespace="private-source")
        ),
    )
    monkeypatch.setattr(confirmed, "load_settings", lambda: object())
    monkeypatch.setattr(confirmed, "create_database_engine", lambda _settings: object())
    monkeypatch.setattr(
        confirmed, "create_database_session_factory", lambda _engine: object()
    )
    monkeypatch.setattr(confirmed, "dispose_database_engine", lambda _engine: None)
    monkeypatch.setattr(
        confirmed,
        "apply_confirmed_import",
        lambda *_args, **_kwargs: SimpleNamespace(replayed=False),
    )

    def fail_reconciliation(*_args: object, **_kwargs: object) -> None:
        raise OSError("private-card-text")

    monkeypatch.setattr(confirmed, "reconcile_confirmed_import", fail_reconciliation)

    assert confirmed.main() == 2
    assert _events(capsys) == [
        {
            "event": "import_command_completed",
            "operation": "confirmed",
            "outcome": "io_error",
            "phase": "reconciliation",
            "database_committed": True,
            "reports_written": 0,
            "replayed": False,
        }
    ]

    monkeypatch.setattr(
        confirmed,
        "apply_confirmed_import",
        lambda *_args, **_kwargs: SimpleNamespace(replayed=True),
    )
    monkeypatch.setattr(
        confirmed,
        "reconcile_confirmed_import",
        lambda *_args, **_kwargs: SimpleNamespace(status="passed"),
    )
    monkeypatch.setattr(confirmed, "confirmed_import_report_as_dict", lambda *_args: {})
    monkeypatch.setattr(confirmed, "reconciliation_report_as_dict", lambda *_args: {})
    monkeypatch.setattr(confirmed, "_write_report", lambda *_args: None)

    assert confirmed.main() == 0
    assert _events(capsys) == [
        {
            "event": "import_command_completed",
            "operation": "confirmed",
            "outcome": "passed",
            "phase": "done",
            "database_committed": True,
            "reports_written": 2,
            "replayed": True,
        }
    ]
