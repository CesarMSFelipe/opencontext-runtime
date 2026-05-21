"""Knowledge graph facade for indexing and querying code symbols."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from opencontext_core.config import KnowledgeGraphConfig
from opencontext_core.indexing.graph_db import Edge, FileRecord, GraphDatabase, Node
from opencontext_core.indexing.tree_sitter_parser import (
    LANGUAGE_EXTENSIONS,
    TreeSitterParser,
)


class KnowledgeGraph:
    """Facade for the code knowledge graph.

    Provides high-level API for indexing projects, searching symbols,
    and querying relationships between code entities.
    """

    def __init__(
        self,
        config: KnowledgeGraphConfig | None = None,
        db_path: str | Path = ".storage/opencontext/codegraph.db",
    ) -> None:
        self.config = config or KnowledgeGraphConfig()
        self.db = GraphDatabase(db_path=db_path)
        self.parser = TreeSitterParser()
        self.db.init_schema()

    def index_file(self, file_path: str, content: str) -> dict[str, int]:
        """Index a single file into the knowledge graph.

        Args:
            file_path: Relative path to the file.
            content: File content.

        Returns:
            Dict with node_count and edge_count.
        """

        if not self.config.enabled:
            return {"nodes": 0, "edges": 0}

        # Skip if too large
        if len(content.encode("utf-8")) > self.config.max_file_size:
            return {"nodes": 0, "edges": 0}

        # Skip excluded patterns
        for pattern in self.config.exclude:
            if self._match_pattern(file_path, pattern):
                return {"nodes": 0, "edges": 0}

        # Detect language
        language = self.parser.detect_language(file_path)
        if language is None:
            return {"nodes": 0, "edges": 0}

        # Skip if language not in configured list (when list is non-empty)
        if self.config.languages and language not in self.config.languages:
            return {"nodes": 0, "edges": 0}

        # Delete existing data for this file
        self.db.delete_file_and_nodes(file_path)

        # Parse file
        parsed_symbols, parsed_edges = self.parser.parse_file(file_path, content)

        # Insert file record
        self.db.upsert_file(
            FileRecord(
                id=None,
                path=file_path,
                language=language,
                last_modified=0,
                hash="",
                size=len(content),
            )
        )

        # Insert symbols
        node_map: dict[str, int] = {}
        nodes: list[Node] = []
        for sym in parsed_symbols:
            node = Node(
                id=None,
                name=sym.name,
                kind=sym.kind,
                file_path=file_path,
                line=sym.line,
                column=sym.column,
                end_line=sym.end_line,
                language=language,
                container=sym.container,
                docstring=sym.docstring,
                signature=sym.signature,
                is_exported=sym.is_exported,
            )
            nodes.append(node)

        node_ids = self.db.upsert_nodes(nodes)

        # Build name-to-id map for edge resolution
        for i, sym in enumerate(parsed_symbols):
            key = f"{file_path}:{sym.name}:{sym.line}"
            node_map[key] = node_ids[i]
            node_map[sym.name] = node_ids[i]

        # Insert edges (resolve target names to node IDs when possible)
        edges: list[Edge] = []
        for pe in parsed_edges:
            source_id = node_map.get(pe.source_name)
            target_id = node_map.get(pe.target_name)

            if source_id is not None:
                edges.append(
                    Edge(
                        id=None,
                        source_node_id=source_id,
                        target_node_id=target_id or 0,
                        kind=pe.kind,
                        call_site_file=file_path,
                        call_site_line=pe.call_site_line,
                    )
                )

        if edges:
            self.db.upsert_edges(edges, file_path)

        return {"nodes": len(nodes), "edges": len(edges)}

    def index_project(self, root: str | Path) -> dict[str, Any]:
        """Index all supported files in a project directory.

        Args:
            root: Project root path.

        Returns:
            Statistics dict with files_indexed, nodes, edges.
        """

        if not self.config.enabled:
            return {"files_indexed": 0, "nodes": 0, "edges": 0}

        root_path = Path(root)
        files_indexed = 0
        total_nodes = 0
        total_edges = 0

        for ext in LANGUAGE_EXTENSIONS:
            for file_path in root_path.rglob(f"*{ext}"):
                rel_path = file_path.relative_to(root_path).as_posix()

                # Skip excluded
                skip = False
                for pattern in self.config.exclude:
                    if self._match_pattern(rel_path, pattern):
                        skip = True
                        break
                if skip:
                    continue

                try:
                    content = file_path.read_text(encoding="utf-8")
                    stats = self.index_file(rel_path, content)
                    files_indexed += 1
                    total_nodes += stats["nodes"]
                    total_edges += stats["edges"]
                except (OSError, UnicodeDecodeError):
                    continue

        return {
            "files_indexed": files_indexed,
            "nodes": total_nodes,
            "edges": total_edges,
        }

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search for symbols by name using FTS5."""

        return self.db.search_fts(query, limit)

    def get_stats(self) -> dict[str, int]:
        """Get database statistics."""

        return self.db.get_stats()

    def close(self) -> None:
        """Close the database connection."""

        self.db.close()

    @staticmethod
    def _match_pattern(file_path: str, pattern: str) -> bool:
        """Match a file path against a glob pattern."""

        import fnmatch

        # Simple glob matching
        if fnmatch.fnmatch(file_path, pattern):
            return True
        # Also check if pattern is a directory prefix
        if pattern.endswith("/**"):
            prefix = pattern[:-3]
            if file_path.startswith(prefix + "/") or file_path == prefix:
                return True
        return False
