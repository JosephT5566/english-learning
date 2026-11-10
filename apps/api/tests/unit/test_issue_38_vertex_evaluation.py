"""Exercise synthetic Vertex evaluation without making network calls."""

import importlib
import json
from pathlib import Path

import pytest

ISSUE_DIR = Path(__file__).parents[4] / "doc" / "training" / "issues" / "issue-38"


@pytest.fixture
def vertex_module(monkeypatch):
    monkeypatch.syspath_prepend(str(ISSUE_DIR))
    return importlib.import_module("evaluate_vertex")


def test_rejects_invalid_vectors(vertex_module) -> None:
    with pytest.raises(ValueError, match="dimension"):
        vertex_module.validate_vector([1.0])
    with pytest.raises(ValueError, match="non-finite"):
        vertex_module.validate_vector([float("nan")] + [0.0] * 511)
    with pytest.raises(ValueError, match="zero"):
        vertex_module.validate_vector([0.0] * 512)


def test_synthetic_run_uses_document_and_query_tasks(vertex_module) -> None:
    labels = json.loads((ISSUE_DIR / "relevance.json").read_text(encoding="utf-8"))
    seen = []

    def fake_embed(content, task_type):
        seen.append((content, task_type))
        return [1.0] + [0.0] * 511, 3, 1.0

    report = vertex_module.run_evaluation(labels, fake_embed)
    assert report["request_count"] == 17
    assert report["input_tokens_reported"] == 51
    assert report["dimensions"] == 512
    assert len(report["per_query"]) == 7
    assert all(task == "RETRIEVAL_DOCUMENT" for _, task in seen[:10])
    assert all(task == "RETRIEVAL_QUERY" for _, task in seen[10:])
    assert seen[0][0].startswith("language: en\nterm: exhausted")
    from app.semantic_text import canonical_text

    assert [content for content, _ in seen[:10]] == [
        canonical_text({"language": "en", **card}) for card in labels["cards"]
    ]


def test_dump_vectors_cli_writes_compatible_fixture(
    vertex_module, monkeypatch, tmp_path
):
    import hashlib
    from datetime import datetime
    from types import SimpleNamespace

    from app.semantic_text import MODEL_VERSION

    destination = tmp_path / "fixtures" / "synthetic-en-v1.vectors.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "evaluate_vertex.py",
            "--project",
            "synthetic-project",
            "--dump-vectors",
            str(destination),
        ],
    )
    monkeypatch.setattr(
        vertex_module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="fake-token"),
    )
    monkeypatch.setattr(
        vertex_module,
        "request_embedding",
        lambda **kwargs: ([1.0] + [0.0] * 511, 3, 1.0),
    )
    vertex_module.main()
    payload = json.loads(destination.read_text())
    labels = json.loads(vertex_module.FIXTURE.read_text())
    assert payload["schema_version"] == 1
    assert payload["model"] == vertex_module.MODEL
    assert payload["dim"] == 512
    assert payload["model_version"] == MODEL_VERSION
    assert (
        payload["relevance_sha256"]
        == hashlib.sha256(vertex_module.FIXTURE.read_bytes()).hexdigest()
    )
    assert (
        datetime.fromisoformat(payload["created_at"]).utcoffset().total_seconds() == 0
    )
    assert set(payload["cards"]) == {card["id"] for card in labels["cards"]}
    assert set(payload["queries"]) == {query["text"] for query in labels["queries"]}
    assert all(
        len(vector) == 512
        for vector in [*payload["cards"].values(), *payload["queries"].values()]
    )
