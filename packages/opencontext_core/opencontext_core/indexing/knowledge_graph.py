"""Knowledge graph facade for indexing and querying code symbols."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from opencontext_core.compat import StrEnum
from opencontext_core.config import KnowledgeGraphConfig
from opencontext_core.indexing.graph_db import (
    Edge,
    FileRecord,
    GraphDatabase,
    Node,
    is_test_path,
)
from opencontext_core.indexing.graph_delta import CacheInvalidationRegistry, GraphDelta
from opencontext_core.indexing.tree_sitter_parser import (
    LANGUAGE_EXTENSIONS,
    TreeSitterParser,
)


def _stable_symbol_id(project_id: str, file_path: str, qualified_name: str, kind: str) -> str:
    """Return a 16-char deterministic hex ID for a symbol, unique across files."""
    payload = f"{project_id}:{file_path}:{qualified_name}:{kind}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _kg_fts_rowid(node_id: str) -> int:
    """Deterministic int64 fts_rowid for a content-addressed ``kg_<hex>`` node id.

    The nodes table requires a unique integer ``fts_rowid``; KG v2 ids carry a
    ``kg_`` prefix (not valid hex), so we hash the id to a stable 60-bit int rather
    than parse the prefixed string as hex. Used for owner/framework-fact nodes whose
    ids are ``kg_<hash>`` instead of the legacy 16-hex symbol id.
    """
    return int(hashlib.sha256(node_id.encode()).hexdigest()[:15], 16)


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
        # KG v2 (KG-CONV): dependent caches register invalidation hooks here; the
        # KG fires them on every delta-producing mutation (reindex/apply/supersede).
        self.cache_invalidation = CacheInvalidationRegistry()
        # KG v2 (KG-14): an optional observer collects kg.* events / receipts. None
        # (default) means no events are emitted — the legacy path is unchanged.
        self.observer: Any | None = None
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

        # Insert file record. The content hash is the staleness signal (has the file
        # changed since it was indexed?). last_modified is intentionally 0: index_file
        # receives content, not an absolute path, so there's no mtime to record — the
        # hash, not the mtime, drives reindexing.
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
                content_snippet=sym.content_snippet,
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

        self.db.rebuild_fts()

        # Pass 2: resolve cross-file edges using the complete global node map.
        # First prune dangling cross-file edges from any previously deleted nodes
        # so that INSERT OR IGNORE does not silently keep stale rows.
        cross_edges = self._resolve_cross_file_edges(file_contents)
        conn = self.db._connect()
        reindexed_files = {fp for fp, _ in file_contents}
        if reindexed_files:
            placeholders = ",".join("?" * len(reindexed_files))
            conn.execute(
                f"DELETE FROM edges WHERE call_site_file IN ({placeholders})"
                " AND target_node_id NOT IN (SELECT id FROM nodes)",
                list(reindexed_files),
            )
        if cross_edges:
            _SQL = "INSERT OR IGNORE INTO edges (source_node_id, target_node_id, kind, call_site_file, call_site_line) VALUES (?, ?, ?, ?, ?)"  # noqa: E501
            conn.executemany(
                _SQL,
                [
                    (e.source_node_id, e.target_node_id, e.kind, e.call_site_file, e.call_site_line)
                    for e in cross_edges
                ],
            )
            total_edges += sum(1 for e in cross_edges if e.kind == "calls")
        conn.commit()

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
        existing_tests: set[tuple[str, str]] = set()
        unresolved_seen: set[tuple[str, int | None]] = set()
        for row in conn.execute(
            "SELECT source_node_id, target_node_id, kind FROM edges "
            "WHERE kind IN ('calls', 'tests')"
        ).fetchall():
            pair = (row["source_node_id"], row["target_node_id"])
            if row["kind"] == "tests":
                existing_tests.add(pair)
            else:
                existing.add(pair)

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
                    # A test symbol calling a non-test symbol also gets a dedicated
                    # `tests` edge (KG_CONTEXT_COMPRESSION_CONTRACT) so related-tests
                    # queries no longer rely on the calls-from-test-file heuristic.
                    # Checked BEFORE the calls dedup so a pre-existing calls edge
                    # (indexed before tests emission landed) still gains its edge.
                    if (
                        pe.kind == "calls"
                        and is_test_path(node_files.get(source_id, ""))
                        and not is_test_path(node_files.get(target_id, ""))
                        and (source_id, target_id) not in existing_tests
                    ):
                        existing_tests.add((source_id, target_id))
                        cross_edges.append(
                            Edge(
                                id=None,
                                source_node_id=source_id,
                                target_node_id=target_id,
                                kind="tests",
                                call_site_file=file_path,
                                call_site_line=pe.call_site_line,
                            )
                        )
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

        Handles ``from x import a, b`` -> {a: x, b: x}, multi-line
        ``from x import (\n  a,\n  b\n)``, and ``import b`` -> {b: b}.
        Used only as a disambiguation signal for same-name cross-file targets.
        """
        imports: dict[str, str] = {}
        lines = content.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith("from ") and " import " in line:
                mod, _, names_part = line[len("from ") :].partition(" import ")
                mod = mod.strip()
                # Accumulate multi-line import: from x import (\n  a,\n  b\n)
                accumulated = names_part
                if "(" in names_part and ")" not in names_part:
                    i += 1
                    while i < len(lines):
                        continuation = lines[i].strip()
                        accumulated += " " + continuation
                        i += 1
                        if ")" in continuation:
                            break
                for name in accumulated.split(","):
                    name = name.split(" as ")[0].strip().strip("()")
                    if name and name != "*":
                        imports[name] = mod
            elif line.startswith("import "):
                for name in line[len("import ") :].split(","):
                    name = name.split(" as ")[0].strip()
                    if name:
                        imports[name.split(".")[-1]] = name
            i += 1
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

    def reindex_files(self, file_paths: set[str], root: Path) -> dict[str, Any]:
        """Incrementally re-index a specific set of files.

        Reads each file from disk, re-parses it (upsert semantics — unchanged
        symbols are preserved, removed ones pruned), then rebuilds cross-file
        edges for the affected set only.

        Returns stats dict with nodes/edges counts.
        """
        stats = {"files": 0, "nodes": 0, "edges": 0, "skipped": 0}
        file_contents: list[tuple[str, str]] = []
        for rel_path in file_paths:
            abs_path = root / rel_path
            try:
                content = abs_path.read_text(encoding="utf-8", errors="replace")
            except FileNotFoundError:
                # File was deleted — remove its nodes from the graph
                self.db.delete_file_and_nodes(rel_path)
                stats["skipped"] += 1
                continue
            except Exception:
                stats["skipped"] += 1
                continue
            result = self.index_file(rel_path, content)
            if result.get("parse_mode") != "skipped":
                stats["files"] += 1
                stats["nodes"] += result.get("nodes", 0)
                file_contents.append((rel_path, content))
        if file_contents:
            self.db.rebuild_fts()
            stats["edges"] += self.finalize_cross_file_edges(file_contents)
        return stats

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

    # --- KG v2: typed incremental delta (KG-08) --------------------------------

    def _node_ids_for_files(self, file_paths: set[str]) -> dict[str, set[str]]:
        """Map each file path to the set of node ids the store currently holds for it."""
        result: dict[str, set[str]] = {}
        conn = self.db._connect()
        for path in file_paths:
            rows = conn.execute("SELECT id FROM nodes WHERE file_path = ?", (path,)).fetchall()
            result[path] = {row["id"] for row in rows}
        return result

    def _edge_sigs_for_files(self, file_paths: set[str]) -> set[str]:
        """Signatures (``src->kind->tgt``) of edges whose call site is in ``file_paths``."""
        if not file_paths:
            return set()
        conn = self.db._connect()
        placeholders = ",".join("?" * len(file_paths))
        rows = conn.execute(
            "SELECT source_node_id, target_node_id, kind FROM edges "
            f"WHERE call_site_file IN ({placeholders})",
            list(file_paths),
        ).fetchall()
        return {f"{r['source_node_id']}->{r['kind']}->{r['target_node_id']}" for r in rows}

    def reindex_delta(self, file_paths: set[str], root: Path) -> GraphDelta:
        """Incrementally reindex ``file_paths`` and return a typed :class:`GraphDelta`.

        Additive over :meth:`reindex_files` (whose dict return is unchanged): this
        diffs the per-file node/edge sets before and after the reindex so the caller
        gets the exact ids added/updated/deleted (OC-KG-001 §13). Fires registered
        cache-invalidation hooks (KG-CONV) before returning.
        """
        before_nodes = self._node_ids_for_files(file_paths)
        before_edges = self._edge_sigs_for_files(file_paths)

        self.reindex_files(file_paths, root)

        after_nodes = self._node_ids_for_files(file_paths)
        after_edges = self._edge_sigs_for_files(file_paths)

        added_nodes: list[str] = []
        deleted_nodes: list[str] = []
        updated_nodes: list[str] = []
        for path in file_paths:
            before = before_nodes.get(path, set())
            after = after_nodes.get(path, set())
            added_nodes.extend(sorted(after - before))
            deleted_nodes.extend(sorted(before - after))
            updated_nodes.extend(sorted(before & after))

        added_edges = sorted(after_edges - before_edges)
        deleted_edges = sorted(before_edges - after_edges)
        affected_symbols = sorted({*added_nodes, *deleted_nodes, *updated_nodes})

        delta = GraphDelta(
            added_nodes=added_nodes,
            updated_nodes=updated_nodes,
            deleted_nodes=deleted_nodes,
            added_edges=added_edges,
            deleted_edges=deleted_edges,
            affected_symbols=affected_symbols,
            affected_files=sorted(file_paths),
        )
        self.cache_invalidation.fire(delta)
        if self.observer is not None:
            from opencontext_core.models.trace import KG_DELTA_CREATED

            self.observer.emit(
                KG_DELTA_CREATED,
                added=len(added_nodes),
                deleted=len(deleted_nodes),
                files=len(file_paths),
            )
        return delta

    def index_with_receipt(self, root: str | Path, *, storage_dir: str | Path | None = None) -> Any:
        """Index ``root`` while emitting kg.index.* events and writing a receipt (KG-14).

        Additive over :meth:`index_project` (whose return is unchanged): this brackets
        the index run with ``kg.index.started`` / ``kg.index.completed`` (or
        ``kg.index.failed``) and persists an index :class:`KgReceipt`. Returns the
        receipt; ``receipt.details['stats']`` carries the index stats.
        """
        from opencontext_core.indexing.kg_receipts import KgObserver
        from opencontext_core.models.kg_v2 import now_iso
        from opencontext_core.models.trace import (
            KG_INDEX_COMPLETED,
            KG_INDEX_FAILED,
            KG_INDEX_STARTED,
        )

        observer = self.observer if self.observer is not None else KgObserver(storage_dir)
        if self.observer is None:
            self.observer = observer
        started = now_iso()
        observer.emit(KG_INDEX_STARTED, root=str(root))
        try:
            stats = self.index_project(root)
        except Exception as exc:
            observer.emit(KG_INDEX_FAILED, error=str(exc))
            observer.write_receipt("index", status="failed", started_at=started, error=str(exc))
            raise
        observer.emit(KG_INDEX_COMPLETED, **stats)
        return observer.write_receipt("index", started_at=started, stats=stats)

    def apply_delta(self, delta: GraphDelta) -> None:
        """Replay a :class:`GraphDelta`'s deletions against the store (KG-08, §23).

        Removes the delta's ``deleted_nodes`` (and their edges) so a delta computed
        elsewhere — e.g. by a plugin provider — converges the native index, then
        fires cache-invalidation hooks. Added/updated ids are already materialised by
        the index pass that produced the delta, so applying them is a no-op here.
        """
        conn = self.db._connect()
        for node_id in delta.deleted_nodes:
            conn.execute(
                "DELETE FROM edges WHERE source_node_id = ? OR target_node_id = ?",
                (node_id, node_id),
            )
            conn.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
        conn.commit()
        self.cache_invalidation.fire(delta)

    def supersede_node(self, old_id: str, new_id: str) -> bool:
        """Mark ``old_id`` superseded by ``new_id`` and fire cache invalidation (KG-06)."""
        ok = self.db.supersede_node(old_id, new_id)
        if ok:
            self.cache_invalidation.fire(
                GraphDelta(updated_nodes=[old_id], affected_symbols=[old_id])
            )
            if self.observer is not None:
                from opencontext_core.models.trace import KG_NODE_SUPERSEDED

                self.observer.emit(KG_NODE_SUPERSEDED, old_id=old_id, new_id=new_id)
        return ok

    # --- KG v2: framework / config / doc extraction (KG-13) --------------------

    def index_framework_facts(self, root: str | Path, *, include_docs: bool = False) -> int:
        """Extract + persist detected-framework and config/doc facts (KG-13).

        Detects the project framework and writes its routes/services/config/tests as
        typed graph nodes/edges with evidence; when ``include_docs`` is set, also
        emits ``config`` nodes for YAML/JSON/Markdown files. Opt-in and additive — the
        default tree-sitter index path is unchanged. Returns the number of nodes
        persisted. Framework-fact node ids are ``kg_<hash>`` (content-addressed).
        """
        from opencontext_core.indexing.framework_profiles import (
            extract_doc_config_facts,
            extract_framework_facts,
        )

        root_path = Path(root)
        extraction = extract_framework_facts(root_path)
        if include_docs:
            extraction.merge(extract_doc_config_facts(root_path))
        if not extraction.nodes and not extraction.edges:
            return 0

        conn = self.db._connect()
        for node in extraction.nodes:
            evidence_json = (
                json.dumps([e.model_dump() for e in node.evidence]) if node.evidence else None
            )
            conn.execute(
                "INSERT OR IGNORE INTO nodes "
                "(id, fts_rowid, name, kind, file_path, line, column, end_line, "
                " language, container, docstring, signature, is_exported, "
                " observed_at, status, evidence_json) "
                "VALUES (?, ?, ?, ?, ?, 0, 0, 0, ?, NULL, NULL, NULL, 0, ?, 'active', ?)",
                (
                    node.id,
                    _kg_fts_rowid(node.id),
                    node.name,
                    node.type.value,
                    node.path or "",
                    node.language or "",
                    node.temporal.observed_at,
                    evidence_json,
                ),
            )
        for edge in extraction.edges:
            existing = conn.execute(
                "SELECT 1 FROM edges WHERE source_node_id = ? AND target_node_id = ? AND kind = ?",
                (edge.source_id, edge.target_id, edge.type.value),
            ).fetchone()
            if existing is None:
                conn.execute(
                    "INSERT INTO edges "
                    "(source_node_id, target_node_id, kind, call_site_file, call_site_line) "
                    "VALUES (?, ?, ?, ?, 0)",
                    (edge.source_id, edge.target_id, edge.type.value, ""),
                )
        conn.commit()
        self.db.rebuild_fts()
        return len(extraction.nodes)

    # --- KG v2: owner extraction + resolution (KG-13 stage, KG-CONV) -----------

    def extract_owners(self, root: Path, file_paths: set[str] | None = None) -> int:
        """Create ``OWNER`` nodes and ``OWNS`` edges from git/CODEOWNERS provenance.

        For each indexed file (optionally scoped to ``file_paths``) the top git
        author becomes an ``owner`` node; an ``owns`` edge links the file's owner to
        the file path. Owner facts are inferred, so each carries a `TemporalMetadata`
        and an `EvidenceRef`. Returns the number of ``OWNS`` edges written. Degrades
        to 0 when git is unavailable.
        """
        from opencontext_core.indexing.git_context import GitContextProvider
        from opencontext_core.models.kg_v2 import kg_node_id

        provider = GitContextProvider(root)
        if not provider.available:
            return 0

        scope = file_paths or {rec.path for rec in self.db.all_files()}
        conn = self.db._connect()
        written = 0
        for rel_path in sorted(scope):
            info = provider.get_file_info(root / rel_path)
            owner = None
            if info is not None:
                owner = (info.top_authors[0] if info.top_authors else None) or info.last_author
            if not owner:
                continue
            owner_id = kg_node_id("owner", owner)
            # Upsert the owner node (idempotent on its content-addressed id).
            conn.execute(
                "INSERT OR IGNORE INTO nodes "
                "(id, fts_rowid, name, kind, file_path, line, column, end_line, "
                " language, container, docstring, signature, is_exported) "
                "VALUES (?, ?, ?, 'owner', ?, 0, 0, 0, '', NULL, NULL, NULL, 0)",
                (owner_id, _kg_fts_rowid(owner_id), owner, rel_path),
            )
            # Link owner -> file via an OWNS edge (inferred fact, recorded once).
            existing = conn.execute(
                "SELECT 1 FROM edges WHERE source_node_id = ? AND kind = 'owns' "
                "AND call_site_file = ?",
                (owner_id, rel_path),
            ).fetchone()
            if existing is None:
                conn.execute(
                    "INSERT INTO edges "
                    "(source_node_id, target_node_id, kind, call_site_file, call_site_line) "
                    "VALUES (?, NULL, 'owns', ?, 0)",
                    (owner_id, rel_path),
                )
                written += 1
        conn.commit()
        return written

    def resolve_owner(self, file_path: str) -> str | None:
        """Resolve the owner of ``file_path`` by traversing ``OWNS`` edges (KG-CONV).

        Reads the graph, NOT git — owner extraction populated the edges, so this is
        a pure graph lookup. Returns the owner name, or None when no owner is linked.
        """
        conn = self.db._connect()
        row = conn.execute(
            "SELECT n.name FROM edges e JOIN nodes n ON n.id = e.source_node_id "
            "WHERE e.kind = 'owns' AND e.call_site_file = ? LIMIT 1",
            (file_path,),
        ).fetchone()
        return str(row["name"]) if row is not None else None

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


# --- Slice 4: engineering-domain KG schema extension ----------------------------
# Additive only: existing string values and on-disk index format are untouched.
# New values let SDD tooling (requirement/task/test/phase tracking) reuse the
# same GraphDatabase as code symbols without renaming the schema.

# NOTE: local extension module-side enum — the canonical NodeKind/EdgeKind
# for the unified graph still live in opencontext_core.graph.{nodes,edges}.
# Mirror only the engineering-domain additions here so indexing callers can
# refer to them by symbolic name without an import to a separate package.


class NodeKind(StrEnum):
    """Engineering-domain node kinds accepted by the index.

    Additive extension: pre-existing string kinds (e.g. ``function``, ``class``,
    ``test``) are NOT redefined here — they keep their raw string form in the
    SQLite store, and callers may compare ``node.kind`` against the values
    listed below.
    """

    REQUIREMENT = "requirement"
    TASK = "task"
    TEST = "test"
    PHASE = "phase"


class EdgeKind(StrEnum):
    """Engineering-domain edge kinds accepted by the index.

    Additive extension: pre-existing string edge kinds (``calls``, ``imports``,
    ...) are NOT redefined here — they keep their raw string form, and callers
    may compare ``edge.kind`` against the values listed below.
    """

    IMPLEMENTS = "implements"
    VERIFIED_BY = "verified_by"
    DEPENDS_ON = "depends_on"
