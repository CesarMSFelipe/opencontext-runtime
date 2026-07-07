"""Related-tests query over the knowledge graph (KG_CONTEXT_COMPRESSION_CONTRACT).

Finds the tests connected to a file or symbol. Dedicated ``tests``/``covers``
edges (emitted at index time) are preferred; when none exist for the target the
query falls back to the ``calls``-from-a-test-file heuristic, which is what
pre-emission indexes carry for a test invoking the symbol under test. The
``via`` field reports which edge kind linked each test.
"""

from __future__ import annotations

from typing import Any

from opencontext_core.indexing.graph_db import GraphDatabase, is_test_path

_REAL_EDGE_KINDS = ("tests", "covers")
_FALLBACK_EDGE_KINDS = ("calls",)


def _looks_like_path(target: str) -> bool:
    return "/" in target or "\\" in target or "." in target.rsplit("/", 1)[-1]


def _test_links(
    conn: Any, target_ids: dict[str, str], edge_kinds: tuple[str, ...]
) -> list[dict[str, Any]]:
    """Collect test->target links through ``edge_kinds`` edges."""

    placeholders = ",".join("?" for _ in target_ids)
    kind_placeholders = ",".join("?" for _ in edge_kinds)
    # A test can sit on either end of the edge (test -tests-> symbol is the
    # canonical direction; the reverse is tolerated for derived edges).
    edge_rows = conn.execute(
        f"""
        SELECT e.kind AS kind,
               src.id AS src_id, src.name AS src_name, src.file_path AS src_file,
               src.line AS src_line,
               tgt.id AS tgt_id, tgt.name AS tgt_name, tgt.file_path AS tgt_file,
               tgt.line AS tgt_line
        FROM edges e
        JOIN nodes src ON e.source_node_id = src.id
        JOIN nodes tgt ON e.target_node_id = tgt.id
        WHERE e.kind IN ({kind_placeholders})
          AND (e.source_node_id IN ({placeholders})
               OR e.target_node_id IN ({placeholders}))
        """,
        (*edge_kinds, *target_ids, *target_ids),
    ).fetchall()
    related: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in edge_rows:
        if str(row["tgt_id"]) in target_ids and is_test_path(row["src_file"]):
            test_name, test_file, test_line = row["src_name"], row["src_file"], row["src_line"]
            connected_to = row["tgt_name"]
        elif str(row["src_id"]) in target_ids and is_test_path(row["tgt_file"]):
            test_name, test_file, test_line = row["tgt_name"], row["tgt_file"], row["tgt_line"]
            connected_to = row["src_name"]
        else:
            continue
        key = (test_name, test_file)
        if key in seen:
            continue
        seen.add(key)
        related.append(
            {
                "test": test_name,
                "file_path": test_file,
                "line": test_line,
                "via": row["kind"],
                "connected_to": connected_to,
            }
        )
    return related


def find_related_tests(db: GraphDatabase, target: str) -> dict[str, Any]:
    """Return the tests connected to ``target`` (a file path or symbol name)."""

    conn = db._connect()
    if _looks_like_path(target):
        resolved_kind = "file"
        rows = conn.execute("SELECT id, name FROM nodes WHERE file_path = ?", (target,)).fetchall()
    else:
        resolved_kind = "symbol"
        rows = conn.execute("SELECT id, name FROM nodes WHERE name = ?", (target,)).fetchall()

    target_ids = {str(row["id"]): row["name"] for row in rows}
    related: list[dict[str, Any]] = []
    if target_ids:
        related = _test_links(conn, target_ids, _REAL_EDGE_KINDS)
        if not related:
            related = _test_links(conn, target_ids, _FALLBACK_EDGE_KINDS)

    related.sort(key=lambda entry: (entry["file_path"], entry["line"] or 0, entry["test"]))
    return {
        "target": target,
        "resolved": {"kind": resolved_kind, "matches": len(target_ids)},
        "related_tests": related,
    }
