"""Knowledge graph facade for indexing and querying code symbols."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from opencontext_core.config import KnowledgeGraphConfig
from opencontext_core.indexing.graph_db import Edge, FileRecord, GraphDatabase, Node
from opencontext_core.indexing.tree_sitter_parser import (
    LANGUAGE_EXTENSIONS,
    TreeSitterParser,
)


def _stable_symbol_id(project_id: str, file_path: str, qualified_name: str, kind: str) -> str:
    """Return a 16-char deterministic hex ID for a symbol, unique across files."""
    payload = f"{project_id}:{file_path}:{qualified_name}:{kind}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


class KnowledgeGraph:
    """Facade for the code knowledge graph.

    Provides high-level API for indexing projects, searching symbols,
    and querying relationships between code entities.
    """

    def __init__(
        self,
        config: KnowledgeGraphConfig | None = None,
        db_path: str | Path = ".storage/opencontext/context_graph.db",
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
        # Only store edges where both source and target are known in this file.
        # Cross-file edges are resolved in a second pass by index_project().
        edges: list[Edge] = []
        for pe in parsed_edges:
            source_id = node_map.get(pe.source_name)
            target_id = node_map.get(pe.target_name)

            if source_id is not None and target_id is not None:
                edges.append(
                    Edge(
                        id=None,
                        source_node_id=source_id,
                        target_node_id=target_id,
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

        # Collect files to index
        file_contents: list[tuple[str, str]] = []
        for ext in LANGUAGE_EXTENSIONS:
            for file_path in root_path.rglob(f"*{ext}"):
                rel_path = file_path.relative_to(root_path).as_posix()
                skip = False
                for pattern in self.config.exclude:
                    if self._match_pattern(rel_path, pattern):
                        skip = True
                        break
                if skip:
                    continue
                try:
                    content = file_path.read_text(encoding="utf-8")
                    file_contents.append((rel_path, content))
                except (OSError, UnicodeDecodeError):
                    continue

        # Pass 1: index all files (creates nodes + intra-file edges)
        for rel_path, content in file_contents:
            stats = self.index_file(rel_path, content)
            files_indexed += 1
            total_nodes += stats["nodes"]
            total_edges += stats["edges"]

        # Pass 2: resolve cross-file edges using the complete global node map
        cross_edges = self._resolve_cross_file_edges(file_contents)
        if cross_edges:
            conn = self.db._connect()
            _SQL = "INSERT OR IGNORE INTO edges (source_node_id, target_node_id, kind, call_site_file, call_site_line) VALUES (?, ?, ?, ?, ?)"  # noqa: E501
            conn.executemany(
                _SQL,
                [
                    (e.source_node_id, e.target_node_id, e.kind, e.call_site_file, e.call_site_line)
                    for e in cross_edges
                ],
            )
            conn.commit()
            total_edges += len(cross_edges)

        return {
            "files_indexed": files_indexed,
            "nodes": total_nodes,
            "edges": total_edges,
        }

    def _resolve_cross_file_edges(self, file_contents: list[tuple[str, str]]) -> list[Edge]:
        """Second pass: resolve calls whose target lives in a different file."""

        conn = self.db._connect()

        # Build global (name, file_path) → node_id map; avoids silent overwrite on same-name symbols
        global_map: dict[tuple[str, str], int] = {}
        node_files: dict[int, str] = {}
        for row in conn.execute("SELECT id, name, file_path FROM nodes").fetchall():
            global_map[(row["name"], row["file_path"])] = row["id"]
            node_files[row["id"]] = row["file_path"]

        def _resolve(name: str, hint_file: str = "") -> int | None:
            # Try exact (name, hint_file) first, then any file, then short name
            result = global_map.get((name, hint_file))
            if result is None:
                # Fall back: search all files for this name
                for (n, _fp), nid in global_map.items():
                    if n == name:
                        return nid
            if result is None and "." in name:
                short = name.rsplit(".", 1)[-1]
                for (n, _fp), nid in global_map.items():
                    if n == short:
                        return nid
            return result

        # Collect already-stored (source, target) pairs to avoid duplicates
        existing: set[tuple[int, int]] = set()
        for row in conn.execute("SELECT source_node_id, target_node_id FROM edges").fetchall():
            existing.add((row["source_node_id"], row["target_node_id"]))

        cross_edges: list[Edge] = []
        for file_path, content in file_contents:
            language = self.parser.detect_language(file_path)
            if language is None:
                continue
            try:
                _, parsed_edges = self.parser.parse_file(file_path, content)
            except Exception:
                continue

            for pe in parsed_edges:
                source_id = _resolve(pe.source_name, file_path)
                target_id = _resolve(pe.target_name)
                if source_id is None or target_id is None:
                    continue
                if (source_id, target_id) in existing:
                    continue
                src_file = node_files.get(source_id, "")
                tgt_file = node_files.get(target_id, "")
                if src_file and tgt_file and src_file != tgt_file:
                    cross_edges.append(
                        Edge(
                            id=None,
                            source_node_id=source_id,
                            target_node_id=target_id,
                            kind=pe.kind,
                            call_site_file=file_path,
                            call_site_line=pe.call_site_line,
                        )
                    )
                    existing.add((source_id, target_id))

        return cross_edges

    def finalize_cross_file_edges(self, file_contents: list[tuple[str, str]]) -> int:
        """Resolve and store cross-file edges from an externally-managed file batch.

        Call this after a series of index_file() calls to wire up inter-file relationships.
        Returns the number of cross-file edges added.
        """
        cross_edges = self._resolve_cross_file_edges(file_contents)
        if not cross_edges:
            return 0
        conn = self.db._connect()
        _SQL = "INSERT OR IGNORE INTO edges (source_node_id, target_node_id, kind, call_site_file, call_site_line) VALUES (?, ?, ?, ?, ?)"  # noqa: E501
        conn.executemany(
            _SQL,
            [
                (e.source_node_id, e.target_node_id, e.kind, e.call_site_file, e.call_site_line)
                for e in cross_edges
            ],
        )
        conn.commit()
        return len(cross_edges)

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
