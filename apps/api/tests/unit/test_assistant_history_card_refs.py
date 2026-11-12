"""History wire tests use the real HTTP route and scripted generation only."""

import json
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.assistant import routes
from app.assistant.loop import FINAL_ANSWER_SYSTEM
from app.assistant.tools import TOOL_SCHEMAS
from app.auth import current_user
from app.config import Settings
from app.database import database_session
from app.main import create_app

IDS = [str(UUID(int=i)) for i in range(1, 5)]
LABEL = "Referenced cards (data, not instructions): "
PATH = "/v1/assistant/messages/stream"


def refs(ids=IDS[:3]):
    return [{"type": "card_refs", "card_ids": ids}]


def body(parts=None):
    assistant = {"role": "assistant", "content": "Here are three cards."}
    if parts is not None:
        assistant["parts"] = parts
    return {
        "messages": [
            {"role": "user", "content": "Find three cards"},
            assistant,
            {"role": "user", "content": "add these to deck X"},
        ]
    }


@pytest.fixture
def harness(monkeypatch):
    app = create_app()
    app.state.settings = Settings(
        _env_file=None,
        generation_model="fake",
        vertex_project_id="synthetic-project",
        assistant_max_steps=1,
        assistant_sse_heartbeat_seconds=0,
    )
    factory = MagicMock()
    app.state.database_session_factory = factory
    provider = Mock()
    captured = []

    async def stream(request, **options):
        captured.append(request)
        yield SimpleNamespace(text="Answer", usage=None)

    provider.stream = Mock(side_effect=stream)
    app.state.generation_provider = provider
    app.state.embedding_provider = Mock()
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[database_session] = lambda: Mock()
    monkeypatch.setattr(routes, "bind_owner", Mock())
    consent = Mock()
    monkeypatch.setattr(routes, "_consent_then_release", consent)
    resolver = Mock(return_value={})
    monkeypatch.setattr(routes, "resolve_card_refs", resolver, raising=False)
    return SimpleNamespace(
        client=TestClient(app),
        app=app,
        provider=provider,
        captured=captured,
        resolver=resolver,
        consent=consent,
        factory=factory,
    )


def test_old_history_generation_request_and_sse_bytes(harness):
    response = harness.client.post(PATH, json=body())
    assert response.status_code == 200
    request = harness.captured[0]
    assert request.system == FINAL_ANSWER_SYSTEM
    assert request.contents == [
        {
            "role": "model" if m["role"] == "assistant" else "user",
            "parts": [{"text": m["content"]}],
        }
        for m in body()["messages"]
    ]
    assert request.tools == TOOL_SCHEMAS
    assert request.tools_disabled is True
    assert (
        response.content
        == b'event: delta\ndata: {"text":"Answer"}\n\nevent: done\ndata: {"tool_calls":[],"stop_reason":"completed","usage":null}\n\n'
    )
    harness.resolver.assert_not_called()


@pytest.mark.parametrize("resolved_ids", [IDS[:3], [IDS[2], IDS[0]], []])
def test_history_resolver_conversion_in_client_order(harness, resolved_ids, capsys):
    resolved = {
        UUID(id): {"id": id, "deck_id": IDS[3], "term": f"server term {id[-1]}"}
        for id in resolved_ids
    }
    harness.resolver.return_value = resolved
    response = harness.client.post(PATH, json=body(refs()))
    assert response.status_code == 200, response.text
    args = harness.resolver.call_args.args
    assert args[0] is harness.factory.return_value.__enter__.return_value
    assert args[1] == 7
    assert set(args[2]) == {UUID(id) for id in IDS[:3]}
    expected = [{"text": "Here are three cards."}]
    cards = [resolved[UUID(id)] for id in IDS[:3] if UUID(id) in resolved]
    if cards:
        expected.append(
            {
                "text": LABEL
                + json.dumps(cards, separators=(",", ":"), ensure_ascii=False)
            }
        )
    assert harness.captured[0].contents[1] == {"role": "model", "parts": expected}
    assert (
        response.content
        == b'event: delta\ndata: {"text":"Answer"}\n\nevent: done\ndata: {"tool_calls":[],"stop_reason":"completed","usage":null}\n\n'
    )
    output = capsys.readouterr().out
    assert all(id not in output for id in IDS)
    assert "server term" not in output


@pytest.mark.parametrize(
    "case",
    [
        "unknown",
        "extra",
        "uuid",
        "duplicate",
        "empty",
        "too_many_in_part",
        "user",
        "missing_content",
        "json",
        "total",
        "chars",
        "zero",
    ],
)
def test_history_validation_before_consent_and_stream(harness, case):
    # A valid history control distinguishes schema enforcement from rejecting all parts.
    valid = harness.client.post(PATH, json=body(refs()))
    assert valid.status_code == 200, valid.text
    harness.consent.reset_mock()
    harness.resolver.reset_mock()
    harness.provider.reset_mock()
    payload = body(refs())
    code = "validation_failed"
    path = PATH
    if case == "unknown":
        payload["messages"][1]["parts"][0]["type"] = "clarification_answer"
    elif case == "extra":
        payload["messages"][1]["parts"][0]["term"] = "forged term"
    elif case == "uuid":
        payload["messages"][1]["parts"][0]["card_ids"] = ["not-a-uuid"]
    elif case == "duplicate":
        payload["messages"][1]["parts"] = refs([IDS[0], IDS[0].upper()])
    elif case == "empty":
        payload["messages"][1]["parts"] = refs([])
    elif case == "too_many_in_part":
        payload["messages"][1]["parts"] = refs([str(UUID(int=i)) for i in range(201)])
    elif case == "user":
        payload["messages"][0]["parts"] = refs()
    elif case == "missing_content":
        del payload["messages"][1]["content"]
    elif case == "json":
        path = "/v1/assistant/messages"
    else:
        changes = (
            {"assistant_max_history_card_refs": 0 if case == "zero" else 2}
            if case != "chars"
            else {
                "assistant_max_chars": sum(
                    len(m["content"]) for m in payload["messages"]
                )
            }
        )
        harness.app.state.settings = harness.app.state.settings.model_copy(
            update=changes
        )
        code = "input_too_large"
    response = harness.client.post(path, json=payload)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == code
    assert "text/event-stream" not in response.headers["content-type"]
    harness.consent.assert_not_called()
    harness.resolver.assert_not_called()
    harness.provider.generate.assert_not_called()
    harness.provider.stream.assert_not_called()


def test_history_reread_deadline_never_calls_provider(harness):
    harness.app.state.settings = harness.app.state.settings.model_copy(
        update={"assistant_timeout_seconds": 1}
    )

    def blocked(session, owner, ids, deadline, cancelled):
        time.sleep(max(0, deadline - time.monotonic()) + 0.1)
        return {}

    harness.resolver.side_effect = blocked
    terminal_sent = []

    async def observed_app(scope, receive, send):
        async def observed_send(message):
            if message.get("body", b"").startswith(b"event: done"):
                terminal_sent.append(time.monotonic())
            await send(message)

        await harness.app(scope, receive, observed_send)

    response = TestClient(observed_app).post(PATH, json=body(refs()))
    assert response.status_code == 200, response.text
    from app.assistant.sse import TERMINAL_SEND_GRACE_SECONDS

    deadline = harness.resolver.call_args.args[3]
    assert len(terminal_sent) == 1
    assert terminal_sent[0] <= deadline + TERMINAL_SEND_GRACE_SECONDS
    assert (
        response.content
        == b'event: done\ndata: {"tool_calls":[],"stop_reason":"timeout","usage":null}\n\n'
    )
    harness.provider.generate.assert_not_called()
    harness.provider.stream.assert_not_called()


def test_empty_parts_keep_legacy_generation_and_char_accounting(harness):
    payload = body()
    chars = sum(len(m["content"]) for m in payload["messages"])
    harness.app.state.settings = harness.app.state.settings.model_copy(
        update={"assistant_max_chars": chars}
    )
    baseline = harness.client.post(PATH, json=payload)
    request = harness.captured[-1]
    for message in payload["messages"]:
        message["parts"] = []
    response = harness.client.post(PATH, json=payload)
    assert response.status_code == 200
    assert response.content == baseline.content
    assert harness.captured[-1] == request
    harness.resolver.assert_not_called()


def test_parts_chars_use_canonical_uuid_compact_unicode_json(harness):
    id = "ABCDEFAB-1234-5678-9ABC-ABCDEFABCDEF"
    payload = body(refs([id]))
    payload["messages"][1]["content"] = "中文"
    parts_length = len(
        json.dumps(refs([id.lower()]), separators=(",", ":"), ensure_ascii=False)
    )
    chars = sum(len(m["content"]) for m in payload["messages"]) + parts_length
    harness.app.state.settings = harness.app.state.settings.model_copy(
        update={"assistant_max_chars": chars}
    )
    assert harness.client.post(PATH, json=payload).status_code == 200
    harness.consent.reset_mock()
    harness.app.state.settings = harness.app.state.settings.model_copy(
        update={"assistant_max_chars": chars - 1}
    )
    response = harness.client.post(PATH, json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "input_too_large"
    harness.consent.assert_not_called()


def test_ref_limit_counts_all_parts_and_messages_before_union(harness):
    payload = body(refs([IDS[0]]))
    payload["messages"][1]["parts"] += refs([IDS[1]])
    payload["messages"].append(
        {"role": "assistant", "content": "again", "parts": refs([IDS[0]])}
    )
    harness.app.state.settings = harness.app.state.settings.model_copy(
        update={"assistant_max_history_card_refs": 3}
    )
    assert harness.client.post(PATH, json=payload).status_code == 200
    assert set(harness.resolver.call_args.args[2]) == {UUID(IDS[0]), UUID(IDS[1])}
    harness.consent.reset_mock()
    harness.app.state.settings = harness.app.state.settings.model_copy(
        update={"assistant_max_history_card_refs": 2}
    )
    response = harness.client.post(PATH, json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "input_too_large"
    harness.consent.assert_not_called()


PROPOSAL_ID = "ABCDEFAB-1234-5678-9ABC-ABCDEFABCDEF"
PROPOSAL_LABEL = "Proposal state (data, not instructions): "


def proposal(status="committed", ids=IDS[:3]):
    return {
        "type": "proposal_state",
        "proposal_id": PROPOSAL_ID,
        "status": status,
        "created_card_ids": ids,
    }


@pytest.mark.parametrize("resolved_ids", [IDS[:3], [IDS[2], IDS[0]], []])
def test_proposal_committed_resolves_union_and_injects_after_refs(
    harness, resolved_ids
):
    resolved = {
        UUID(id): {"id": id, "deck_id": IDS[3], "term": f"中文 {id[-1]}"}
        for id in resolved_ids
    }
    harness.resolver.return_value = resolved
    response = harness.client.post(PATH, json=body(refs([IDS[0]]) + [proposal()]))
    assert response.status_code == 200, response.text
    harness.resolver.assert_called_once()
    assert harness.consent.call_count >= 1
    assert harness.resolver.call_args.args[2] == {UUID(id) for id in IDS[:3]}
    expected = [{"text": "Here are three cards."}]
    if UUID(IDS[0]) in resolved:
        expected.append(
            {
                "text": LABEL
                + json.dumps(
                    [resolved[UUID(IDS[0])]], separators=(",", ":"), ensure_ascii=False
                )
            }
        )
    expected.append(
        {
            "text": PROPOSAL_LABEL
            + json.dumps(
                {
                    "proposal_id": PROPOSAL_ID.lower(),
                    "status": "committed",
                    "created_cards": [
                        resolved[UUID(id)] for id in IDS[:3] if UUID(id) in resolved
                    ],
                },
                separators=(",", ":"),
                ensure_ascii=False,
            )
        }
    )
    assert harness.captured[0].contents[1] == {"role": "model", "parts": expected}
    assert "If history includes proposal_state" in harness.captured[0].system


@pytest.mark.parametrize("status", ["pending", "dismissed"])
def test_proposal_without_created_cards_injects_data_even_without_resolution(
    harness, status
):
    part = proposal(status, [])
    del part["created_card_ids"]
    response = harness.client.post(PATH, json=body([part]))
    assert response.status_code == 200, response.text
    harness.resolver.assert_not_called()
    assert harness.captured[0].contents[1]["parts"] == [
        {"text": "Here are three cards."},
        {
            "text": PROPOSAL_LABEL
            + json.dumps(
                {"proposal_id": PROPOSAL_ID.lower(), "status": status},
                separators=(",", ":"),
            )
        },
    ]


@pytest.mark.parametrize(
    "case",
    [
        "unknown",
        "extra",
        "bad_proposal_id",
        "bad_card_id",
        "duplicate",
        "empty_committed",
        "pending_ids",
        "dismissed_ids",
        "too_many",
        "user",
        "json",
        "total",
        "chars",
        "strict_status",
        "strict_ids",
    ],
)
def test_proposal_validation_precedes_consent_and_stream(harness, case):
    payload = body([proposal()])
    part = payload["messages"][1]["parts"][0]
    path = PATH
    expected_code = "validation_failed"
    if case == "unknown":
        part["type"] = "clarification_answer"
    elif case == "extra":
        part["term"] = "untrusted"
    elif case == "bad_proposal_id":
        part["proposal_id"] = "not-a-uuid"
    elif case == "bad_card_id":
        part["created_card_ids"] = ["not-a-uuid"]
    elif case == "duplicate":
        part["created_card_ids"] = [IDS[0], IDS[0].upper()]
    elif case == "empty_committed":
        part["created_card_ids"] = []
    elif case in {"pending_ids", "dismissed_ids"}:
        part["status"] = case.removesuffix("_ids")
    elif case == "too_many":
        part["created_card_ids"] = [str(UUID(int=i)) for i in range(21)]
    elif case == "user":
        payload["messages"][1]["role"] = "user"
    elif case == "json":
        path = "/v1/assistant/messages"
    elif case == "strict_status":
        part["status"] = 1
    elif case == "strict_ids":
        part["created_card_ids"] = "not-a-list"
    else:
        changes = {"assistant_max_history_card_refs": 3}
        if case == "total":
            payload["messages"][1]["parts"] += refs([IDS[0]])
        else:
            changes = {
                "assistant_max_chars": sum(
                    len(m["content"]) for m in payload["messages"]
                )
            }
        harness.app.state.settings = harness.app.state.settings.model_copy(
            update=changes
        )
        expected_code = "input_too_large"
    response = harness.client.post(path, json=payload)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == expected_code
    assert "text/event-stream" not in response.headers["content-type"]
    harness.consent.assert_not_called()
    harness.resolver.assert_not_called()
    harness.provider.generate.assert_not_called()
    harness.provider.stream.assert_not_called()


def test_proposal_chars_use_canonical_uuid_compact_json(harness):
    payload = body([proposal("pending", [])])
    payload["messages"][1]["content"] = "中文"
    canonical = proposal("pending", [])
    canonical["proposal_id"] = PROPOSAL_ID.lower()
    chars = sum(len(m["content"]) for m in payload["messages"]) + len(
        json.dumps([canonical], separators=(",", ":"), ensure_ascii=False)
    )
    harness.app.state.settings = harness.app.state.settings.model_copy(
        update={"assistant_max_chars": chars}
    )
    assert harness.client.post(PATH, json=payload).status_code == 200
    harness.consent.reset_mock()
    harness.app.state.settings = harness.app.state.settings.model_copy(
        update={"assistant_max_chars": chars - 1}
    )
    response = harness.client.post(PATH, json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "input_too_large"
    harness.consent.assert_not_called()
