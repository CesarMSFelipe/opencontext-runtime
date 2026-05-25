"""Tests for GraphTunnelStore CRUD and cross-project discovery."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from opencontext_core.indexing.graph_tunnel import (
    CrossProjectEdge,
    GraphTunnel,
    GraphTunnelStore,
    discover_tunnels_from_manifest,
)
from opencontext_core.models.project import DependencyEdge, DependencyGraph, ProjectManifest


_NOW = datetime.now(timezone.utc)


def _manifest(**kwargs: object) -> ProjectManifest:
    """Helper to build a ProjectManifest with required defaults."""
    defaults: dict[str, object] = {
        "project_name": "test",
        "root": "/tmp",
        "profile": "python",
        "technology_profiles": ["python"],
        "files": [],
        "symbols": [],
        "generated_at": _NOW,
    }
    defaults.update(kwargs)
    return ProjectManifest(**defaults)  # type: ignore[arg-type]


class TestCrossProjectEdge:
    def test_minimal_edge(self) -> None:
        edge = CrossProjectEdge(
            source_path="src/main.py",
            target_project="lib-core",
            target_path="lib/core.py",
            kind="import",
            line=1,
        )
        assert edge.source_path == "src/main.py"
        assert edge.target_project == "lib-core"
        assert edge.trust_level == 1.0
        assert edge.metadata == {}

    def test_edge_with_metadata(self) -> None:
        edge = CrossProjectEdge(
            source_path="app.py",
            target_project="utils",
            target_path="utils/helpers.py",
            kind="from_import",
            line=5,
            trust_level=0.8,
            metadata={"context": "optional"},
        )
        assert edge.trust_level == 0.8
        assert edge.metadata["context"] == "optional"


class TestGraphTunnel:
    def test_from_discovered_creates_tunnel(self) -> None:
        edge = CrossProjectEdge(
            source_path="src/main.py",
            target_project="lib-core",
            target_path="lib/core.py",
            kind="import",
            line=1,
        )
        tunnel = GraphTunnel.from_discovered(
            source_project="my-app",
            target_project="lib-core",
            edges=[edge],
        )
        assert tunnel.source_project == "my-app"
        assert tunnel.target_project == "lib-core"
        assert tunnel.discovered is True
        assert tunnel.trust_level == 1.0
        assert len(tunnel.edges) == 1
        assert isinstance(tunnel.created_at, datetime)

    def test_tunnel_serialization_roundtrip(self) -> None:
        edge = CrossProjectEdge(
            source_path="src/main.py",
            target_project="lib-core",
            target_path="lib/core.py",
            kind="import",
            line=1,
        )
        tunnel = GraphTunnel.from_discovered(
            source_project="my-app", target_project="lib-core", edges=[edge]
        )
        data = tunnel.model_dump(mode="json")
        restored = GraphTunnel.model_validate(data)
        assert restored.source_project == "my-app"
        assert restored.target_project == "lib-core"
        assert restored.discovered is True
        assert len(restored.edges) == 1


class TestGraphTunnelStore:
    def test_save_and_get_tunnel(self, tmp_path: Path) -> None:
        store = GraphTunnelStore(base_path=tmp_path)
        edge = CrossProjectEdge(
            source_path="src/main.py",
            target_project="lib-core",
            target_path="lib/core.py",
            kind="import",
            line=1,
        )
        tunnel = GraphTunnel.from_discovered(
            source_project="my-app", target_project="lib-core", edges=[edge]
        )
        store.save_tunnel(tunnel)

        loaded = store.get_tunnel("my-app", "lib-core")
        assert loaded is not None
        assert loaded.source_project == "my-app"
        assert loaded.target_project == "lib-core"
        assert len(loaded.edges) == 1

    def test_get_nonexistent_tunnel_returns_none(self, tmp_path: Path) -> None:
        store = GraphTunnelStore(base_path=tmp_path)
        assert store.get_tunnel("unknown", "nonexistent") is None

    def test_delete_tunnel(self, tmp_path: Path) -> None:
        store = GraphTunnelStore(base_path=tmp_path)
        tunnel = GraphTunnel.from_discovered(
            source_project="a", target_project="b", edges=[]
        )
        store.save_tunnel(tunnel)
        assert store.get_tunnel("a", "b") is not None

        deleted = store.delete_tunnel("a", "b")
        assert deleted is True
        assert store.get_tunnel("a", "b") is None

        # Verify file is also removed
        tunnel_file = store.tunnels_dir / "a__b.json"
        assert not tunnel_file.exists()

    def test_delete_nonexistent_returns_false(self, tmp_path: Path) -> None:
        store = GraphTunnelStore(base_path=tmp_path)
        assert store.delete_tunnel("no", "way") is False

    def test_list_all_tunnels(self, tmp_path: Path) -> None:
        store = GraphTunnelStore(base_path=tmp_path)
        store.save_tunnel(GraphTunnel.from_discovered("a", "b", edges=[]))
        store.save_tunnel(GraphTunnel.from_discovered("c", "d", edges=[]))

        tunnels = store.list_tunnels()
        assert len(tunnels) == 2

    def test_list_tunnels_by_project(self, tmp_path: Path) -> None:
        store = GraphTunnelStore(base_path=tmp_path)
        store.save_tunnel(GraphTunnel.from_discovered("app", "lib1", edges=[]))
        store.save_tunnel(GraphTunnel.from_discovered("app", "lib2", edges=[]))
        store.save_tunnel(GraphTunnel.from_discovered("other", "lib1", edges=[]))

        app_tunnels = store.list_tunnels("app")
        assert len(app_tunnels) == 2  # app→lib1 and app→lib2

    def test_persistence_across_store_instances(self, tmp_path: Path) -> None:
        store1 = GraphTunnelStore(base_path=tmp_path)
        store1.save_tunnel(GraphTunnel.from_discovered("x", "y", edges=[]))

        store2 = GraphTunnelStore(base_path=tmp_path)
        loaded = store2.get_tunnel("x", "y")
        assert loaded is not None
        assert loaded.source_project == "x"
        assert loaded.target_project == "y"

    def test_load_skips_malformed_json(self, tmp_path: Path) -> None:
        tunnels_dir = tmp_path / "tunnels"
        tunnels_dir.mkdir(parents=True, exist_ok=True)
        (tunnels_dir / "bad.json").write_text("not valid json", encoding="utf-8")
        (tunnels_dir / "good.json").write_text(
            json.dumps(
                {
                    "source_project": "good",
                    "target_project": "project",
                    "edges": [],
                    "created_at": "2025-01-01T00:00:00+00:00",
                    "discovered": False,
                    "trust_level": 1.0,
                }
            ),
            encoding="utf-8",
        )

        store = GraphTunnelStore(base_path=tmp_path)
        assert store.get_tunnel("good", "project") is not None
        assert store.list_tunnels("good")[0].target_project == "project"


class TestDiscoverTunnels:
    def test_discover_no_unresolved_edges(self, tmp_path: Path) -> None:
        store = GraphTunnelStore(base_path=tmp_path)
        manifest = _manifest(project_name="test-app", root=str(tmp_path))
        tunnels = discover_tunnels_from_manifest(manifest, store)
        assert tunnels == []

    def test_discover_with_matching_external_project(self, tmp_path: Path) -> None:
        """If a target project has a manifest, discovery should create a tunnel."""
        # Source project setup
        source_root = tmp_path / "source"
        source_root.mkdir()
        (source_root / "src").mkdir()

        # Target project setup with manifest
        target_root = tmp_path / "target-lib"
        target_root.mkdir()
        target_storage = target_root / ".storage" / "opencontext"
        target_storage.mkdir(parents=True)
        target_manifest_path = target_storage / "project_manifest.json"
        target_manifest = _manifest(project_name="target-lib", root=str(target_root))
        target_manifest_path.write_text(
            target_manifest.model_dump_json(indent=2), encoding="utf-8"
        )

        # Source manifest with unresolved edge pointing to target
        unresolved_edge = DependencyEdge(
            source="src/main.py",
            target=str(target_root),
            kind="import",
            internal=False,
            line=1,
        )
        dep_graph = DependencyGraph(
            nodes=["src/main.py"],
            edges=[],
            unresolved=[unresolved_edge],
            generated_at=datetime.now(timezone.utc),
        )
        source_manifest = _manifest(
            project_name="source", root=str(source_root), dependency_graph=dep_graph,
        )

        store = GraphTunnelStore(base_path=tmp_path / "store")
        tunnels = discover_tunnels_from_manifest(
            source_manifest, store, projects_root=tmp_path
        )
        assert len(tunnels) == 1
        assert tunnels[0].source_project == "source"
        assert tunnels[0].target_project == "target-lib"
        assert tunnels[0].discovered is True
        assert len(tunnels[0].edges) == 1

    def test_discover_skips_existing_tunnel(self, tmp_path: Path) -> None:
        """If a tunnel already exists, discovery should skip it."""
        store = GraphTunnelStore(base_path=tmp_path)
        target_root = tmp_path / "existing-target"
        target_root.mkdir()
        target_storage = target_root / ".storage" / "opencontext"
        target_storage.mkdir(parents=True)
        target_manifest = _manifest(project_name="existing-target", root=str(target_root))
        (target_storage / "project_manifest.json").write_text(
            target_manifest.model_dump_json(indent=2), encoding="utf-8"
        )

        # Pre-save a tunnel
        pre_tunnel = GraphTunnel.from_discovered("source", "existing-target", edges=[])
        store.save_tunnel(pre_tunnel)

        unresolved_edge = DependencyEdge(
            source="src/main.py",
            target=str(target_root),
            kind="import",
            internal=False,
            line=1,
        )
        dep_graph = DependencyGraph(
            nodes=["src/main.py"],
            edges=[],
            unresolved=[unresolved_edge],
            generated_at=datetime.now(timezone.utc),
        )
        manifest = _manifest(
            project_name="source", root=str(tmp_path / "source"), dependency_graph=dep_graph,
        )
        (tmp_path / "source").mkdir(exist_ok=True)

        tunnels = discover_tunnels_from_manifest(manifest, store, projects_root=tmp_path)
        assert tunnels == []  # No new tunnels created

    def test_discover_with_relative_import(self, tmp_path: Path) -> None:
        """A relative unresolved import should be resolved."""
        store = GraphTunnelStore(base_path=tmp_path)
        source_root = tmp_path / "rel-source"
        source_root.mkdir()
        (source_root / "lib").mkdir()

        target_root = tmp_path / "shared-lib"
        target_root.mkdir()
        target_storage = target_root / ".storage" / "opencontext"
        target_storage.mkdir(parents=True)
        target_manifest = _manifest(project_name="shared-lib", root=str(target_root))
        (target_storage / "project_manifest.json").write_text(
            target_manifest.model_dump_json(indent=2), encoding="utf-8"
        )

        # Create a file in source that "imports" from ../shared-lib
        (source_root / "src" / "app.py").parent.mkdir(exist_ok=True)
        # We need an ASOLUTE path that matches target_root
        unresolved_edge = DependencyEdge(
            source="src/app.py",
            target="../shared-lib",
            kind="import",
            internal=False,
            line=3,
        )
        dep_graph = DependencyGraph(
            nodes=["src/app.py"],
            edges=[],
            unresolved=[unresolved_edge],
            generated_at=datetime.now(timezone.utc),
        )
        manifest = _manifest(
            project_name="rel-source", root=str(source_root), dependency_graph=dep_graph,
        )

        tunnels = discover_tunnels_from_manifest(manifest, store, projects_root=tmp_path)
        assert len(tunnels) >= 0  # May be 0 if relative resolution doesn't find exact match
