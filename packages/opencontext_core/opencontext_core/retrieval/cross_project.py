"""Cross-project retrieval using graph tunnels."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.context.budgeting import estimate_tokens
from opencontext_core.embeddings.protocols import VectorStore
from opencontext_core.embeddings.stores import LocalVectorStore
from opencontext_core.indexing.graph_tunnel import (
    CrossProjectEdge,
    GraphTunnelStore,
    discover_tunnels_from_manifest,
)
from opencontext_core.models.context import ContextItem, ContextPriority
from opencontext_core.models.project import ProjectFile, ProjectManifest
from opencontext_core.paths import StorageMode, resolve_storage_path
from opencontext_core.retrieval.retriever import ProjectRetriever


class CrossProjectRetriever:
    """Retrieves context from linked projects via graph tunnels."""

    def __init__(
        self,
        manifest: ProjectManifest,
        tunnel_store: GraphTunnelStore,
        vector_store: VectorStore | None = None,
        auto_discover: bool = True,
        max_tokens_per_project: int = 1000,
    ) -> None:
        self.manifest = manifest
        self.tunnel_store = tunnel_store
        self.vector_store = vector_store or LocalVectorStore()
        self.auto_discover = auto_discover
        self.max_tokens_per_project = max_tokens_per_project
        self._local_retriever = ProjectRetriever(manifest)

        if auto_discover:
            discover_tunnels_from_manifest(manifest, tunnel_store)

    def retrieve(
        self,
        query: str,
        top_k: int = 20,
    ) -> list[ContextItem]:
        """Retrieve context from local project and linked cross-project tunnels."""
        items: list[ContextItem] = []

        local_items = self._local_retriever.retrieve(query, top_k=top_k)
        items.extend(local_items)

        cross_items = self._retrieve_cross_project(query, top_k=top_k)
        items.extend(cross_items)

        return items

    def _retrieve_cross_project(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[ContextItem]:
        """Retrieve context from linked projects using tunnels."""
        if not self.tunnel_store:
            return []

        tunnels = self.tunnel_store.list_tunnels(self.manifest.project_name)
        if not tunnels:
            return []

        cross_items: list[ContextItem] = []
        for tunnel in tunnels:
            # Determine the linked project direction for this manifest.
            if tunnel.source_project == self.manifest.project_name:
                target_project = tunnel.target_project
                edges = tunnel.edges
            elif tunnel.target_project == self.manifest.project_name:
                target_project = tunnel.source_project
                edges = [
                    CrossProjectEdge(
                        source_path=edge.target_path,
                        target_project=tunnel.source_project,
                        target_path=edge.source_path,
                        kind=edge.kind,
                        line=edge.line,
                    )
                    for edge in tunnel.edges
                ]
            else:
                continue  # Shouldn't happen

            # Load target project manifest
            target_manifest_path = (
                resolve_storage_path(
                    Path(self.manifest.root).parent / target_project,
                    StorageMode.local,
                )
                / "project_manifest.json"
            )
            if not target_manifest_path.exists():
                continue

            try:
                target_manifest = ProjectManifest.model_validate_json(
                    target_manifest_path.read_text(encoding="utf-8")
                )
            except Exception:
                continue

            # Build context items from target project symbols/files referenced by edges
            target_items = self._items_from_target_project(
                target_manifest,
                edges,
                query,
                self.max_tokens_per_project,
            )
            cross_items.extend(target_items)

        return cross_items

    def _items_from_target_project(
        self,
        target_manifest: ProjectManifest,
        edges: list[CrossProjectEdge],
        query: str,
        token_budget: int,
    ) -> list[ContextItem]:
        """Build ContextItems for a target project based on tunnel edges."""
        if not edges:
            return []

        # For now, use simple keyword matching on symbol names and file paths
        # More sophisticated: use vector store if available
        query_terms = query.lower().split()
        scored_items: list[tuple[float, ContextItem]] = []

        # Candidate selection from edges
        for edge in edges:
            # Find the relevant symbol or file in target manifest
            # Try exact file match
            matched_file = next(
                (f for f in target_manifest.files if f.path == edge.target_path),
                None,
            )
            if matched_file:
                # Score based on name matches
                score = self._score_match(matched_file, query_terms)
                if score > 0:
                    content = matched_file.summary
                    items_p = ContextItem(
                        id=f"cross:file:{target_manifest.project_name}:{matched_file.path}",
                        content=content,
                        source=f"[{target_manifest.project_name}] {matched_file.path}",
                        source_type="cross_file",
                        priority=ContextPriority.P2,
                        tokens=estimate_tokens(content),
                        score=score,
                        metadata={
                            "project": target_manifest.project_name,
                            "cross_reference": True,
                            "original_path": matched_file.path,
                        },
                    )
                    scored_items.append((score, items_p))
                    continue

            # Try symbol match within that file
            matched_symbols = [
                s
                for s in target_manifest.symbols
                if s.path == edge.target_path and any(q in s.name.lower() for q in query_terms)
            ]
            for symbol in matched_symbols[:3]:  # Limit to top 3 symbols per edge
                snippet = f"{symbol.kind} {symbol.name} in {symbol.path}:{symbol.line}"
                score = 0.8 if any(q in symbol.name.lower() for q in query_terms) else 0.4
                items_p = ContextItem(
                    id=f"cross:symbol:{target_manifest.project_name}:{symbol.id}",
                    content=snippet,
                    source=f"[{target_manifest.project_name}] {symbol.path}:{symbol.line}",
                    source_type="cross_symbol",
                    priority=ContextPriority.P2,
                    tokens=estimate_tokens(snippet),
                    score=score,
                    metadata={
                        "project": target_manifest.project_name,
                        "cross_reference": True,
                        "symbol_kind": symbol.kind,
                    },
                )
                scored_items.append((score, items_p))

        scored_items.sort(key=lambda x: x[0], reverse=True)

        selected: list[ContextItem] = []
        used_tokens = 0
        for _score, item in scored_items:
            if used_tokens + item.tokens > token_budget:
                break
            selected.append(item)
            used_tokens += item.tokens

        return selected

    def _score_match(self, file: ProjectFile, query_terms: list[str]) -> float:
        """Calculate simple match score for a file."""
        if not query_terms:
            return 1.0
        score = 0.0
        path_lower = file.path.lower()
        summary_lower = (file.summary or "").lower()
        for term in query_terms:
            if term in path_lower:
                score += 0.3
            if term in summary_lower:
                score += 0.5
        return min(1.0, score)
