"""Impact analysis distinguishes unknown-node from zero-impact.

Before the fix, `analyze` returned an all-empty `ImpactResult` with `symbol=""`
when the node id was missing — identical in shape to a real leaf symbol with no
callers, so callers could not tell "no impact" from "no such symbol". The result
must now carry a `found` signal plus risk inputs (callers/dependents/files/tests/
centrality) usable to derive a risk level.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.config import KnowledgeGraphConfig
from opencontext_core.indexing.impact_analysis import ImpactAnalyzer
from opencontext_core.indexing.knowledge_graph import KnowledgeGraph


@pytest.fixture
def kg(tmp_path: Path) -> KnowledgeGraph:
    config = KnowledgeGraphConfig(enabled=True, languages=["python"])
    graph = KnowledgeGraph(config=config, db_path=tmp_path / "kg.db")
    yield graph
    graph.close()


def _node_id(kg: KnowledgeGraph, name: str, file_path: str) -> str | None:
    conn = kg.db._connect()
    row = conn.execute(
        "SELECT id FROM nodes WHERE name = ? AND file_path = ?",
        (name, file_path),
    ).fetchone()
    return row["id"] if row else None


def test_unknown_node_reports_not_found(kg: KnowledgeGraph) -> None:
    kg.index_file("a.py", "def leaf():\n    return 1\n")
    analyzer = ImpactAnalyzer(kg.db)

    result = analyzer.analyze("this-id-does-not-exist")
    assert result.found is False
    assert result.risk_level == "unknown"


def test_existing_leaf_reports_real_zero_impact(kg: KnowledgeGraph) -> None:
    kg.index_file("a.py", "def leaf():\n    return 1\n")
    leaf_id = _node_id(kg, "leaf", "a.py")
    assert leaf_id is not None

    analyzer = ImpactAnalyzer(kg.db)
    result = analyzer.analyze(leaf_id)

    assert result.found is True
    assert result.symbol == "leaf"
    assert result.direct_callers == []
    assert result.risk_level == "low"
    assert result.risk_level != "unknown"


def test_high_fan_in_symbol_yields_elevated_risk(kg: KnowledgeGraph, tmp_path: Path) -> None:
    # core_util is called by many distinct functions across files.
    (tmp_path / "lib.py").write_text("def core_util():\n    return 1\n")
    callers_src = "from lib import core_util\n\n"
    for i in range(8):
        callers_src += f"def caller_{i}():\n    return core_util()\n\n\n"
    (tmp_path / "callers.py").write_text(callers_src)
    (tmp_path / "leaf.py").write_text("def lonely():\n    return 0\n")
    kg.index_project(tmp_path)

    core_id = _node_id(kg, "core_util", "lib.py")
    lonely_id = _node_id(kg, "lonely", "leaf.py")
    assert core_id is not None
    assert lonely_id is not None

    analyzer = ImpactAnalyzer(kg.db)
    core = analyzer.analyze(core_id)
    lonely = analyzer.analyze(lonely_id)

    levels = ["low", "medium", "high", "critical"]
    assert core.found is True
    assert len(core.direct_callers) >= 5
    assert levels.index(core.risk_level) > levels.index(lonely.risk_level)
