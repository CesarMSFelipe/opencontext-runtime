"""KG prune: drop nodes/edges whose source files no longer exist on disk."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.config import KnowledgeGraphConfig
from opencontext_core.graph.prune import prune_knowledge_graph
from opencontext_core.indexing.knowledge_graph import KnowledgeGraph


@pytest.fixture
def kg(tmp_path: Path) -> KnowledgeGraph:
    config = KnowledgeGraphConfig(enabled=True, languages=["python"])
    graph = KnowledgeGraph(config=config, db_path=tmp_path / "kg.db")
    yield graph
    graph.close()


def _index_linked_project(kg: KnowledgeGraph, root: Path) -> None:
    """keeper.py calls into goner.py so deleting goner leaves a dangling edge."""
    (root / "keeper.py").write_text(
        "from goner import gone\n\n\ndef kept():\n    return gone()\n",
        encoding="utf-8",
    )
    (root / "goner.py").write_text("def gone():\n    return 2\n", encoding="utf-8")
    kg.index_project(root)


class TestPruneKnowledgeGraph:
    def test_noop_when_all_files_exist(self, kg: KnowledgeGraph, tmp_path: Path) -> None:
        _index_linked_project(kg, tmp_path)
        report = prune_knowledge_graph(kg.db, tmp_path)
        assert report == {
            "nodes_removed": 0,
            "edges_removed": 0,
            "files_removed": 0,
            "dry_run": False,
        }

    def test_dry_run_reports_counts_without_deleting(
        self, kg: KnowledgeGraph, tmp_path: Path
    ) -> None:
        _index_linked_project(kg, tmp_path)
        (tmp_path / "goner.py").unlink()
        report = prune_knowledge_graph(kg.db, tmp_path, dry_run=True)
        assert report["dry_run"] is True
        assert report["nodes_removed"] == 1
        assert report["edges_removed"] >= 1
        assert report["files_removed"] == 1
        conn = kg.db._connect()
        remaining = conn.execute(
            "SELECT COUNT(*) FROM nodes WHERE file_path = 'goner.py'"
        ).fetchone()[0]
        assert remaining == 1, "dry-run must leave the graph intact"

    def test_prune_removes_nodes_edges_and_file_rows(
        self, kg: KnowledgeGraph, tmp_path: Path
    ) -> None:
        _index_linked_project(kg, tmp_path)
        (tmp_path / "goner.py").unlink()
        report = prune_knowledge_graph(kg.db, tmp_path)
        assert report["dry_run"] is False
        assert report["nodes_removed"] == 1
        assert report["edges_removed"] >= 1
        assert report["files_removed"] == 1
        conn = kg.db._connect()
        assert (
            conn.execute("SELECT COUNT(*) FROM nodes WHERE file_path = 'goner.py'").fetchone()[0]
            == 0
        )
        assert conn.execute("SELECT COUNT(*) FROM files WHERE path = 'goner.py'").fetchone()[0] == 0
        dangling = conn.execute(
            "SELECT COUNT(*) FROM edges WHERE target_node_id IS NOT NULL "
            "AND target_node_id NOT IN (SELECT id FROM nodes)"
        ).fetchone()[0]
        assert dangling == 0
        # Surviving file is untouched.
        assert (
            conn.execute("SELECT COUNT(*) FROM nodes WHERE file_path = 'keeper.py'").fetchone()[0]
            >= 1
        )

    def test_prune_removes_edges_dangling_on_missing_nodes(
        self, kg: KnowledgeGraph, tmp_path: Path
    ) -> None:
        _index_linked_project(kg, tmp_path)
        conn = kg.db._connect()
        conn.execute(
            "INSERT INTO edges (source_node_id, target_node_id, kind, call_site_file,"
            " call_site_line) VALUES ('missing_src', 'missing_tgt', 'calls', 'keeper.py', 1)"
        )
        conn.commit()
        report = prune_knowledge_graph(kg.db, tmp_path)
        assert report["edges_removed"] == 1
        assert report["nodes_removed"] == 0
