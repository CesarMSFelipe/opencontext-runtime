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
    db.rebuild_fts()
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


def _seed_symbol_and_tests_db(tmp_path: Path) -> Path:
    """A DB with a ``BridgeDetector`` class plus many test functions that, under bare
    BM25, match more of a natural-language query's filler tokens than the class does.
    """
    db_path = tmp_path / "context_graph.db"
    db = GraphDatabase(db_path=db_path)
    db.init_schema()
    for path in ("src/bridge_detector.py", "tests/test_bridge_detector.py"):
        db.upsert_file(
            FileRecord(id=None, path=path, language="python", last_modified=1, hash=path, size=10)
        )
    db.upsert_nodes(
        [
            Node(
                id=None,
                name="BridgeDetector",
                kind="class",
                file_path="src/bridge_detector.py",
                line=52,
                column=0,
                end_line=120,
                language="python",
                container=None,
                docstring="Detects bridges in a project.",
                signature="class BridgeDetector",
                is_exported=True,
            )
        ]
    )
    # Several test functions whose bodies/docstrings carry the generic query words
    # (count, dict, type, returning) so bare BM25 floats them above the class.
    test_nodes = [
        Node(
            id=None,
            name=f"test_detect_case_{i}",
            kind="function",
            file_path="tests/test_bridge_detector.py",
            line=10 + i,
            column=0,
            end_line=12 + i,
            language="python",
            container=None,
            docstring="returns a dict mapping type to count; returning count by type",
            signature=f"def test_detect_case_{i}()",
            is_exported=False,
        )
        for i in range(8)
    ]
    db.upsert_nodes(test_nodes)
    # Enough unrelated noise nodes that each match the query's generic filler tokens to
    # push ``class BridgeDetector`` well past any reasonable BM25 top-k — modeling the
    # real repo, where the class lands at BM25 rank ~169. Without name-anchored recall
    # the definition is simply not a candidate.
    # Upsert per file: upsert_nodes prunes stale nodes of nodes[0].file_path, so a
    # single mixed-file batch would drop most. One file per noise node keeps all 300.
    for i in range(300):
        db.upsert_file(
            FileRecord(
                id=None,
                path=f"src/noise_{i}.py",
                language="python",
                last_modified=1,
                hash=f"n{i}",
                size=10,
            )
        )
        db.upsert_nodes(
            [
                Node(
                    id=None,
                    name=f"helper_count_dict_{i}",
                    kind="function",
                    file_path=f"src/noise_{i}.py",
                    line=1,
                    column=0,
                    end_line=2,
                    language="python",
                    container=None,
                    docstring="count dict type returning of to add by mapping value count dict",
                    signature=f"def helper_count_dict_{i}()",
                    is_exported=False,
                )
            ]
        )
    db.rebuild_fts()
    db.close()
    return db_path


def test_definition_query_surfaces_impl_not_only_its_tests(tmp_path: Path) -> None:
    """An "add X to <Symbol>" query must surface the file that DEFINES <Symbol>.

    Regression: bare BM25 over the natural-language query ranked many test functions
    (which match generic filler tokens count/dict/type) above ``class BridgeDetector``
    — whose only matching token is its name — so the defining impl was never even a
    candidate. Name-anchored candidate generation must include the definition, and the
    definition-affinity score must rank it at/near the top.
    """
    from opencontext_core.retrieval.planner import FTSRetrievalSource, RetrievalPlanner

    db_path = _seed_symbol_and_tests_db(tmp_path)
    planner = RetrievalPlanner([FTSRetrievalSource(db_path, tmp_path)])
    items = planner.retrieve(
        "Add count_by_type() to BridgeDetector returning a dict of bridge_type to count",
        top_k=5,
    )

    sources = [it.source for it in items]
    assert any("src/bridge_detector.py" in s for s in sources), (
        f"defining impl not retrieved as a candidate; got {sources}"
    )
    # The definition should outrank the tests (be the first impl-or-test hit).
    impl_rank = next(i for i, s in enumerate(sources) if "src/bridge_detector.py" in s)
    test_ranks = [i for i, s in enumerate(sources) if "tests/" in s]
    assert not test_ranks or impl_rank < min(test_ranks), (
        f"defining impl did not outrank its tests; order={sources}"
    )


def test_runtime_context_pack_uses_retrieval_planner(tmp_path: Path, monkeypatch) -> None:
    """Runtime candidate generation goes through RetrievalPlanner plans."""

    import opencontext_core.runtime as runtime_module
    from opencontext_core.retrieval.contracts import EvidenceRequest
    from opencontext_core.retrieval.planner import ManifestRetrievalSource, RetrievalPlanner

    class SpyPlanner:
        called = False

        def __init__(self, manifest: ProjectManifest, **_: object) -> None:
            self.manifest = manifest

        @classmethod
        def from_config(
            cls, manifest: ProjectManifest, _config: object, **_kw: object
        ) -> SpyPlanner:
            # Runtime builds the planner via from_config; route it to the spy.
            return cls(manifest)

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


def test_recent_failure_memory_boosts_matching_candidate(tmp_path: Path) -> None:
    """H2: a candidate that recent FAILURE memory flagged outranks an otherwise
    identical candidate — the recent_failure weight is fed in prod, not always 0."""
    from types import SimpleNamespace

    from opencontext_core.models.context import ContextItem, ContextPriority, DataClassification
    from opencontext_core.retrieval.contracts import EvidenceRequest, RetrievalSurface
    from opencontext_core.retrieval.planner import RetrievalPlanner

    def _item(item_id: str, source: str) -> ContextItem:
        return ContextItem(
            id=item_id,
            content="login token check",
            source=source,
            source_type="file",
            priority=ContextPriority.P2,
            tokens=5,
            score=0.7,
            metadata={"freshness": "current"},
            classification=DataClassification.INTERNAL,
            source_trust=0.8,
        )

    class _Source:
        name = "fixture"

        def retrieve(self, query: str, limit: int) -> list[ContextItem]:
            return [_item("a", "src/a.py"), _item("b", "src/b.py")]

    class _Memory:
        def search(self, query: str, *, scope: object = None, limit: int = 10) -> list[object]:
            return [SimpleNamespace(linked_nodes=["src/b.py"], confidence=0.9)]

    request = EvidenceRequest(
        query="login",
        root=tmp_path,
        surface=RetrievalSurface.RUNTIME,
        max_tokens=1000,
        risk_level="normal",
    )

    boosted = RetrievalPlanner([_Source()], memory_store=_Memory())
    plain = RetrievalPlanner([_Source()])

    assert boosted.plan(request, top_k=2).evidence[0].id == "b"
    # Without the failure memory the tie breaks the other way (token, id order).
    assert plain.plan(request, top_k=2).evidence[0].id == "a"
