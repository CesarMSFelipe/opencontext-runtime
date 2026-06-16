"""Doctor flags an empty knowledge graph (the interrupted-index silent failure)."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.config import OpenContextConfig, default_config_data
from opencontext_core.doctor.component_checks import ComponentDoctor
from opencontext_core.indexing.graph_db import GraphDatabase, Node


def _doctor() -> ComponentDoctor:
    return ComponentDoctor(OpenContextConfig.model_validate(default_config_data()))


def _graph(tmp_path: Path) -> GraphDatabase:
    db_path = tmp_path / ".storage" / "opencontext" / "context_graph.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = GraphDatabase(db_path=db_path)
    db.init_schema()
    return db


def _kg_check(doctor: ComponentDoctor):
    return next(c for c in doctor.check_knowledge_graph() if c.name == "kg_database")


def test_empty_graph_is_flagged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _graph(tmp_path)  # schema, zero nodes
    db.close()
    monkeypatch.chdir(tmp_path)

    check = _kg_check(_doctor())
    assert check.ok is False
    assert check.status == "empty"
    assert "index" in (check.recommendation or "").lower()


def test_legacy_codegraph_name_is_resolved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Only the legacy codegraph.db exists (no context_graph.db). The runtime uses
    # it via a shim; the doctor must report it healthy, not "missing".
    storage = tmp_path / ".storage" / "opencontext"
    storage.mkdir(parents=True, exist_ok=True)
    db = GraphDatabase(db_path=storage / "codegraph.db")
    db.init_schema()
    db.upsert_nodes(
        [
            Node(
                id="abc123def4567890",
                name="login",
                kind="function",
                file_path="src/auth.py",
                line=1,
                column=0,
                end_line=2,
                language="python",
                container=None,
                docstring=None,
                signature=None,
                is_exported=True,
            )
        ]
    )
    db.close()
    monkeypatch.chdir(tmp_path)

    check = _kg_check(_doctor())
    assert check.ok is True
    assert check.status == "healthy"


def test_populated_graph_is_healthy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _graph(tmp_path)
    db.upsert_nodes(
        [
            Node(
                id="abc123def4567890",
                name="login",
                kind="function",
                file_path="src/auth.py",
                line=1,
                column=0,
                end_line=2,
                language="python",
                container=None,
                docstring=None,
                signature=None,
                is_exported=True,
            )
        ]
    )
    db.close()
    monkeypatch.chdir(tmp_path)

    check = _kg_check(_doctor())
    assert check.ok is True
    assert check.status == "healthy"
