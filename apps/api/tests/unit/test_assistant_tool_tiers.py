"""Permission tiers are enforced before execution, including external executors."""

import json
import time
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.assistant import tools
from app.assistant.loop import run_assistant
from app.config import Settings
from app.generation import GenerationResult


def fake_spec(tier="write"):
    return tools.ToolSpec(
        "fake_tool",
        {"name": "fake_tool", "parameters": {"type": "object"}},
        tools.Filters,
        tier,
    )


def test_registry_has_exact_ordered_read_tiers():
    assert isinstance(tools.REGISTRY, tuple)
    assert [(spec.name, spec.tier, spec.args_model) for spec in tools.REGISTRY] == [
        ("search_cards", "read", tools.SearchArguments),
        ("get_due_cards", "read", tools.DueArguments),
        ("get_review_stats", "read", tools.Filters),
    ]
    with pytest.raises(FrozenInstanceError):
        tools.REGISTRY[0].tier = "write"


@pytest.mark.parametrize("invalid", ["visible_write", "duplicate", "mismatch", "tier"])
def test_registry_builder_rejects_invalid_specs(invalid):
    spec = fake_spec()
    specs, options = [spec], {}
    if invalid == "visible_write":
        options["model_visible_tiers"] = frozenset({"read", "propose", "write"})
    elif invalid == "duplicate":
        specs.append(spec)
    elif invalid == "mismatch":
        specs = [tools.ToolSpec("other", spec.schema, tools.Filters, "read")]
    else:
        specs = [fake_spec("invalid")]
    with pytest.raises(ValueError):
        tools.build_registry(specs, **options)


def test_model_write_call_is_unknown_and_never_executed(monkeypatch, capsys):
    spec = fake_spec()
    monkeypatch.setattr(
        tools, "REGISTRY", tools.build_registry((*tools.REGISTRY, spec))
    )
    executor, session = Mock(), Mock()
    execute = tools.SessionTools(
        session, 1, Settings(_env_file=None), None, executors={spec.name: executor}
    )
    call = {"name": spec.name, "args": {}}
    provider = Mock()
    provider.generate.side_effect = [
        GenerationResult(
            text="", parts=[{"functionCall": call}], function_calls=[call]
        ),
        GenerationResult(text="Done"),
    ]
    response = run_assistant(
        messages=[{"role": "user", "content": "Test"}],
        settings=Settings(_env_file=None),
        provider=provider,
        execute=execute,
        request_id="tier-test",
    )
    for invocation in provider.generate.call_args_list:
        assert spec.name not in [s["name"] for s in invocation.args[0].tools]
    assert [(c.name, c.status) for c in response.tool_calls] == [
        ("unknown", "invalid_call")
    ]
    second = provider.generate.call_args_list[1].args[0]
    assert second.contents[-1]["parts"][0]["functionResponse"]["response"] == {
        "error": "invalid_tool_call"
    }
    executor.assert_not_called()
    session.assert_not_called()
    with pytest.raises(ValueError, match="invalid_tool_call"):
        tools.validate_call(spec.name, {}, Settings(_env_file=None))
    logs = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert logs and all(log["event"] == "assistant_step" for log in logs)
    assert spec.name not in json.dumps(logs)


@pytest.mark.parametrize("name", ["fake_tool", "absent_tool"])
def test_session_refuses_nonvisible_name_without_session_access(monkeypatch, name):
    spec = fake_spec()
    monkeypatch.setattr(
        tools, "REGISTRY", tools.build_registry((*tools.REGISTRY, spec))
    )
    session, executor = Mock(), Mock()
    execute = tools.SessionTools(
        session, 1, None, None, executors={spec.name: executor}
    )
    with pytest.raises(tools.ToolNotModelVisible):
        execute(name, {}, time.monotonic() + 5)
    assert session.mock_calls == []
    executor.assert_not_called()


def test_search_readonly_precedes_first_query_and_post_embedding_ranking(monkeypatch):
    # Require the tier-aware registry as well as the real search transaction path.
    assert tools.REGISTRY[0].tier == "read"
    events = []
    session = Mock()

    def sql(statement, *args):
        statement = str(statement)
        events.append(statement)
        if "eligible_count" in statement:
            return Mock(
                mappings=lambda: Mock(
                    one=lambda: SimpleNamespace(eligible_count=1, indexed_count=1)
                )
            )
        if "ORDER BY e.embedding" in statement:
            return Mock(mappings=lambda: Mock(all=list))
        return Mock()

    session.execute.side_effect = sql
    session.commit.side_effect = lambda: events.append("COMMIT")
    monkeypatch.setattr(
        tools, "require_genai_consent", lambda *_: events.append("CONSENT")
    )
    embedding = Mock()
    embedding.query_embedding.side_effect = lambda *a, **k: (
        events.append("EMBED") or [0.0] * 512
    )
    execute = tools.SessionTools(
        session,
        1,
        Settings(_env_file=None, vertex_project_id="synthetic-project"),
        embedding,
    )
    execute(
        "search_cards",
        {"query": "harbor", "target_language": "en"},
        time.monotonic() + 5,
    )
    readonly = [
        i for i, value in enumerate(events) if value == "SET TRANSACTION READ ONLY"
    ]
    coverage = next(i for i, value in enumerate(events) if "eligible_count" in value)
    ranking = next(
        i for i, value in enumerate(events) if "ORDER BY e.embedding" in value
    )
    assert len(readonly) == 2
    assert events.index("CONSENT") < events.index("COMMIT") < readonly[0] < coverage
    assert coverage < events.index("EMBED") < readonly[1] < ranking
    assert events[events.index("EMBED") - 1] == "COMMIT"
    session.rollback.assert_called_once()
