"""Tests for GraphHealthReport + compute_graph_health (Workstream E)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from opencontext_core.indexing.graph_health import GraphHealthReport, compute_graph_health

# ── model ─────────────────────────────────────────────────────────────────────


def test_report_schema_version() -> None:
    r = GraphHealthReport(status="empty", indexed=False)
    assert r.schema_version == "opencontext.graph_health.v1"


def test_report_ok_only_when_healthy() -> None:
    assert GraphHealthReport(status="healthy", indexed=True).ok() is True
    assert GraphHealthReport(status="degraded", indexed=True).ok() is False
    assert GraphHealthReport(status="empty", indexed=False).ok() is False
    assert GraphHealthReport(status="unavailable", indexed=False).ok() is False


def test_report_forbids_extra() -> None:
    with pytest.raises(ValidationError):
        GraphHealthReport(status="healthy", indexed=True, bogus=1)


def test_report_round_trip() -> None:
    r = GraphHealthReport(
        status="degraded",
        indexed=True,
        nodes=10,
        edges=5,
        files=3,
        orphan_symbols=2,
        dangling_edges=1,
        languages={"python": 10},
        warnings=["w"],
    )
    restored = GraphHealthReport.model_validate(r.model_dump())
    assert restored.nodes == 10
    assert restored.languages == {"python": 10}


# ── compute_graph_health: fail-closed paths ───────────────────────────────────


def test_missing_db_is_unavailable(tmp_path: Path) -> None:
    r = compute_graph_health(tmp_path / "does-not-exist.db")
    assert r.status == "unavailable"
    assert r.indexed is False
    assert r.warnings


def test_empty_db_is_empty(tmp_path: Path) -> None:
    from opencontext_core.indexing.graph_db import GraphDatabase

    db_path = tmp_path / "empty.db"
    db = GraphDatabase(db_path=db_path)
    db.init_schema()
    db.close()

    r = compute_graph_health(db_path)
    assert r.status == "empty"
    assert r.indexed is False
    assert r.nodes == 0


# ── compute_graph_health: real indexed project ────────────────────────────────


def _index_tiny_project(tmp_path: Path) -> Path:
    from opencontext_core.config import KnowledgeGraphConfig
    from opencontext_core.indexing.knowledge_graph import KnowledgeGraph

    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "auth.py").write_text(
        "def login(u):\n    return validate(u)\n\n\ndef validate(u):\n    return bool(u)\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "kg.db"
    cfg = KnowledgeGraphConfig(enabled=True, languages=["python"])
    kg = KnowledgeGraph(config=cfg, db_path=db_path)
    kg.index_project(root)
    kg.close()
    return db_path


def test_indexed_project_reports_nodes(tmp_path: Path) -> None:
    db_path = _index_tiny_project(tmp_path)
    r = compute_graph_health(db_path)
    assert r.indexed is True
    assert r.nodes > 0
    assert r.status in ("healthy", "degraded")
    assert "python" in r.languages


def test_indexed_project_no_dangling_edges(tmp_path: Path) -> None:
    db_path = _index_tiny_project(tmp_path)
    r = compute_graph_health(db_path)
    # A freshly indexed project should have no dangling edges.
    assert r.dangling_edges == 0
