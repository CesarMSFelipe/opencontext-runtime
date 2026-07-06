"""Explain a persisted run's context pack (KG_CONTEXT_COMPRESSION_CONTRACT).

Replays which files/symbols/edges a run's ``context-pack.json`` selected and
why, plus the pack metrics block, from either persisted run layout:
``.opencontext/runs/<run_id>/`` or ``.opencontext/sessions/<sid>/runs/<run_id>/``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from opencontext_core.paths import StorageMode, resolve_workspace_path


def locate_run_context_pack(root: Path, run_id: str) -> Path | None:
    """Return the run's ``context-pack.json`` path, or None when not persisted."""

    workspace = resolve_workspace_path(root, StorageMode.local)
    direct = workspace / "runs" / run_id / "context-pack.json"
    if direct.is_file():
        return direct
    sessions = workspace / "sessions"
    if sessions.is_dir():
        for session_dir in sorted(sessions.iterdir()):
            candidate = session_dir / "runs" / run_id / "context-pack.json"
            if candidate.is_file():
                return candidate
    return None


def explain_pack_payload(pack: dict[str, Any], *, run_id: str, pack_path: str) -> dict[str, Any]:
    """Shape a persisted pack dict into the explain-pack report payload."""

    selected: list[dict[str, Any]] = []
    edges_used: list[str] = []
    for item in pack.get("included") or []:
        metadata = item.get("metadata") or {}
        retrieval_source = metadata.get("retrieval_source") or item.get("source_type", "")
        reason = metadata.get("reason") or f"included via {retrieval_source or 'unknown'}"
        provenance = metadata.get("graph_provenance") or {}
        relationships = provenance.get("relationships") or []
        edges_used.extend(str(rel) for rel in relationships)
        selected.append(
            {
                "id": item.get("id", ""),
                "source": item.get("source", ""),
                "source_type": item.get("source_type", ""),
                "tokens": item.get("tokens", 0),
                "score": item.get("score", 0.0),
                "reason": reason,
                "retrieval_source": retrieval_source,
            }
        )

    omissions = [
        {
            "item_id": omission.get("item_id", ""),
            "reason": omission.get("reason", ""),
            "tokens": omission.get("tokens", 0),
        }
        for omission in pack.get("omissions") or []
    ]

    return {
        "run_id": run_id,
        "pack_path": pack_path,
        "selected": selected,
        "omissions": omissions,
        "edges_used": edges_used,
        "used_tokens": pack.get("used_tokens", 0),
        "available_tokens": pack.get("available_tokens", 0),
        "compression": pack.get("compression"),
        "context": pack.get("context"),
    }
