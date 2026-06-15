"""LocalVectorStore wired as an optional semantic retrieval source.

A query with no FTS/graph hit but a semantic (vector) match must return the
vector candidate. The source is gated on config.embedding.enabled; default off
must leave planner behavior unchanged (no vector source attached).
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from opencontext_core.compat import UTC
from opencontext_core.embeddings.generators import DeterministicEmbeddingGenerator
from opencontext_core.embeddings.models import EmbeddedItem
from opencontext_core.embeddings.stores import LocalVectorStore
from opencontext_core.models.context import DataClassification


def _seed_store(base_path: Path, generator: DeterministicEmbeddingGenerator) -> LocalVectorStore:
    store = LocalVectorStore(base_path)
    text = "token bucket rate limiter implementation"
    vector = asyncio.run(generator.embed([text]))[0]
    item = EmbeddedItem(
        id="emb-1",
        item_id="src/ratelimit.py:10:TokenBucket",
        item_type="symbol",
        project_name="demo",
        content=text,
        vector=vector,
        classification=DataClassification.INTERNAL,
        created_at=datetime.now(tz=UTC),
        embedded_at=datetime.now(tz=UTC),
        metadata={"source_path": "src/ratelimit.py"},
    )
    store.store([item])
    return store


def test_vector_source_returns_semantic_candidate(tmp_path: Path) -> None:
    from opencontext_core.retrieval.planner import VectorRetrievalSource

    generator = DeterministicEmbeddingGenerator(dimensions=64)
    store = _seed_store(tmp_path / "vs", generator)

    source = VectorRetrievalSource(store, generator, project_name="demo")
    items = source.retrieve("token bucket rate limiter implementation", limit=5)

    assert items
    item = items[0]
    assert item.metadata["retrieval_source"] == "vector"
    assert item.source_type == "vector"
    assert "TokenBucket" in item.id or "TokenBucket" in item.source


def test_vector_candidate_surfaces_when_no_fts_or_graph_hit(tmp_path: Path) -> None:
    """A query with only a semantic match returns the vector candidate via plan()."""
    from opencontext_core.retrieval.planner import RetrievalPlanner, VectorRetrievalSource

    class _EmptySource:
        name = "manifest"

        def retrieve(self, query: str, limit: int):
            return []

    generator = DeterministicEmbeddingGenerator(dimensions=64)
    store = _seed_store(tmp_path / "vs", generator)
    vsource = VectorRetrievalSource(store, generator, project_name="demo")

    planner = RetrievalPlanner([_EmptySource(), vsource])
    items = planner.retrieve("token bucket rate limiter implementation", top_k=5)

    assert items
    assert any(i.metadata.get("retrieval_source") == "vector" for i in items)


def test_planner_factory_off_by_default(tmp_path: Path) -> None:
    """RetrievalPlanner.from_config must not attach a vector source when disabled."""
    from opencontext_core.config import OpenContextConfig, default_config_data
    from opencontext_core.models.project import (
        DependencyGraph,
        FileKind,
        ProjectFile,
        ProjectManifest,
    )
    from opencontext_core.retrieval.planner import RetrievalPlanner

    src = tmp_path / "src" / "auth.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("def authenticate_user():\n    return True\n", encoding="utf-8")
    manifest = ProjectManifest(
        project_name="demo",
        root=str(tmp_path),
        profile="python",
        technology_profiles=["python"],
        files=[
            ProjectFile(
                id="src/auth.py",
                path="src/auth.py",
                language="python",
                file_type=FileKind.CODE,
                tokens=20,
                size_bytes=src.stat().st_size,
                summary="auth",
            )
        ],
        symbols=[],
        dependency_graph=DependencyGraph(
            nodes=["src/auth.py"], edges=[], unresolved=[], generated_at=datetime.now(tz=UTC)
        ),
        generated_at=datetime.now(tz=UTC),
    )

    config = OpenContextConfig.model_validate(default_config_data())
    assert config.embedding.enabled is False

    planner = RetrievalPlanner.from_config(manifest, config, storage_path=tmp_path / "st")
    source_names = {s.name for s in planner.sources}
    assert "vector" not in source_names


def test_planner_factory_attaches_vector_when_enabled(tmp_path: Path) -> None:
    from opencontext_core.config import OpenContextConfig, default_config_data
    from opencontext_core.models.project import (
        DependencyGraph,
        FileKind,
        ProjectFile,
        ProjectManifest,
    )
    from opencontext_core.retrieval.planner import RetrievalPlanner

    src = tmp_path / "src" / "auth.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("def authenticate_user():\n    return True\n", encoding="utf-8")
    manifest = ProjectManifest(
        project_name="demo",
        root=str(tmp_path),
        profile="python",
        technology_profiles=["python"],
        files=[
            ProjectFile(
                id="src/auth.py",
                path="src/auth.py",
                language="python",
                file_type=FileKind.CODE,
                tokens=20,
                size_bytes=src.stat().st_size,
                summary="auth",
            )
        ],
        symbols=[],
        dependency_graph=DependencyGraph(
            nodes=["src/auth.py"], edges=[], unresolved=[], generated_at=datetime.now(tz=UTC)
        ),
        generated_at=datetime.now(tz=UTC),
    )

    data = default_config_data()
    data["embedding"]["enabled"] = True
    data["embedding"]["provider"] = "local"
    config = OpenContextConfig.model_validate(data)

    planner = RetrievalPlanner.from_config(manifest, config, storage_path=tmp_path / "st")
    source_names = {s.name for s in planner.sources}
    assert "vector" in source_names
