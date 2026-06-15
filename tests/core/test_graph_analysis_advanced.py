"""Modularity-based communities, hub detection, and personalized PageRank.

Upgrades over the plain connected-components + degree-only analysis: a
modularity-scored, label-propagation community partition (deterministic),
betweenness-style hub detection, and a query-seeded personalized PageRank that
feeds the ranker. All deterministic for identical graph content; stdlib only.
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
    db = GraphDatabase(db_path=db_path)
    db.init_schema()
    names = set(extra or [])
    for a, b in calls:
        names.add(a)
        names.add(b)
    name_to_id: dict[str, str] = {}
    for idx, name in enumerate(sorted(names)):
        ids = db.upsert_nodes([_node(name, file_path=f"src/{name}.py", line=idx + 1)])
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


def _two_clusters() -> list[tuple[str, str]]:
    """Two dense triangles joined by a single bridge edge."""
    cluster_a = [("a1", "a2"), ("a2", "a3"), ("a3", "a1")]
    cluster_b = [("b1", "b2"), ("b2", "b3"), ("b3", "b1")]
    bridge = [("a1", "b1")]
    return cluster_a + cluster_b + bridge


def test_modularity_partition_separates_dense_clusters(tmp_path: Path) -> None:
    db_path = tmp_path / "g.db"
    name_to_id = _build_graph(db_path, _two_clusters())

    analyzer = GraphAnalyzer(GraphDatabase(db_path=db_path))
    try:
        partition = analyzer.detect_communities()
    finally:
        analyzer.close()

    a_comms = {partition[name_to_id[n]] for n in ("a1", "a2", "a3")}
    b_comms = {partition[name_to_id[n]] for n in ("b1", "b2", "b3")}
    # Each dense cluster collapses to one community, distinct from the other,
    # even though a bridge edge connects them (degree-only CC would merge them).
    assert len(a_comms) == 1
    assert len(b_comms) == 1
    assert a_comms != b_comms


def test_modularity_score_is_positive_for_clustered_graph(tmp_path: Path) -> None:
    db_path = tmp_path / "g.db"
    _build_graph(db_path, _two_clusters())

    analyzer = GraphAnalyzer(GraphDatabase(db_path=db_path))
    try:
        partition = analyzer.detect_communities()
        score = analyzer.modularity(partition)
    finally:
        analyzer.close()

    # A good partition of a clustered graph has clearly positive modularity.
    assert score > 0.2


def test_communities_reproducible_across_runs(tmp_path: Path) -> None:
    db_path = tmp_path / "g.db"
    _build_graph(db_path, _two_clusters())

    analyzer = GraphAnalyzer(GraphDatabase(db_path=db_path))
    try:
        first = analyzer.detect_communities()
        second = analyzer.detect_communities()
    finally:
        analyzer.close()

    assert first == second


def test_hub_detection_flags_central_broker(tmp_path: Path) -> None:
    db_path = tmp_path / "g.db"
    # A single broker node lies on every cross-cluster shortest path.
    calls = [
        ("a1", "hub"),
        ("a2", "hub"),
        ("hub", "b1"),
        ("hub", "b2"),
    ]
    name_to_id = _build_graph(db_path, calls)

    analyzer = GraphAnalyzer(GraphDatabase(db_path=db_path))
    try:
        hubs = analyzer.detect_hubs()
    finally:
        analyzer.close()

    assert hubs, "expected at least one hub"
    hub_ids = [h.node_id for h in hubs]
    # The broker has the highest betweenness and must rank first.
    assert hub_ids[0] == name_to_id["hub"]


def test_hub_detection_is_deterministic(tmp_path: Path) -> None:
    db_path = tmp_path / "g.db"
    _build_graph(db_path, _two_clusters())

    analyzer = GraphAnalyzer(GraphDatabase(db_path=db_path))
    try:
        first = [(h.node_id, round(h.score, 9)) for h in analyzer.detect_hubs()]
        second = [(h.node_id, round(h.score, 9)) for h in analyzer.detect_hubs()]
    finally:
        analyzer.close()

    assert first == second


def test_personalized_pagerank_seeds_lift_named_symbol(tmp_path: Path) -> None:
    db_path = tmp_path / "g.db"
    name_to_id = _build_graph(db_path, _two_clusters())

    analyzer = GraphAnalyzer(GraphDatabase(db_path=db_path))
    try:
        ranks = analyzer.personalized_pagerank(seed_names=["a1"])
    finally:
        analyzer.close()

    # Seeding on a1 must give cluster-a nodes more mass than cluster-b nodes.
    assert ranks[name_to_id["a2"]] > ranks[name_to_id["b2"]]


def test_personalized_pagerank_is_deterministic(tmp_path: Path) -> None:
    db_path = tmp_path / "g.db"
    _build_graph(db_path, _two_clusters())

    analyzer = GraphAnalyzer(GraphDatabase(db_path=db_path))
    try:
        first = analyzer.personalized_pagerank(seed_names=["a1"])
        second = analyzer.personalized_pagerank(seed_names=["a1"])
    finally:
        analyzer.close()

    assert first == second
