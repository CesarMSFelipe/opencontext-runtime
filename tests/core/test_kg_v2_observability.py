"""PR-008 KG v2 receipts + kg.* events + owner resolution (KG-14, KG-CONV)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from opencontext_core.indexing.kg_receipts import KgObserver
from opencontext_core.indexing.knowledge_graph import KnowledgeGraph
from opencontext_core.models.trace import (
    KG_INDEX_COMPLETED,
    KG_INDEX_STARTED,
    KG_NODE_SUPERSEDED,
    KG_QUERY_COMPLETED,
    KG_SUBGRAPH_CREATED,
)
from opencontext_core.retrieval.query_planner import ContextBudget, KgQueryPlanner


def _kg(tmp_path: Path) -> KnowledgeGraph:
    return KnowledgeGraph(db_path=str(tmp_path / "kg.db"), project_id="proj")


def test_index_emits_events_and_writes_receipt(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    storage = tmp_path / "storage"
    kg = _kg(tmp_path)
    try:
        receipt = kg.index_with_receipt(tmp_path, storage_dir=storage)
        names = kg.observer.emitted_names()
        assert KG_INDEX_STARTED in names
        assert KG_INDEX_COMPLETED in names
        assert receipt.operation == "index"
        files = list((storage / "kg" / "receipts").glob("*.json"))
        assert files, "an index receipt file must be written"
    finally:
        kg.close()


def test_query_emits_completed_and_persists_receipt(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text("def parser():\n    return 1\n", encoding="utf-8")
    storage = tmp_path / "storage"
    kg = _kg(tmp_path)
    try:
        kg.index_project(tmp_path)
        observer = KgObserver(storage_dir=storage)
        planner = KgQueryPlanner(kg, observer=observer)
        plan = planner.plan("parser", node="apply", budget=ContextBudget(max_nodes=5))
        sub = planner.retrieve_subgraph(plan)
        names = observer.emitted_names()
        assert KG_SUBGRAPH_CREATED in names
        assert KG_QUERY_COMPLETED in names
        receipts = list((storage / "kg" / "receipts").glob("*.json"))
        assert receipts, "a query/retrieval receipt must be persisted"
        # The receipt records the subgraph served the request, no broad file read.
        import json

        data = json.loads(receipts[0].read_text(encoding="utf-8"))
        assert data["subgraph_used"] is True
        assert data["broad_file_read"] is False
        assert sub is not None
    finally:
        kg.close()


def test_supersede_emits_event_and_marks_node(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(
        "def alpha():\n    return 1\n\n\ndef beta():\n    return 2\n", encoding="utf-8"
    )
    kg = _kg(tmp_path)
    kg.observer = KgObserver()
    try:
        kg.index_project(tmp_path)
        rows = {r["name"]: r["id"] for r in kg.search("alpha", limit=20)}
        rows.update({r["name"]: r["id"] for r in kg.search("beta", limit=20)})
        assert "alpha" in rows and "beta" in rows
        ok = kg.supersede_node(rows["alpha"], rows["beta"])
        assert ok is True
        assert KG_NODE_SUPERSEDED in kg.observer.emitted_names()
        temporal = kg.db.get_node_temporal(rows["alpha"])
        assert temporal is not None
        assert temporal.status == "superseded"
        assert temporal.superseded_by == rows["beta"]
    finally:
        kg.close()


def test_owner_resolves_from_graph(tmp_path: Path) -> None:
    if subprocess.run(["git", "--version"], capture_output=True).returncode != 0:
        pytest.skip("git unavailable")
    # Build a tiny git repo so owner extraction has authorship to read.
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "a@b.c"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Ada Owner"], check=True)
    (tmp_path / "m.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-qm", "init"],
        check=True,
        env={
            "GIT_AUTHOR_NAME": "Ada Owner",
            "GIT_AUTHOR_EMAIL": "a@b.c",
            "GIT_COMMITTER_NAME": "Ada Owner",
            "GIT_COMMITTER_EMAIL": "a@b.c",
            "PATH": _path(),
        },
    )
    kg = _kg(tmp_path)
    try:
        kg.index_project(tmp_path)
        written = kg.extract_owners(tmp_path, {"m.py"})
        assert written >= 1
        # Resolution reads the graph (OWNS edge), not git.
        owner = kg.resolve_owner("m.py")
        assert owner == "Ada Owner"
    finally:
        kg.close()


def _path() -> str:
    import os

    return os.environ.get("PATH", "/usr/bin:/bin")
