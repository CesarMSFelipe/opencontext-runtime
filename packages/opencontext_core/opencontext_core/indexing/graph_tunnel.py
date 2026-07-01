"""Cross-project graph tunnel models and storage.

Enables linked context retrieval across project boundaries by discovering
and persisting relationships between independently indexed projects.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import UTC
from opencontext_core.models.project import DependencyEdge, ProjectManifest
from opencontext_core.paths import StorageMode, resolve_storage_path, resolve_workspace_path


class CrossProjectEdge(BaseModel):
    """A dependency edge that crosses into another project."""

    model_config = ConfigDict(extra="forbid")

    source_path: str = Field(description="Source file path within current project.")
    target_project: str = Field(description="Name of the linked target project.")
    target_path: str = Field(description="Target file path within the target project.")
    kind: str = Field(description="Dependency kind: 'import', 'from_import', 'require', etc.")
    line: int = Field(description="Line number where dependency occurs in source.")
    trust_level: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Trust level for this cross-project link (0-1)."
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional edge metadata.")


class GraphTunnel(BaseModel):
    """A bidirectional link between two projects."""

    model_config = ConfigDict(extra="forbid")

    source_project: str = Field(description="Source project name.")
    target_project: str = Field(description="Target project name.")
    edges: list[CrossProjectEdge] = Field(description="Edges forming this tunnel.")
    created_at: datetime = Field(description="Tunnel creation timestamp.")
    discovered: bool = Field(
        default=False,
        description="Whether tunnel was auto-discovered (True) or manually created (False).",
    )
    trust_level: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Overall trust level for this project link."
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional tunnel metadata."
    )

    @classmethod
    def from_discovered(
        cls,
        source_project: str,
        target_project: str,
        edges: list[CrossProjectEdge],
    ) -> GraphTunnel:
        """Create a tunnel from auto-discovery."""
        return cls(
            source_project=source_project,
            target_project=target_project,
            edges=edges,
            created_at=datetime.now(tz=UTC),
            discovered=True,
            trust_level=1.0,  # Auto-discovered tunnels are fully trusted initially
        )


class GraphTunnelStore:
    """Persistent storage for cross-project graph tunnels.

    Stores tunnel definitions as JSON files under .storage/opencontext/tunnels/.
    """

    def __init__(self, base_path: Path | str = ".storage/opencontext") -> None:
        self.base_path = Path(base_path)
        # Created lazily on first save (see save_tunnel) so an indexed project
        # with no cross-project tunnels leaves no empty ``tunnels/`` directory.
        self.tunnels_dir = self.base_path / "tunnels"
        self._index: dict[tuple[str, str], GraphTunnel] = {}
        self._load()

    def _load(self) -> None:
        """Load all tunnel definitions from disk."""
        self._index.clear()
        if not self.tunnels_dir.exists():
            return
        for path in self.tunnels_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                tunnel = GraphTunnel.model_validate(data)
                key = (tunnel.source_project, tunnel.target_project)
                self._index[key] = tunnel
            except Exception:
                continue  # Skip malformed

    def save_tunnel(self, tunnel: GraphTunnel) -> None:
        """Persist a tunnel definition."""
        key = (tunnel.source_project, tunnel.target_project)
        self._index[key] = tunnel
        self.tunnels_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{tunnel.source_project}__{tunnel.target_project}.json"
        path = self.tunnels_dir / filename
        path.write_text(tunnel.model_dump_json(indent=2), encoding="utf-8")

    def get_tunnel(self, source: str, target: str) -> GraphTunnel | None:
        """Retrieve a tunnel by project names."""
        return self._index.get((source, target))

    def list_tunnels(self, project: str | None = None) -> list[GraphTunnel]:
        """List all tunnels, optionally filtered by a project."""
        if project is None:
            return list(self._index.values())
        return [
            tunnel for (src, tgt), tunnel in self._index.items() if src == project or tgt == project
        ]

    def delete_tunnel(self, source: str, target: str) -> bool:
        """Delete a tunnel definition. Returns True if deleted."""
        key = (source, target)
        tunnel = self._index.pop(key, None)
        if tunnel is None:
            return False
        filename = f"{source}__{target}.json"
        path = self.tunnels_dir / filename
        if path.exists():
            path.unlink()
        return True


def discover_tunnels_from_manifest(
    manifest: ProjectManifest,
    tunnel_store: GraphTunnelStore,
    projects_root: Path | None = None,
) -> list[GraphTunnel]:
    """Auto-discover cross-project tunnels from dependency graph.

    Scans the manifest's dependency graph for unresolved external imports
    that point to other OpenContext projects within the workspace.

    Args:
        manifest: Current project manifest
        tunnel_store: Store to check for existing tunnels and save new ones
        projects_root: Root directory containing sibling projects (default: parent of project root)

    Returns:
        List of newly discovered tunnels
    """
    new_tunnels: list[GraphTunnel] = []
    projects_root = projects_root or Path(manifest.root).parent

    # Group unresolved edges by potential target project
    potential_targets: dict[str, list[tuple[DependencyEdge, Path]]] = {}
    if manifest.dependency_graph is None:
        return []

    for edge in manifest.dependency_graph.unresolved:
        # Resolve relative paths to absolute
        target_abs = _resolve_external_path(Path(manifest.root) / edge.source, edge.target)
        if target_abs is None:
            continue

        # Check if this absolute path contains a manifest
        candidate_manifest = (
            resolve_storage_path(target_abs, StorageMode.local) / "project_manifest.json"
        )
        if not candidate_manifest.exists():
            # Try legacy location
            candidate_manifest = (
                resolve_workspace_path(target_abs, StorageMode.local) / "manifest.json"
            )
            if not candidate_manifest.exists():
                continue

        # Load the target project manifest to get its name
        try:
            target_manifest = ProjectManifest.model_validate_json(
                candidate_manifest.read_text(encoding="utf-8")
            )
        except Exception:
            continue

        target_project_name = target_manifest.project_name
        key = (manifest.project_name, target_project_name)

        # Skip if tunnel already exists
        if tunnel_store.get_tunnel(*key) is not None:
            continue

        edges_list = potential_targets.setdefault(target_project_name, [])
        edges_list.append((edge, target_abs))

    # Create tunnels for each discovered target project
    for target_project, edge_infos in potential_targets.items():
        cross_edges = []
        for edge, target_abs in edge_infos:
            # Compute target path relative to target project root
            try:
                rel_target = Path(target_abs).relative_to(projects_root / target_project)
            except ValueError:
                rel_target = Path(edge.target)
            cross_edges.append(
                CrossProjectEdge(
                    source_path=edge.source,
                    target_project=target_project,
                    target_path=str(rel_target),
                    kind=edge.kind,
                    line=edge.line,
                    trust_level=1.0,
                )
            )

        tunnel = GraphTunnel.from_discovered(
            source_project=manifest.project_name,
            target_project=target_project,
            edges=cross_edges,
        )
        tunnel_store.save_tunnel(tunnel)
        new_tunnels.append(tunnel)

    return new_tunnels


def _resolve_external_path(source_file: Path, target: str) -> Path | None:
    """Attempt to resolve an external dependency to an absolute path."""
    # Handle relative imports
    if target.startswith("."):
        resolved = (source_file.parent / target).resolve()
        if resolved.exists():
            return resolved
        # Try adding extensions
        for ext in [".py", ".js", ".ts", ".php"]:
            if (resolved.with_suffix(resolved.suffix + ext)).exists():
                return resolved.with_suffix(resolved.suffix + ext)
        return None

    # Handle absolute/namespace imports (could be node_modules or installed packages)
    # For node.js, check node_modules
    node_modules = source_file.parent / "node_modules" / target.replace(".", "/")
    if node_modules.exists():
        return node_modules.resolve()

    # For python, check common paths - but we'd need sys.path
    # Skip these for now - they're typically external libraries

    return None
