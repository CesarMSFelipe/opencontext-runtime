"""ProgressiveExpander wired into the live retrieval path.

`RetrievalPlanner.plan()` must, when a graph DB is available, expand the
retrieved seeds by the request's expansion_rounds/graph_radius using a
UnifiedGraph built from the planner's graph DB, feed graph distance into the
hybrid ranker, and surface discovered neighbors as additive evidence. With no
graph DB it must be a strict no-op (manifest/graph fallback unchanged).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from opencontext_core.compat import UTC
from opencontext_core.indexing.graph_db import Edge, FileRecord, GraphDatabase, Node
from opencontext_core.models.context import ContextItem, ContextPriority
from opencontext_core.models.project import (
    DependencyGraph,
    FileKind,
    ProjectFile,
    ProjectManifest,
)
from opencontext_core.retrieval.contracts import EvidenceRequest, RetrievalSurface
from opencontext_core.retrieval.planner import RetrievalPlanner


def _manifest(root: Path) -> ProjectManifest:
    source = root / "src" / "auth.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("def authenticate_user():\n    return True\n", encoding="utf-8")
    return ProjectManifest(
        project_name="demo",
        root=str(root),
        profile="python",
        technology_profiles=["python"],
        files=[
            ProjectFile(
                id="src/auth.py",
                path="src/auth.py",
                language="python",
                file_type=FileKind.CODE,
                tokens=20,
                size_bytes=source.stat().st_size,
                summary="Authentication helpers",
            )
        ],
        symbols=[],
        dependency_graph=DependencyGraph(
            nodes=["src/auth.py"],
            edges=[],
            unresolved=[],
            generated_at=datetime.now(tz=UTC),
        ),
        generated_at=datetime.now(tz=UTC),
    )


def _node(name: str, file_path: str, line: int) -> Node:
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
        docstring=f"{name} docstring",
        signature=f"def {name}()",
        is_exported=True,
    )


def _seeded_graph_db(db_path: Path) -> dict[str, str]:
    """Graph where authenticate_user calls verify_password; returns name->id."""
    db = GraphDatabase(db_path=db_path)
    db.init_schema()
    db.upsert_file(
        FileRecord(
            id=None,
            path="src/auth.py",
            language="python",
            last_modified=1,
            hash="h",
            size=1,
        )
    )
    ids_a = db.upsert_nodes([_node("authenticate_user", "src/auth.py", 1)])
    ids_b = db.upsert_nodes([_node("verify_password", "src/crypto.py", 1)])
    name_to_id = {"authenticate_user": ids_a[0], "verify_password": ids_b[0]}
    db.insert_edge(
        Edge(
            id=None,
            source_node_id=ids_a[0],
            target_node_id=ids_b[0],
            kind="calls",
            call_site_file="src/auth.py",
            call_site_line=1,
        )
    )
    db.rebuild_fts()
    db.close()
    return name_to_id


def _request(root: Path, query: str, *, rounds: int = 2, radius: int = 1) -> EvidenceRequest:
    return EvidenceRequest(
        query=query,
        root=root,
        surface=RetrievalSurface.RUNTIME,
        max_tokens=2000,
        expansion_rounds=rounds,
        graph_radius=radius,
    )


def test_expander_invoked_from_plan_with_unified_graph(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "context_graph.db"
    _seeded_graph_db(db_path)

    captured: dict[str, object] = {}

    import opencontext_core.retrieval.planner as planner_module
    from opencontext_core.context.planning.expansion import ProgressiveExpander

    original_expand = ProgressiveExpander.expand

    def spy_expand(self, seeds, plan, contract, graph=None, memory=None, round_num=1):
        captured["called"] = True
        captured["graph"] = graph
        captured["expansion_rounds"] = plan.expansion_rounds
        captured["graph_radius"] = plan.graph_radius
        return original_expand(self, seeds, plan, contract, graph, memory, round_num)

    monkeypatch.setattr(planner_module.ProgressiveExpander, "expand", spy_expand)

    planner = RetrievalPlanner(_manifest(tmp_path), graph_db_path=db_path)
    planner.plan(_request(tmp_path, "authenticate_user", rounds=2, radius=1), top_k=5)

    assert captured.get("called") is True
    from opencontext_core.graph.unified import UnifiedGraph

    assert isinstance(captured.get("graph"), UnifiedGraph)
    assert captured.get("expansion_rounds") == 2
    assert captured.get("graph_radius") == 1


def test_plan_surfaces_graph_neighbor_as_evidence(tmp_path: Path) -> None:
    db_path = tmp_path / "context_graph.db"
    _seeded_graph_db(db_path)

    planner = RetrievalPlanner(_manifest(tmp_path), graph_db_path=db_path)
    plan = planner.plan(_request(tmp_path, "authenticate_user", rounds=2, radius=1), top_k=5)

    # The graph neighbor verify_password is reachable only via graph expansion
    # (it is not in the manifest and a plain query would not surface it as a seed).
    blob = " ".join(e.content + " " + e.source + " " + e.id for e in plan.evidence).lower()
    assert "verify_password" in blob


def test_no_graph_db_is_strict_noop(tmp_path: Path) -> None:
    # Without a graph DB, expansion must not run and evidence is the manifest set.
    planner = RetrievalPlanner(_manifest(tmp_path))
    plan = planner.plan(_request(tmp_path, "authenticate_user"), top_k=5)
    sources = {e.provenance.get("retrieval_source") for e in plan.evidence}
    assert sources == {"manifest"}


def test_graph_distance_feeds_ranking(tmp_path: Path) -> None:
    # Two equal-lexical candidates; the one that is a graph seed (distance 0)
    # must outrank the one with no graph distance via graph_centrality weight.
    db_path = tmp_path / "context_graph.db"
    name_to_id = _seeded_graph_db(db_path)
    seed_id = name_to_id["authenticate_user"]

    class _StubSource:
        name = "stub"

        def retrieve(self, query: str, limit: int) -> list[ContextItem]:
            return [
                ContextItem(
                    id="zzz_far",
                    content="def zzz_far(): pass",
                    source="src/zzz.py",
                    source_type="file",
                    priority=ContextPriority.P1,
                    tokens=100,
                    score=0.5,
                    source_trust=0.5,
                ),
                ContextItem(
                    id=seed_id,
                    content="def authenticate_user(): pass",
                    source="src/auth.py:1",
                    source_type="graph_symbol",
                    priority=ContextPriority.P1,
                    tokens=100,
                    score=0.5,
                    source_trust=0.5,
                ),
            ][:limit]

    planner = RetrievalPlanner([_StubSource()], graph_db_path=db_path)
    plan = planner.plan(_request(tmp_path, "authenticate_user", rounds=1, radius=1), top_k=5)
    assert plan.evidence[0].id == seed_id, "graph-distance seed should rank first"
