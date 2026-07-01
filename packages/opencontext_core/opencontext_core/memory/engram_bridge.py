"""Bridge to a co-resident Engram install.

OpenContext memory is multi-level. Engram is a separate persistent-memory tool
a user may already run. The two are designed to coexist:

- Engram present  -> Engram owns the EPISODIC/SEMANTIC levels; OpenContext keeps
  PROCEDURAL/FAILURE/WORKING locally. ``CompositeMemoryStore`` routes by layer,
  so the user's existing Engram workflow keeps working and OpenContext recalls
  from (and writes the durable layers back into) the same store.
- Engram absent   -> OpenContext ``LocalMemoryStore`` covers every level.

This module is the transport for the standalone runtime, which cannot reach the
Engram MCP tools (those exist only inside the agent). It talks to the same
on-disk store the MCP server uses:

- read  (``mem_search``): query Engram's SQLite directly with ``LIKE`` — no FTS5
  module dependency, read-only, never mutates the user's store.
- write (``mem_save``):   shell out to the ``engram`` CLI so Engram's own dedup,
  triggers, and sync invariants are preserved.

Everything degrades to empty/no-op on error — memory must never raise.
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

_TRUTHY = {"1", "true", "yes", "on"}

# Engram observation type -> OpenContext cognitive layer. Engram owns EPISODIC
# (what happened) and SEMANTIC (durable knowledge); session summaries are the
# episodic record, everything else Engram stores is treated as semantic.
_ENGRAM_TO_LAYER = {"session_summary": "episodic", "episodic": "episodic"}
# OpenContext layer -> Engram type for writes (only the two Engram-owned layers
# are ever routed here by CompositeMemoryStore).
_LAYER_TO_ENGRAM = {"episodic": "session_summary", "semantic": "discovery"}


def _engram_db_path() -> Path:
    """Resolve Engram's SQLite path (env-overridable, defaults to ~/.engram)."""
    override = os.environ.get("OPENCONTEXT_ENGRAM_DB")
    if override:
        return Path(override).expanduser()
    home = os.environ.get("ENGRAM_HOME")
    if home:
        return Path(home).expanduser() / "engram.db"
    return Path.home() / ".engram" / "engram.db"


def engram_project() -> str:
    """Project key matching Engram's convention (slugified working-dir name).

    .. deprecated:: 2.0
        Use :func:`engram_project_full` for the 5-case detector with
        ambiguity surfacing and recovery-token flow.
    """
    import warnings

    warnings.warn(
        "engram_project() is deprecated since 2.0; use engram_project_full() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    override = os.environ.get("OPENCONTEXT_ENGRAM_PROJECT")
    if override:
        return override
    return Path.cwd().name.strip().lower().replace(" ", "-")


def engram_project_full(cwd: Path | None = None) -> Any:
    """Full 5-case project detection via :mod:`opencontext_memory.project`.

    PR2.d additive extension: returns a
    :class:`opencontext_memory.project.DetectionResult` so callers can
    inspect ``source``, ``warning`` and (for ambiguous projects)
    ``available_projects`` + ``recovery_token``.

    The legacy ``engram_project()`` string-shaped function stays put for
    back-compat with the existing ``backends/factory.py`` wiring; the
    new full detector is the canonical path for any host that wants
    ambiguity-surfacing + ``git_child`` auto-promotion.
    """
    from opencontext_memory.project import DetectProjectFull

    resolved = Path(cwd).resolve() if cwd is not None else Path.cwd()
    return DetectProjectFull(resolved)


def detect_engram() -> bool:
    """Return True when a co-resident Engram install is usable.

    ``OPENCONTEXT_ENGRAM`` forces the answer (``1``/``0``) for both production
    opt-out and test control. Auto-detection is suppressed under pytest so the
    suite stays on local memory regardless of the host and never writes into a
    real Engram store. Otherwise: the ``engram`` CLI on PATH (write capable) or
    an existing store on disk (read capable) counts as present.
    """
    forced = os.environ.get("OPENCONTEXT_ENGRAM")
    if forced is not None:
        return forced.strip().lower() in _TRUTHY
    if "PYTEST_CURRENT_TEST" in os.environ:
        return False
    if shutil.which("engram"):
        return True
    return _engram_db_path().exists()


def _layer_for(engram_type: str) -> str:
    return _ENGRAM_TO_LAYER.get((engram_type or "").lower(), "semantic")


class EngramCliClient:
    """``EngramClient`` over Engram's SQLite (read) and ``engram`` CLI (write)."""

    def __init__(
        self,
        *,
        db_path: Path | None = None,
        project: str | None = None,
        binary: str = "engram",
        timeout: float = 10.0,
    ) -> None:
        self._db = db_path or _engram_db_path()
        self._project = project or engram_project()
        self._binary = binary
        self._timeout = timeout

    def mem_search(
        self,
        *,
        query: str = "",
        limit: int = 10,
        type: str | None = None,  # OpenContext layer value, e.g. "episodic"
        project: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        want_layer = (type or "").lower() or None
        try:
            rows = self._read(
                query, limit=limit, project=project or self._project, want_layer=want_layer
            )
        except Exception as exc:
            _log.warning("engram read failed (query=%r): %s", str(query)[:80], exc)
            return {"results": []}
        results: list[dict[str, Any]] = []
        for row in rows:
            layer = _layer_for(row.get("type", ""))
            if want_layer is not None and layer != want_layer:
                continue
            results.append(
                {
                    "id": str(row.get("id", "")),
                    "type": layer,  # normalized to the OpenContext taxonomy
                    "title": row.get("title", ""),
                    "content": row.get("content", "") or row.get("title", ""),
                    "topic_key": row.get("topic_key") or row.get("title", ""),
                    "project": row.get("project", ""),
                    "confidence": 1.0,
                }
            )
            if len(results) >= limit:
                break
        return {"results": results}

    def _read(
        self, query: str, *, limit: int, project: str, want_layer: str | None = None
    ) -> list[dict[str, Any]]:
        if not query.strip() or not self._db.exists():
            return []
        con = sqlite3.connect(f"file:{self._db}?mode=ro", uri=True, timeout=self._timeout)
        try:
            like = f"%{query.strip()}%"
            sql = (
                "SELECT id, type, title, content, topic_key, project "
                "FROM observations "
                "WHERE deleted_at IS NULL AND project = ? "
                "AND (title LIKE ? OR content LIKE ?) "
            )
            params: list[Any] = [project, like, like]
            # Push the layer filter into SQL so a recent burst of one layer can't
            # starve the requested layer out of the over-fetch window.
            episodic_types = tuple(
                t for t, layer in _ENGRAM_TO_LAYER.items() if layer == "episodic"
            )
            if want_layer in ("episodic", "semantic") and episodic_types:
                placeholders = ",".join("?" * len(episodic_types))
                op = "IN" if want_layer == "episodic" else "NOT IN"
                sql += f"AND type {op} ({placeholders}) "
                params.extend(episodic_types)
            sql += "ORDER BY updated_at DESC LIMIT ?"
            params.append(max(limit * 4, limit))
            cur = con.execute(sql, params)
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]
        finally:
            con.close()

    def mem_save(
        self,
        *,
        title: str,
        content: str,
        type: str | None = None,
        project: str | None = None,
        scope: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        engram_type = _LAYER_TO_ENGRAM.get((type or "").lower(), "discovery")
        cmd = [
            self._binary,
            "save",
            str(title),
            str(content),
            "--type",
            engram_type,
            "--project",
            project or self._project,
        ]
        if scope:
            cmd += ["--scope", str(scope)]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=self._timeout, check=False)
        except Exception as exc:  # missing binary, timeout — never propagate
            _log.warning("engram save failed (title=%r): %s", str(title)[:80], exc)
            return {"ok": False}
        if proc.returncode != 0:
            _log.warning(
                "engram save exited %d (title=%r): %s",
                proc.returncode,
                str(title)[:80],
                (proc.stderr or b"").decode("utf-8", "replace")[:200],
            )
            return {"ok": False}
        return {"ok": True}


def default_engram_client() -> EngramCliClient | None:
    """Build a CLI-backed client when Engram is detected, else None."""
    if not detect_engram():
        return None
    return EngramCliClient()
