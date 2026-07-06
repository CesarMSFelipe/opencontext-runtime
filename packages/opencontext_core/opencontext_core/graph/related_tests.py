"""Related-tests query over the knowledge graph (KG_CONTEXT_COMPRESSION_CONTRACT).

Finds the tests connected to a file or symbol. Dedicated ``tests``/``covers``
edges are honored when present; a ``calls`` edge whose caller lives in a test
file is treated as the same test->symbol relationship, because that is what the
indexer emits today for a test invoking the symbol under test.
"""

from __future__ import annotations

from typing import Any

from opencontext_core.indexing.graph_db import GraphDatabase, is_test_path

_TEST_EDGE_KINDS = ("tests", "covers", "calls")


def _looks_like_path(target: str) -> bool:
    return "/" in target or "\\" in target or "." in target.rsplit("/", 1)[-1]


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
    seen: set[tuple[str, str]] = set()
    if target_ids:
        placeholders = ",".join("?" for _ in target_ids)
        kind_placeholders = ",".join("?" for _ in _TEST_EDGE_KINDS)
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
            (*_TEST_EDGE_KINDS, *target_ids, *target_ids),
        ).fetchall()
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

    related.sort(key=lambda entry: (entry["file_path"], entry["line"] or 0, entry["test"]))
    return {
        "target": target,
        "resolved": {"kind": resolved_kind, "matches": len(target_ids)},
        "related_tests": related,
    }
