"""Method/attribute call edges are resolved and persisted.

Before the fix, `_extract_calls` stored the whole dotted expression (`self._step`,
`obj.method`) as the target name, and `index_file` only kept an edge when
`node_map.get(target_name)` matched a bare symbol name — so every method/attribute
call edge was silently dropped.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.config import KnowledgeGraphConfig
from opencontext_core.indexing.call_graph import CallGraphAnalyzer
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


def test_intra_file_self_method_call_produces_edge(kg: KnowledgeGraph) -> None:
    code = (
        "class Service:\n"
        "    def run(self):\n"
        "        return self._step()\n"
        "\n"
        "    def _step(self):\n"
        "        return 1\n"
    )
    kg.index_file("svc.py", code)

    run_id = _node_id(kg, "run", "svc.py")
    step_id = _node_id(kg, "_step", "svc.py")
    assert run_id is not None
    assert step_id is not None

    analyzer = CallGraphAnalyzer(kg.db)
    callees = {c["name"] for c in analyzer.get_callees(run_id)}
    assert "_step" in callees


def test_callers_include_method_call(kg: KnowledgeGraph) -> None:
    code = (
        "class Service:\n"
        "    def handle(self):\n"
        "        return 1\n"
        "\n"
        "\n"
        "def main():\n"
        "    s = Service()\n"
        "    return s.handle()\n"
    )
    kg.index_file("svc.py", code)

    handle_id = _node_id(kg, "handle", "svc.py")
    assert handle_id is not None

    analyzer = CallGraphAnalyzer(kg.db)
    callers = {c["name"] for c in analyzer.get_callers(handle_id)}
    assert "main" in callers


def test_module_qualified_call_resolves_cross_file(kg: KnowledgeGraph, tmp_path: Path) -> None:
    (tmp_path / "b.py").write_text("def helper():\n    return 1\n")
    (tmp_path / "a.py").write_text("import b\n\n\ndef caller():\n    return b.helper()\n")
    kg.index_project(tmp_path)

    helper_id = _node_id(kg, "helper", "b.py")
    assert helper_id is not None

    analyzer = CallGraphAnalyzer(kg.db)
    callers = {c["name"] for c in analyzer.get_callers(helper_id)}
    assert "caller" in callers
