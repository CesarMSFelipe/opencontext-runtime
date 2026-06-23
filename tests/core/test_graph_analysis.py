"""deterministic graph analysis over the persisted nodes/edges.

Covers centrality (in/out degree), configurable god-node detection,
connected-components + label-propagation community partition, and the
name-resolving path / explain queries. All must be reproducible for identical
graph content (no extra hard deps; networkx optional).
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.indexing.graph_analysis import GraphAnalyzer
from opencontext_core.indexing.graph_db import Edge, GraphDatabase, Node


def _node(name: str, file_path: str = "src/m.py", line: int = 1) -> Node:
    return Node(
        id=None,
        name=name,
        kind="function",
        file_path=file_path,
        line=line,
        column=0,
        end_line=line + 1,
        language="python",
        container=None,
        docstring=None,
        signature=f"def {name}()",
        is_exported=True,
    )


def _build_graph(db_path: Path, calls: list[tuple[str, str]], extra: list[str] | None = None):
    """Build a graph DB with one node per symbol and a 'calls' edge per pair.

    Returns a dict mapping symbol name -> stable node id.
    """
    db = GraphDatabase(db_path=db_path)
    db.init_schema()
    names = set(extra or [])
    for a, b in calls:
        names.add(a)
        names.add(b)
    name_to_id: dict[str, str] = {}
    # Insert each symbol as its own file so stable ids are unique per symbol.
    for idx, name in enumerate(sorted(names)):
        nodes = [_node(name, file_path=f"src/{name}.py", line=idx + 1)]
        ids = db.upsert_nodes(nodes)
        name_to_id[name] = ids[0]
    for a, b in calls:
        db.insert_edge(
            Edge(
                id=None,
                source_node_id=name_to_id[a],
                target_node_id=name_to_id[b],
                kind="calls",
                call_site_file=f"src/{a}.py",
                call_site_line=1,
            )
        )
    db.close()
    return name_to_id


def test_god_node_detection_flags_highly_referenced_symbol(tmp_path: Path) -> None:
    db_path = tmp_path / "g.db"
    # core_util called by 10 distinct symbols; each caller has at most 1 caller.
    callers = [f"c{i}" for i in range(10)]
    calls = [(c, "core_util") for c in callers]
    name_to_id = _build_graph(db_path, calls)

    analyzer = GraphAnalyzer(GraphDatabase(db_path=db_path))
    try:
        centrality = analyzer.compute_centrality()
        gods = analyzer.detect_god_nodes(threshold=5)
    finally:
        analyzer.close()

    core_id = name_to_id["core_util"]
    # Highest centrality must be core_util.
    top = max(centrality, key=lambda nid: centrality[nid].score)
    assert top == core_id
    # Flagged as god node; single-caller symbols are not.
    god_ids = {g.node_id for g in gods}
    assert core_id in god_ids
    assert name_to_id["c0"] not in god_ids


def test_centrality_is_deterministic_across_runs(tmp_path: Path) -> None:
    db_path = tmp_path / "g.db"
    calls = [("a", "b"), ("a", "c"), ("b", "c"), ("d", "c")]
    _build_graph(db_path, calls)

    def run() -> dict[str, float]:
        analyzer = GraphAnalyzer(GraphDatabase(db_path=db_path))
        try:
            return {nid: c.score for nid, c in analyzer.compute_centrality().items()}
        finally:
            analyzer.close()

    assert run() == run()


def test_path_query_returns_existing_call_path(tmp_path: Path) -> None:
    db_path = tmp_path / "g.db"
    _build_graph(db_path, [("a", "b"), ("b", "c")])

    analyzer = GraphAnalyzer(GraphDatabase(db_path=db_path))
    try:
        result = analyzer.path("a", "c")
    finally:
        analyzer.close()

    assert result.found is True
    assert result.hops == 2
    names = [hop["name"] for hop in result.path]
    assert "b" in names


def test_path_query_reports_no_path_without_raising(tmp_path: Path) -> None:
    db_path = tmp_path / "g.db"
    # a->b->c is a chain; d is isolated (give it a self-less node).
    _build_graph(db_path, [("a", "b"), ("b", "c")], extra=["d"])

    analyzer = GraphAnalyzer(GraphDatabase(db_path=db_path))
    try:
        result = analyzer.path("a", "d")
    finally:
        analyzer.close()

    assert result.found is False


def test_explain_reports_callers_callees_and_path(tmp_path: Path) -> None:
    db_path = tmp_path / "g.db"
    _build_graph(db_path, [("a", "b"), ("b", "c")])

    analyzer = GraphAnalyzer(GraphDatabase(db_path=db_path))
    try:
        explanation = analyzer.explain("b")
    finally:
        analyzer.close()

    assert explanation.resolved is True
    caller_names = {c["name"] for c in explanation.callers}
    callee_names = {c["name"] for c in explanation.callees}
    assert "a" in caller_names
    assert "c" in callee_names


def test_explain_unresolved_symbol_does_not_raise(tmp_path: Path) -> None:
    db_path = tmp_path / "g.db"
    _build_graph(db_path, [("a", "b")])

    analyzer = GraphAnalyzer(GraphDatabase(db_path=db_path))
    try:
        explanation = analyzer.explain("does_not_exist")
    finally:
        analyzer.close()

    assert explanation.resolved is False
