"""Knowledge graph facade for indexing and querying code symbols."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class StaleReport:
    """Indexed files that drifted from disk since the last index."""

    changed: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.changed) + len(self.deleted)


class KnowledgeGraph:
    """Facade for the code knowledge graph.

    Provides high-level API for indexing projects, searching symbols,
    and querying relationships between code entities.
    """

    def __init__(
        self,
        config: KnowledgeGraphConfig | None = None,
        db_path: str | Path = ".storage/opencontext/context_graph.db",
        project_id: str = "",
    ) -> None:
        self.config = config or KnowledgeGraphConfig()
        self.db = GraphDatabase(db_path=db_path)
        self.parser = TreeSitterParser()
        # Stable node ids are scoped per project so the same file path in two
        # different projects/DBs never collides. Default to the db parent name.
        self.project_id = project_id or Path(db_path).resolve().parent.name
        self.db.init_schema()

    def index_file(self, file_path: str, content: str) -> dict[str, Any]:
        """Index a single file into the knowledge graph.

        Args:
            file_path: Relative path to the file.
            content: File content.

        Returns:
            Dict with ``nodes``/``edges`` counts plus ``parse_mode`` and ``degraded``
            so callers can tell a precise tree-sitter parse from a regex fallback.
        """

        if not self.config.enabled:
            return {"nodes": 0, "edges": 0, "parse_mode": "skipped", "degraded": False}

        skipped = {"nodes": 0, "edges": 0, "parse_mode": "skipped", "degraded": False}

        # Skip if too large
        if len(content.encode("utf-8")) > self.config.max_file_size:
            return skipped

        # Skip excluded patterns
        for pattern in self.config.exclude:
            if self._match_pattern(file_path, pattern):
                return skipped

        # Detect language
        language = self.parser.detect_language(file_path)
        if language is None:
            return skipped

        # Skip if language not in configured list (when list is non-empty)
        if self.config.languages and language not in self.config.languages:
            return skipped

        # Parse file (carrying parse-mode provenance). Note: we deliberately do NOT
        # call delete_file_and_nodes here — stable ids let upsert_nodes preserve
        # unchanged symbols (and inbound edges) and prune only removed ones.
        parsed = self.parser.parse_file_status(file_path, content)
        parsed_symbols, parsed_edges = parsed.symbols, parsed.edges

        # Insert file record. The content hash powers staleness detection (has the
        # file changed since it was indexed?); it was previously stored empty.
        self.db.upsert_file(
            FileRecord(
                id=None,
                path=file_path,
                language=language,
                last_modified=0,
                hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                size=len(content),
            )
        )

        # Build symbol nodes; stable ids are assigned by upsert_nodes.
        nodes: list[Node] = [
            Node(
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
            for sym in parsed_symbols
        ]
        node_ids = self.db.upsert_nodes(nodes, self.project_id)

        # Build per-file resolution maps for edge resolution.
        by_name: dict[str, list[int]] = {}  # bare name -> indices (handles overloads)
        for i, sym in enumerate(parsed_symbols):
            by_name.setdefault(sym.name, []).append(i)
        # Index of methods grouped by container, for receiver/self disambiguation.
        container_of: dict[int, str | None] = {
            i: sym.container for i, sym in enumerate(parsed_symbols)
        }

        # Resolve intra-file edges, INCLUDING method/attribute calls. A method call
        # (self._step(), obj.method()) carries attr=method-name; we bind it to a
        # same-file symbol by attr name (preferring same-container for self.*).
        edges: list[Edge] = []
        seen: set[tuple[str, str]] = set()
        for pe in parsed_edges:
            src_idx = self._resolve_local_source(pe.source_name, by_name)
            if src_idx is None:
                continue
            tgt_idx = self._resolve_local_target(pe, by_name, container_of, src_idx)
            if tgt_idx is None:
                continue
            source_id = node_ids[src_idx]
            target_id = node_ids[tgt_idx]
            if (source_id, target_id) in seen:
                continue
            seen.add((source_id, target_id))
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

        # Replace this file's outbound edges (keyed on call_site_file); inbound edges
        # from other files are untouched and continue to resolve to surviving ids.
        self.db.upsert_edges(edges, file_path)

        return {
            "nodes": len(nodes),
            "edges": len(edges),
            "parse_mode": parsed.mode,
            "degraded": parsed.degraded,
        }

    @staticmethod
    def _resolve_local_source(source_name: str, by_name: dict[str, list[int]]) -> int | None:
        """Resolve the calling symbol to a single local index."""
        idxs = by_name.get(source_name)
        if not idxs:
            return None
        # The source is the enclosing function/method name; if overloaded, the first
        # is fine (the call site line ties it deterministically enough for edges).
        return idxs[0]

    @staticmethod
    def _resolve_local_target(
        pe: Any,
        by_name: dict[str, list[int]],
        container_of: dict[int, str | None],
        src_idx: int,
    ) -> int | None:
        """Resolve a call target to a local symbol index, handling method/attribute calls.

        Bare-name calls bind to a same-name local symbol when unambiguous. Method/
        attribute calls (``self._step``/``obj.method``) bind by the attribute name,
        preferring a target in the SAME container for ``self``/``this`` receivers.
        Ambiguous bare-name targets are left for the cross-file pass (return None).
        """
        # Decompose attribute/receiver if present.
        attr = getattr(pe, "attr", None) or pe.target_name
        receiver = getattr(pe, "receiver", None)
        if "." in attr:
            attr = attr.rsplit(".", 1)[-1]

        candidates = by_name.get(attr, [])
        if not candidates:
            return None

        if receiver in ("self", "this"):
            same_container = [
                i for i in candidates if container_of.get(i) == container_of.get(src_idx)
            ]
            if same_container:
                return same_container[0]
        if len(candidates) == 1:
            return candidates[0]
        # Multiple local same-name targets and no disambiguator -> leave for cross-file
        # pass / mark unresolved rather than binding arbitrarily.
        return None

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
            total_edges += sum(1 for e in cross_edges if e.kind == "calls")

        return {
            "files_indexed": files_indexed,
            "nodes": total_nodes,
            "edges": total_edges,
        }

    def _resolve_cross_file_edges(self, file_contents: list[tuple[str, str]]) -> list[Edge]:
        """Second pass: resolve calls whose target lives in a different file.

        Resolution is deterministic and disambiguation-aware:
        * a target name with a single global definition binds to it;
        * an ambiguous name (multiple definitions) is disambiguated by the call
          site's imports (``from x import save`` / ``import b``) or the receiver's
          class — and if still ambiguous it is recorded as an UNRESOLVED edge
          (``kind='calls_unresolved'``, no target) rather than bound arbitrarily.
        Iteration order never decides a binding, so repeated indexing is stable.
        """

        conn = self.db._connect()

        # name -> sorted list of (file_path, node_id) for every definition of that name.
        by_name: dict[str, list[tuple[str, str]]] = {}
        node_files: dict[str, str] = {}
        node_container: dict[str, str | None] = {}
        # (file_path, name) -> node_id and (file_path, container.method) for method lookup.
        by_file_name: dict[tuple[str, str], str] = {}
        class_files: dict[str, list[str]] = {}  # class name -> files defining it
        for row in conn.execute(
            "SELECT id, name, file_path, kind, container FROM nodes ORDER BY file_path, name"
        ).fetchall():
            by_name.setdefault(row["name"], []).append((row["file_path"], row["id"]))
            node_files[row["id"]] = row["file_path"]
            node_container[row["id"]] = row["container"]
            by_file_name[(row["file_path"], row["name"])] = row["id"]
            if row["kind"] == "class":
                class_files.setdefault(row["name"], []).append(row["file_path"])

        def _resolve_source(name: str, hint_file: str) -> str | None:
            nid = by_file_name.get((hint_file, name))
            if nid is not None:
                return nid
            defs = by_name.get(name)
            return defs[0][1] if defs else None

        existing: set[tuple[str, str]] = set()
        unresolved_seen: set[tuple[str, int | None]] = set()
        for row in conn.execute(
            "SELECT source_node_id, target_node_id FROM edges WHERE kind = 'calls'"
        ).fetchall():
            existing.add((row["source_node_id"], row["target_node_id"]))

        cross_edges: list[Edge] = []
        for file_path, content in file_contents:
            language = self.parser.detect_language(file_path)
            if language is None:
                continue
            try:
                parsed = self.parser.parse_file_status(file_path, content)
            except Exception:
                continue
            parsed_edges = parsed.edges
            imports = self._parse_imports(content)

            for pe in parsed_edges:
                source_id = _resolve_source(pe.source_name, file_path)
                if source_id is None:
                    continue

                attr = getattr(pe, "attr", None) or pe.target_name
                if "." in attr:
                    attr = attr.rsplit(".", 1)[-1]
                receiver = getattr(pe, "receiver", None)

                target_id, ambiguous = self._resolve_cross_target(
                    attr, receiver, file_path, imports, by_name, by_file_name, class_files
                )

                if target_id is not None:
                    if node_files.get(target_id) == file_path:
                        continue  # intra-file edge already handled in pass 1
                    if (source_id, target_id) in existing:
                        continue
                    existing.add((source_id, target_id))
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
                elif ambiguous:
                    # Record the call as unresolved (never bound to an arbitrary node).
                    key = (source_id, pe.call_site_line)
                    if key in unresolved_seen:
                        continue
                    unresolved_seen.add(key)
                    cross_edges.append(
                        Edge(
                            id=None,
                            source_node_id=source_id,
                            target_node_id=None,  # type: ignore[arg-type]
                            kind="calls_unresolved",
                            call_site_file=file_path,
                            call_site_line=pe.call_site_line,
                        )
                    )

        return cross_edges

    @staticmethod
    def _parse_imports(content: str) -> dict[str, str]:
        """Map an imported symbol name to the module path it came from.

        Handles ``from x import a, b`` -> {a: x, b: x} and ``import b`` -> {b: b}.
        Used only as a disambiguation signal for same-name cross-file targets.
        """
        imports: dict[str, str] = {}
        for raw in content.splitlines():
            line = raw.strip()
            if line.startswith("from ") and " import " in line:
                mod, _, names = line[len("from ") :].partition(" import ")
                mod = mod.strip()
                for name in names.split(","):
                    name = name.split(" as ")[0].strip().strip("()")
                    if name and name != "*":
                        imports[name] = mod
            elif line.startswith("import "):
                for name in line[len("import ") :].split(","):
                    name = name.split(" as ")[0].strip()
                    if name:
                        imports[name.split(".")[-1]] = name
        return imports

    @staticmethod
    def _resolve_cross_target(
        attr: str,
        receiver: str | None,
        file_path: str,
        imports: dict[str, str],
        by_name: dict[str, list[tuple[str, str]]],
        by_file_name: dict[tuple[str, str], str],
        class_files: dict[str, list[str]],
    ) -> tuple[str | None, bool]:
        """Return (resolved_node_id, ambiguous_flag) for a cross-file call target.

        ambiguous=True means multiple same-name definitions exist and none could be
        chosen deterministically (the caller records an unresolved edge).
        """
        defs = by_name.get(attr, [])
        if not defs:
            return None, False
        if len(defs) == 1:
            return defs[0][1], False

        # Disambiguate by import module path: `from x import save` -> file x*.
        def _module_to_file(mod: str) -> str | None:
            tail = mod.replace(".", "/").split("/")[-1]
            for fp, nid in defs:
                stem = fp.rsplit("/", 1)[-1].removesuffix(".py")
                if stem == tail or fp.removesuffix(".py").endswith(mod.replace(".", "/")):
                    return nid
            return None

        # Receiver-based disambiguation (A().process() with A imported from a.py).
        if receiver:
            recv_type = receiver.split("(")[0].strip()
            if recv_type in imports:
                hit = _module_to_file(imports[recv_type])
                if hit is not None:
                    return hit, False
            # receiver is a class name defined in exactly one file
            if recv_type in class_files and len(class_files[recv_type]) == 1:
                cf = class_files[recv_type][0]
                nid = by_file_name.get((cf, attr))
                if nid is not None:
                    return nid, False

        # Direct import of the called name: `from x import save; save()`.
        if attr in imports:
            hit = _module_to_file(imports[attr])
            if hit is not None:
                return hit, False

        # Multiple candidates, no disambiguator -> ambiguous (do not guess).
        return None, True

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

    def resolve_symbol_path(self, path: str) -> str | None:
        """Resolve a dotted reference (e.g. ``AuthService.login``) to a node id.

        Partial-path resolution: the last segment is the symbol, the preceding
        segments are scope hints used to disambiguate same-name definitions.
        Returns ``None`` when there is no match or the path stays ambiguous.
        """
        from opencontext_core.indexing.name_resolution import SymbolRef, resolve_partial_path

        segments = [s for s in path.split(".") if s]
        if not segments:
            return None
        conn = self.db._connect()
        rows = conn.execute(
            "SELECT id, name, container, file_path FROM nodes WHERE name = ?",
            (segments[-1],),
        ).fetchall()
        refs = [
            SymbolRef(
                id=r["id"], name=r["name"], container=r["container"], file_path=r["file_path"]
            )
            for r in rows
        ]
        return resolve_partial_path(path, refs)

    def get_stats(self) -> dict[str, int]:
        """Get database statistics."""

        return self.db.get_stats()

    def stale_files(self, root: Path) -> StaleReport:
        """Indexed files whose content changed on disk, or were deleted.

        Compares each indexed file's stored content hash against the file on disk.
        A stale index silently degrades retrieval (the agent gets context for code
        that no longer exists), so this powers a freshness warning. Files indexed
        before hashes were stored (empty hash) are skipped — a reindex enables
        tracking. New, never-indexed files are out of scope here.
        """
        changed: list[str] = []
        deleted: list[str] = []
        for record in self.db.all_files():
            path = root / record.path
            if not path.exists():
                deleted.append(record.path)
                continue
            if not record.hash:
                continue  # pre-hash index; reindex to enable tracking
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if hashlib.sha256(content.encode("utf-8")).hexdigest() != record.hash:
                changed.append(record.path)
        return StaleReport(changed=changed, deleted=deleted)

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
