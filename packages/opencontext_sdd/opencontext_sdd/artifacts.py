"""SDD registry and per-change manifest artifacts.

SDD_CONTRACT "Current → Target additions": a project-level registry of known
changes (``.opencontext/sdd/registry.json``) and a per-change ``manifest.json``
carrying cycle metadata plus the state-machine position (SDD-ARTIFACTS).

All writes are additive JSON: fields are only ever added, never renamed or
removed. Entries record real disk state resolved through
:func:`opencontext_sdd.status.Resolve` — never fabricated positions.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REGISTRY_SCHEMA = "opencontext.sdd-registry"
MANIFEST_SCHEMA = "opencontext.sdd-manifest"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def registry_path(cwd: Path | str) -> Path:
    """Project-level SDD registry path (``.opencontext/sdd/registry.json``)."""
    return Path(cwd) / ".opencontext" / "sdd" / "registry.json"


def load_registry(cwd: Path | str) -> dict[str, Any]:
    """Read the registry; a missing/corrupt file yields a fresh empty registry."""
    path = registry_path(cwd)
    fresh: dict[str, Any] = {
        "schemaName": REGISTRY_SCHEMA,
        "schemaVersion": 1,
        "changes": {},
    }
    if not path.exists():
        return fresh
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fresh
    if not isinstance(data, dict):
        return fresh
    data.setdefault("schemaName", REGISTRY_SCHEMA)
    data.setdefault("schemaVersion", 1)
    data.setdefault("changes", {})
    return data


def _write_registry(cwd: Path | str, registry: dict[str, Any]) -> Path:
    path = registry_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    return path


def ensure_registry(cwd: Path | str) -> Path:
    """Create the registry file when missing; never overwrites an existing one."""
    path = registry_path(cwd)
    if path.exists():
        return path
    return _write_registry(cwd, load_registry(cwd))


def update_registry(
    cwd: Path | str,
    change: str,
    *,
    state: str,
    path: str | None = None,
) -> Path:
    """Upsert the registry entry for *change* with its state-machine position."""
    registry = load_registry(cwd)
    entry = dict(registry["changes"].get(change) or {})
    entry["state"] = state
    entry["updated_at"] = _now()
    if path is not None:
        entry["path"] = path
    registry["changes"][change] = entry
    return _write_registry(cwd, registry)


def write_change_manifest(cwd: Path | str, change: str | None) -> Path | None:
    """Write ``openspec/changes/<change>/manifest.json`` from resolved disk state.

    Returns ``None`` (writes nothing) when the change dir does not exist —
    a manifest is evidence of a real change, never a placeholder.
    """
    from opencontext_sdd.status import Resolve

    status = Resolve(change, cwd=str(cwd))
    if status.changeRoot is None or status.changeName is None:
        return None
    payload = {
        "schemaName": MANIFEST_SCHEMA,
        "schemaVersion": 1,
        "change": status.changeName,
        "state": status.cycleState,
        "currentPhase": status.currentPhase,
        "nextRecommended": status.nextRecommended,
        "artifacts": dict(status.artifacts),
        "blockedReasons": list(status.blockedReasons),
        "updated_at": _now(),
    }
    manifest = Path(cwd) / status.changeRoot / "manifest.json"
    manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return manifest


def mark_manifest_archived(archived_root: Path, change: str) -> Path:
    """Update (or create) the preserved manifest of an archived change."""
    manifest_path = archived_root / "manifest.json"
    payload: dict[str, Any] = {}
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                payload = existing
        except (OSError, json.JSONDecodeError):
            payload = {}
    payload.setdefault("schemaName", MANIFEST_SCHEMA)
    payload.setdefault("schemaVersion", 1)
    payload["change"] = change
    payload["state"] = "archived"
    payload["currentPhase"] = "archive"
    payload["nextRecommended"] = "new"
    payload["updated_at"] = _now()
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return manifest_path


__all__ = [
    "MANIFEST_SCHEMA",
    "REGISTRY_SCHEMA",
    "ensure_registry",
    "load_registry",
    "mark_manifest_archived",
    "registry_path",
    "update_registry",
    "write_change_manifest",
]
