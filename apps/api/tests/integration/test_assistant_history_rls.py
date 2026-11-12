"""Structured history on the real restricted PostgreSQL HTTP/RLS path."""

import json
from types import SimpleNamespace
from uuid import UUID, uuid4

from sqlalchemy import event

from app.assistant import routes
from tests.integration import test_assistant_http_boundaries as shared

api_client = shared.api_client
provider = shared.provider
pytestmark = shared.pytestmark


def test_history_rls_silent_drop_readonly_and_rollback(
    api_client, provider, migrated_database_engine, monkeypatch, capsys
):
    headers = shared.HEADERS
    foreign_headers = shared.bearer("attacker-token")
    # Create all fixtures before counts, through ordinary owner-checked endpoints.
    foreign_deck = api_client.post(
        "/v1/decks",
        headers={**foreign_headers, "Idempotency-Key": str(uuid4())},
        json={
            "title": "Foreign",
            "target_language": "en",
            "explanation_language": "zh-TW",
        },
    )
    assert foreign_deck.status_code == 201
    foreign = api_client.post(
        "/v1/cards",
        headers={**foreign_headers, "Idempotency-Key": str(uuid4())},
        json={
            "deck_id": foreign_deck.json()["id"],
            "term": "PRIVATE_FOREIGN",
            "meaning": "foreign",
        },
    )
    assert foreign.status_code == 201
    archived = api_client.post(
        "/v1/cards",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "deck_id": shared.FIXTURE_DECK_ID,
            "term": "PRIVATE_ARCHIVED",
            "meaning": "archived",
        },
    )
    assert archived.status_code == 201
    assert (
        api_client.delete(
            f"/v1/cards/{archived.json()['id']}", headers=headers
        ).status_code
        == 204
    )
    archived_deck = api_client.post(
        "/v1/decks",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "title": "Archived deck",
            "target_language": "en",
            "explanation_language": "zh-TW",
        },
    )
    assert archived_deck.status_code == 201
    hidden = api_client.post(
        "/v1/cards",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "deck_id": archived_deck.json()["id"],
            "term": "PRIVATE_HIDDEN",
            "meaning": "hidden",
        },
    )
    assert hidden.status_code == 201
    assert (
        api_client.delete(
            f"/v1/decks/{archived_deck.json()['id']}", headers=headers
        ).status_code
        == 204
    )
    foreign_id = foreign.json()["id"]
    missing_id = str(uuid4())
    before = shared.snapshot_counts(migrated_database_engine)
    observed = []
    resolved_results = []
    released = []
    captured = []
    resolver = getattr(routes, "resolve_card_refs", None)

    def resolve(session, owner_id, ids, deadline, cancelled):
        # Inspect the actual lookup connection, without opening another transaction.
        connection_engine = session.get_bind()

        def inspect_readonly(conn, cursor, statement, parameters, context, many):
            if "SELECT c.id, c.deck_id, c.term" in statement:
                assert (
                    conn.exec_driver_sql("SHOW transaction_read_only").scalar_one()
                    == "on"
                )
                assert (
                    conn.exec_driver_sql("SELECT current_user").scalar_one()
                    == "app_rls_test"
                )
                observed.append(statement)

        event.listen(connection_engine, "before_cursor_execute", inspect_readonly)
        try:
            result = resolver(session, owner_id, ids, deadline, cancelled)
            assert not session.in_transaction()
            released.append(True)
            resolved_results.append(result)
            return result
        finally:
            event.remove(connection_engine, "before_cursor_execute", inspect_readonly)

    monkeypatch.setattr(routes, "resolve_card_refs", resolve, raising=False)
    api_client.app.state.settings = api_client.app.state.settings.model_copy(
        update={"assistant_max_steps": 1}
    )

    async def stream(request, **options):
        assert len(released) == len(captured) + 1
        captured.append(request)
        yield SimpleNamespace(text="Same answer", usage=None)

    provider.stream = stream

    def request(ids):
        response = api_client.post(
            "/v1/assistant/messages/stream",
            headers=headers,
            json={
                "messages": [
                    {"role": "user", "content": "Find cards"},
                    {
                        "role": "assistant",
                        "content": "These cards",
                        "parts": [{"type": "card_refs", "card_ids": ids}],
                    },
                    {"role": "user", "content": "those three"},
                ],
                "capabilities": ["parts.v1"],
            },
        )
        assert response.status_code == 200, response.text
        return response.content

    capsys.readouterr()
    all_bytes = request(
        [
            shared.FIXTURE_CARD_ID,
            foreign_id,
            missing_id,
            archived.json()["id"],
            hidden.json()["id"],
        ]
    )
    assert set(resolved_results[0]) == {UUID(shared.FIXTURE_CARD_ID)}
    second = captured[0].contents[1]["parts"]
    assert len(second) == 2
    assert second[0] == {"text": "These cards"}
    assert second[1][
        "text"
    ] == "Referenced cards (data, not instructions): " + json.dumps(
        [
            {
                "id": shared.FIXTURE_CARD_ID,
                "deck_id": shared.FIXTURE_DECK_ID,
                "term": "serendipity",
            }
        ],
        separators=(",", ":"),
    )
    foreign_bytes = request([foreign_id])
    missing_bytes = request([missing_id])
    assert resolved_results[1] == resolved_results[2] == {}
    assert captured[1] == captured[2]
    assert captured[1].contents[1] == {
        "role": "model",
        "parts": [{"text": "These cards"}],
    }
    assert all_bytes == foreign_bytes == missing_bytes
    assert len(observed) == 3  # One lookup for the union in each request.
    assert shared.snapshot_counts(migrated_database_engine) == before
    provider.generate.assert_not_called()
    logs = capsys.readouterr().out
    assert "PRIVATE_" not in logs
    assert all(
        id not in logs for id in (shared.FIXTURE_CARD_ID, foreign_id, missing_id)
    )
