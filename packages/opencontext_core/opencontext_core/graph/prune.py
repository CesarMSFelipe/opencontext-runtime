"""Prune stale knowledge-graph entries whose source files vanished from disk.

Complements ``GraphDatabase.prune_files_absent_from`` (which reconciles against a
freshly-scanned keep-set during indexing): this variant checks the indexed file
records against the filesystem directly, supports dry-run reporting, and also
drops edges dangling on missing nodes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from opencontext_core.indexing.graph_db import GraphDatabase

# Surviving nodes = nodes whose file is NOT in the missing set; every edge must
# land on them. Edges are stale when their call site file vanished, or when
# either endpoint no longer resolves to a surviving node (dangling included).
_STALE_EDGE_PREDICATE = (
    "call_site_file IN (SELECT path FROM _kg_prune_missing)"
    " OR source_node_id NOT IN"
    " (SELECT id FROM nodes WHERE file_path NOT IN (SELECT path FROM _kg_prune_missing))"
    " OR (target_node_id IS NOT NULL AND target_node_id NOT IN"
    " (SELECT id FROM nodes WHERE file_path NOT IN (SELECT path FROM _kg_prune_missing)))"
)
_STALE_NODE_PREDICATE = "file_path IN (SELECT path FROM _kg_prune_missing)"


def prune_knowledge_graph(
    db: GraphDatabase, root: Path, *, dry_run: bool = False
) -> dict[str, Any]:
    """Remove nodes/edges whose source files no longer exist under ``root``.

    Also removes edges dangling on missing nodes. With ``dry_run`` the graph is
    left intact and only the would-be removal counts are reported.
    """

    conn = db._connect()
    missing = sorted(record.path for record in db.all_files() if not (root / record.path).exists())
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS _kg_prune_missing (path TEXT PRIMARY KEY)")
    conn.execute("DELETE FROM _kg_prune_missing")
    conn.executemany(
        "INSERT OR IGNORE INTO _kg_prune_missing (path) VALUES (?)", ((p,) for p in missing)
    )

    nodes_removed = conn.execute(
        f"SELECT COUNT(*) FROM nodes WHERE {_STALE_NODE_PREDICATE}"
    ).fetchone()[0]
    edges_removed = conn.execute(
        f"SELECT COUNT(*) FROM edges WHERE {_STALE_EDGE_PREDICATE}"
    ).fetchone()[0]

    if not dry_run and (missing or edges_removed):
        conn.execute(f"DELETE FROM edges WHERE {_STALE_EDGE_PREDICATE}")
        conn.execute(f"DELETE FROM nodes WHERE {_STALE_NODE_PREDICATE}")
        conn.execute("DELETE FROM files WHERE path IN (SELECT path FROM _kg_prune_missing)")

    conn.execute("DELETE FROM _kg_prune_missing")
    conn.commit()
    return {
        "nodes_removed": nodes_removed,
        "edges_removed": edges_removed,
        "files_removed": len(missing),
        "dry_run": dry_run,
    }
