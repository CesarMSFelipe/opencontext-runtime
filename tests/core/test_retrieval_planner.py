"""Tests for unified retrieval planner."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from conftest import create_sample_project, write_config
from opencontext_core.compat import UTC
from opencontext_core.indexing.graph_db import FileRecord, GraphDatabase, Node
from opencontext_core.models.context import ContextItem
from opencontext_core.models.project import DependencyGraph, FileKind, ProjectFile, ProjectManifest
from opencontext_core.runtime import OpenContextRuntime


def _manifest(root: Path) -> ProjectManifest:
    source = root / "src" / "auth.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        "def authenticate_user(username: str, password: str) -> bool:\n"
        "    return verify_password(username, password)\n",
        encoding="utf-8",
    )
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


def test_manifest_source_preserves_existing_project_retriever_behavior(tmp_path: Path) -> None:
    """Manifest source returns ContextItems from the existing ProjectRetriever path."""

    from opencontext_core.retrieval.planner import ManifestRetrievalSource, RetrievalPlanner

    source = ManifestRetrievalSource(_manifest(tmp_path))
    items = RetrievalPlanner([source]).retrieve("authenticate user", top_k=5)

    assert items
    assert items[0].source == "src/auth.py"
    assert items[0].metadata["retrieval_source"] == "manifest"
    assert "retrieval_rationale" in items[0].metadata


def test_planner_falls_back_when_graph_source_fails(tmp_path: Path) -> None:
    """A failing additive source must not block manifest candidates."""

    from opencontext_core.retrieval.planner import ManifestRetrievalSource, RetrievalPlanner

    class FailingSource:
        name = "broken_graph"

        def retrieve(self, query: str, limit: int) -> list[ContextItem]:
            raise RuntimeError("graph unavailable")

    planner = RetrievalPlanner([FailingSource(), ManifestRetrievalSource(_manifest(tmp_path))])
    items = planner.retrieve(
        "authenticate user",
        top_k=5,
    )

    assert items
    assert {item.metadata["retrieval_source"] for item in items} == {"manifest"}


def test_graph_source_emits_provenance_and_freshness_metadata(tmp_path: Path) -> None:
    """Graph-derived candidates carry source, rationale, and provenance metadata."""

    from opencontext_core.retrieval.planner import GraphRetrievalSource

    source_file = tmp_path / "src" / "auth.py"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text(
        "def authenticate_user(username: str, password: str) -> bool:\n    return True\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "codegraph.db"
    db = GraphDatabase(db_path=db_path)
    db.init_schema()
    db.upsert_file(
        FileRecord(
            id=None,
            path="src/auth.py",
            language="python",
            last_modified=1,
            hash="abc123",
            size=source_file.stat().st_size,
        )
    )
    db.upsert_nodes(
        [
            Node(
                id=None,
                name="authenticate_user",
                kind="function",
                file_path="src/auth.py",
                line=1,
                column=0,
                end_line=2,
                language="python",
                container=None,
                docstring="Authenticate a user.",
                signature="def authenticate_user(username: str, password: str) -> bool",
                is_exported=True,
            )
        ]
    )
    db.close()

    items = GraphRetrievalSource(db_path=db_path, root=tmp_path).retrieve(
        "authenticate_user",
        limit=3,
    )

    assert len(items) == 1
    item = items[0]
    assert item.source == "src/auth.py:1"
    assert item.source_type == "graph_symbol"
    assert "authenticate_user" in item.content
    assert item.metadata["retrieval_source"] == "graph"
    assert item.metadata["freshness"] == "unknown"
    assert item.metadata["graph_provenance"]["db_path"] == str(db_path)


def test_runtime_context_pack_uses_retrieval_planner(tmp_path: Path, monkeypatch) -> None:
    """Runtime candidate generation goes through RetrievalPlanner plans."""

    import opencontext_core.runtime as runtime_module
    from opencontext_core.retrieval.contracts import EvidenceRequest
    from opencontext_core.retrieval.planner import ManifestRetrievalSource, RetrievalPlanner

    class SpyPlanner:
        called = False

        def __init__(self, manifest: ProjectManifest, *, graph_db_path: Path | None = None) -> None:
            self.manifest = manifest
            self.graph_db_path = graph_db_path

        def plan(self, request: EvidenceRequest, top_k: int):
            SpyPlanner.called = True
            return RetrievalPlanner([ManifestRetrievalSource(self.manifest)]).plan(request, top_k)

    project_root = tmp_path / "project"
    project_root.mkdir()
    create_sample_project(project_root)
    runtime = OpenContextRuntime(
        config_path=write_config(tmp_path, project_root),
        storage_path=tmp_path / ".storage/opencontext",
    )
    runtime.index_project(project_root)
    monkeypatch.setattr(runtime_module, "RetrievalPlanner", SpyPlanner)

    pack = runtime.build_context_pack("authentication", max_tokens=1000)

    assert SpyPlanner.called is True
    assert pack.included
