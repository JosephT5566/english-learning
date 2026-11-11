"""Propose executors cannot write even under the ordinary writable RLS role."""

import os
import time

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.assistant import tools
from app.database import bind_owner
from tests.integration.test_assistant_http_boundaries import snapshot_counts
from tests.integration.test_auth_and_authorization import api_client  # noqa: F401

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1",
        reason="PostgreSQL tests are opt-in",
    ),
]


def test_propose_executor_insert_is_readonly(monkeypatch, request):
    # Resolve the new API before DB fixtures so unchanged main fails without a DB.
    spec = tools.ToolSpec(
        "fake_propose", {"name": "fake_propose"}, tools.Filters, "propose"
    )
    monkeypatch.setattr(
        tools, "REGISTRY", tools.build_registry((*tools.REGISTRY, spec))
    )
    client = request.getfixturevalue("api_client")
    engine = request.getfixturevalue("migrated_database_engine")
    before = snapshot_counts(engine)
    with client.app.state.database_session_factory() as session:
        bind_owner(session, 1)
        assert (
            session.execute(text("SELECT current_user")).scalar_one() == "app_rls_test"
        )
        session.rollback()

        def insert(arguments, deadline):
            session.execute(
                text(
                    "INSERT INTO learning_decks (owner_id, target_language, explanation_language, title) VALUES (1, 'en', 'zh-TW', 'tier test')"
                )
            )

        execute = tools.SessionTools(
            session, 1, client.app.state.settings, None, executors={spec.name: insert}
        )
        with pytest.raises(DBAPIError) as failure:
            execute(spec.name, {}, time.monotonic() + 5)
        assert failure.value.orig.sqlstate == "25006"
    assert snapshot_counts(engine) == before
