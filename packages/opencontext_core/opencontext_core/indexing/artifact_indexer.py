"""Index non-code context artifacts (schemas, specs, configs) into the knowledge graph."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from opencontext_core.config import ContextArtifact
    from opencontext_core.indexing.graph_db import GraphDatabase, Node

_SNIPPET_CHARS = 800


def index_artifacts(
    artifacts: list[ContextArtifact],
    root: Path,
    db: GraphDatabase,
    project_id: str = "",
) -> int:
    """Upsert each artifact as a KG node with kind='artifact'. Returns count indexed."""
    from opencontext_core.indexing.graph_db import Node
    from opencontext_core.indexing.knowledge_graph import _stable_symbol_id

    indexed = 0
    for artifact in artifacts:
        path = root / artifact.path
        if not path.exists():
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        node_id = _stable_symbol_id(project_id, artifact.path, artifact.name, "artifact")
        node = Node(
            id=node_id,
            name=artifact.name,
            kind="artifact",
            file_path=artifact.path,
            line=1,
            column=0,
            end_line=len(content.splitlines()),
            language=artifact.type,
            container=None,
            docstring=f"[{artifact.type}] {artifact.path}",
            signature=None,
            is_exported=True,
            content_snippet=content[:_SNIPPET_CHARS],
        )
        db.upsert_nodes([node], project_id=project_id)
        indexed += 1

    return indexed
