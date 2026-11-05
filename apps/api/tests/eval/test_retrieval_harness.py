"""Check failure reports and the SQL harness with generated control vectors, not Vertex."""

import json
import os
from datetime import UTC, datetime

import pytest

from app.semantic_text import MODEL_VERSION
from tests.eval.retrieval_eval import (
    FIX_COMMAND,
    LABELS,
    THRESHOLD,
    initial_report,
    load_vectors,
    score_rankings,
    write_report,
)
from tests.eval.test_retrieval_eval import retrieve_rankings


@pytest.fixture
def control_fixture(tmp_path):
    labels = json.loads(LABELS.read_text())
    cards = {}
    for index, card in enumerate(labels["cards"]):
        vector = [0.0] * 512
        vector[index] = 1.0
        cards[card["id"]] = vector
    queries = {
        query["text"]: [
            float(query["relevance"].get(card["id"], 0)) for card in labels["cards"]
        ]
        + [0.0] * 502
        for query in labels["queries"]
    }
    payload = {
        "schema_version": 1,
        "model": "gemini-embedding-001",
        "dim": 512,
        "model_version": MODEL_VERSION,
        "relevance_sha256": initial_report(labels)["relevance_sha256"],
        "created_at": datetime.now(UTC).isoformat(),
        "cards": cards,
        "queries": queries,
    }
    path = tmp_path / "control.json"
    path.write_text(json.dumps(payload))
    return labels, payload, path


def test_missing_fixture_reports_fix_command(tmp_path):
    labels = json.loads(LABELS.read_text())
    report = initial_report(labels)
    with pytest.raises(AssertionError, match="Missing frozen vector fixture") as caught:
        load_vectors(labels, report, tmp_path / "missing.json")
    report["error"] = str(caught.value)
    write_report(report, tmp_path / "report")
    markdown = (tmp_path / "report/report.md").read_text()
    result = json.loads((tmp_path / "report/report.json").read_text())
    assert FIX_COMMAND in markdown
    assert result["fix_command"] == FIX_COMMAND
    assert result["macro_ndcg_at_5"] is None
    assert len(result["per_query"]) == 7
    assert "vector fixture missing" in result["fixture_sha_status"]


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("relevance_sha256", "wrong", "SHA-256"),
        ("model_version", "old", "MODEL_VERSION"),
        ("dim", 256, "dimension"),
    ],
)
def test_rejects_incompatible_metadata(control_fixture, field, value, message):
    labels, payload, path = control_fixture
    payload[field] = value
    path.write_text(json.dumps(payload))
    report = initial_report(labels)
    with pytest.raises(AssertionError, match=message):
        load_vectors(labels, report, path)
    if field == "relevance_sha256":
        assert report["fixture_sha_status"] == "MISMATCH"


def test_broken_ranking_report_names_queries(control_fixture, tmp_path):
    labels, _, _ = control_fixture
    report = initial_report(labels)
    score_rankings(labels, {query["text"]: [] for query in labels["queries"]}, report)
    report["error"] = "macro nDCG@5 below threshold"
    write_report(report, tmp_path)
    result = json.loads((tmp_path / "report.json").read_text())
    markdown = (tmp_path / "report.md").read_text()
    assert result["macro_ndcg_at_5"] == 0
    assert len(result["below_threshold"]) == 7
    assert "required >= 0.75" in markdown
    assert all(query["text"] in markdown for query in labels["queries"])


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1",
    reason="requires disposable PostgreSQL/pgvector",
)
def test_postgres_control_detects_reversed_ranking(
    control_fixture, migrated_database_engine
):
    labels, _, path = control_fixture
    report = initial_report(labels)
    vectors = load_vectors(labels, report, path)
    rankings = retrieve_rankings(migrated_database_engine, labels, vectors)
    score_rankings(labels, rankings, report)
    assert report["macro_ndcg_at_5"] >= THRESHOLD
    reversed_rankings = {query: list(reversed(ids)) for query, ids in rankings.items()}
    score_rankings(labels, reversed_rankings, report)
    assert report["macro_ndcg_at_5"] < THRESHOLD


@pytest.mark.parametrize("failure", ["ranking", "database"])
def test_gate_failure_always_writes_report(
    control_fixture, tmp_path, monkeypatch, failure
):
    from types import SimpleNamespace

    from tests.eval import test_retrieval_eval as gate

    labels, payload, _ = control_fixture
    monkeypatch.setenv("RUN_POSTGRES_INTEGRATION_TESTS", "1")
    monkeypatch.setattr(gate, "load_vectors", lambda *args: payload)
    monkeypatch.setattr(
        gate, "write_report", lambda report: write_report(report, tmp_path)
    )

    def retrieve(*args):
        if failure == "database":
            raise RuntimeError("database unavailable")
        return {query["text"]: [] for query in labels["queries"]}

    monkeypatch.setattr(gate, "retrieve_rankings", retrieve)
    request = SimpleNamespace(getfixturevalue=lambda name: object())
    with pytest.raises((AssertionError, RuntimeError)):
        gate.test_frozen_retrieval_ndcg(request)
    report = json.loads((tmp_path / "report.json").read_text())
    assert (tmp_path / "report.md").is_file()
    assert report["error"]
    assert len(report["per_query"]) == 7
    if failure == "ranking":
        assert report["macro_ndcg_at_5"] == 0
        assert len(report["below_threshold"]) == 7
