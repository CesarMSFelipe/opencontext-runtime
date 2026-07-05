"""Per-session config snapshot writer (PR-013, SPEC-CLI-013-04).

Every resolved run persists its fully-resolved configuration to
``.opencontext/sessions/<session_id>/config-snapshot.yaml`` so a run is
reproducible: you can read exactly which config produced it. Write-only
projection — never read back into runtime behaviour.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from opencontext_core.config import OpenContextConfig
from opencontext_core.paths import StorageMode, resolve_workspace_path

SNAPSHOT_FILENAME = "config-snapshot.yaml"


def snapshot_path(root: str | Path, session_id: str) -> Path:
    return (
        resolve_workspace_path(root, StorageMode.local)
        / "sessions"
        / session_id
        / SNAPSHOT_FILENAME
    )


def write_snapshot(
    resolved: OpenContextConfig | dict[str, Any],
    session_id: str,
    root: str | Path = ".",
    *,
    provenance: dict[str, str] | None = None,
) -> Path:
    """Serialise *resolved* config to the session's ``config-snapshot.yaml``.

    Accepts either an :class:`OpenContextConfig` or an already-resolved dict.
    Returns the snapshot path. Best-effort directory creation; raises only on a
    genuine write failure (callers wrap it so a snapshot never fails a run).
    """
    if isinstance(resolved, OpenContextConfig):
        data: dict[str, Any] = resolved.model_dump(mode="json")
    else:
        data = dict(resolved)

    document: dict[str, Any] = {"session_id": session_id, "config": data}
    if provenance:
        document["provenance"] = dict(provenance)

    path = snapshot_path(root, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path
