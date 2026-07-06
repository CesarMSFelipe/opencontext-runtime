"""Install manifest v2 — snapshot collector and manifest-driven uninstall.

The workspace install snapshots the project before writing, diffs afterwards,
and records everything it created in ``oc-manifest.json`` (schema_version 2,
additive over the v1 ownership fields). Uninstall then deletes exactly the
recorded ``created_paths`` + ``state_paths``, reverts managed marker blocks in
``modified_files``, reports unmanaged leftovers without deleting them, and
verifies by re-scanning the manifest (INSTALL_UNINSTALL_CONTRACT.md).
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA_VERSION = 2

# Both managed-block syntaxes used by configurator.filemerge.
_MARKER_RE = re.compile(r"opencontext:([A-Za-z0-9_-]+):start")

# Root-level files that installs merge marker blocks into.
_BLOCK_MANAGED_CANDIDATES = (".gitignore", "AGENTS.md", "CLAUDE.md", "GEMINI.md", "QWEN.md")

# Pre-existing directories whose contents install may extend; their trees are
# snapshotted so files added inside them are still recorded individually.
_MANAGED_DIRS = (".opencontext", ".storage", ".claude")


# ---------------------------------------------------------------------------
# Managed marker blocks
# ---------------------------------------------------------------------------


def detect_markers(text: str) -> list[str]:
    """Return the managed block ids present in *text*, in order of appearance."""
    seen: list[str] = []
    for match in _MARKER_RE.finditer(text):
        marker = match.group(1)
        if marker not in seen:
            seen.append(marker)
    return seen


def strip_managed_blocks(text: str, markers: list[str]) -> str:
    """Remove the listed managed blocks (both comment syntaxes); no-op otherwise."""
    from opencontext_core.configurator.filemerge import (
        inject_managed_lines,
        inject_managed_section,
    )

    for marker in markers:
        text = inject_managed_lines(text, marker, [])
        text = inject_managed_section(text, marker, "")
    return text


# ---------------------------------------------------------------------------
# Install method detection (best effort, report only)
# ---------------------------------------------------------------------------


def detect_install_method() -> str:
    """Best-effort detection of how the running OpenContext was installed."""
    import sys

    try:
        import importlib.metadata as im

        dist = im.distribution("opencontext-cli")
        location = str(dist.locate_file(""))
        raw = dist.read_text("direct_url.json")
        if raw and json.loads(raw).get("dir_info", {}).get("editable"):
            return "editable"
        if f"{os.sep}pipx{os.sep}" in location:
            return "pipx"
        if sys.prefix != getattr(sys, "base_prefix", sys.prefix):
            return "venv"
        return "pip"
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Snapshot + diff collector
# ---------------------------------------------------------------------------


@dataclass
class WorkspaceSnapshot:
    """Pre-install picture of the paths install may create or modify."""

    root: Path
    top_level: set[str] = field(default_factory=set)
    entries: set[str] = field(default_factory=set)
    block_markers: dict[str, list[str]] = field(default_factory=dict)


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _walk(base: Path, root: Path, into: set[str]) -> None:
    for current, dirnames, filenames in os.walk(base, followlinks=False):
        current_path = Path(current)
        into.add(_rel(current_path, root))
        for name in [*dirnames, *filenames]:
            into.add(_rel(current_path / name, root))


def snapshot_workspace(root: Path) -> WorkspaceSnapshot:
    """Record what already exists before install writes anything."""
    root = Path(root)
    snap = WorkspaceSnapshot(root=root)
    if not root.is_dir():
        return snap
    for child in root.iterdir():
        snap.top_level.add(child.name)
        snap.entries.add(child.name)
    for name in _MANAGED_DIRS:
        managed = root / name
        if managed.is_dir():
            _walk(managed, root, snap.entries)
    for name in _BLOCK_MANAGED_CANDIDATES:
        candidate = root / name
        if candidate.is_file():
            try:
                snap.block_markers[name] = detect_markers(
                    candidate.read_text(encoding="utf-8", errors="ignore")
                )
            except OSError:
                snap.block_markers[name] = []
    return snap


def collect_install_changes(snapshot: WorkspaceSnapshot, root: Path) -> dict[str, Any]:
    """Diff the workspace against *snapshot*: everything new is install-created."""
    root = Path(root)
    created: set[str] = set()
    if root.is_dir():
        for child in root.iterdir():
            if child.name not in snapshot.top_level:
                created.add(child.name)
                if child.is_dir() and not child.is_symlink():
                    _walk(child, root, created)
        for name in _MANAGED_DIRS:
            managed = root / name
            if name in snapshot.top_level and managed.is_dir():
                after: set[str] = set()
                _walk(managed, root, after)
                created.update(after - snapshot.entries)

    modified_files: list[dict[str, Any]] = []
    for name in _BLOCK_MANAGED_CANDIDATES:
        candidate = root / name
        if not candidate.is_file():
            continue
        try:
            markers_now = detect_markers(candidate.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
        new_markers = [m for m in markers_now if m not in snapshot.block_markers.get(name, [])]
        if new_markers:
            modified_files.append(
                {
                    "path": name,
                    "markers": new_markers,
                    "created_by_install": name not in snapshot.top_level,
                }
            )
    # A pre-existing file that only gained a managed block is modified, not created.
    created -= {entry["path"] for entry in modified_files if not entry["created_by_install"]}
    return {"created_paths": sorted(created), "modified_files": modified_files}


def _ordered_union(first: list[str], second: list[str]) -> list[str]:
    out: list[str] = []
    for item in [*first, *second]:
        if item not in out:
            out.append(item)
    return out


def build_manifest_fields(
    root: Path,
    snapshot: WorkspaceSnapshot,
    *,
    agent_configs: list[str],
    product_version: str | None = None,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the v2 manifest fields, merging with *existing* so reinstalls are
    idempotent (INST-003: no duplicated entries, no lost entries)."""
    from opencontext_core.paths import StorageMode, resolve_storage_path

    root = Path(root)
    changes = collect_install_changes(snapshot, root)
    existing = existing or {}

    state_paths: list[str] = []
    if (root / ".opencontext").is_dir():
        state_paths.append(".opencontext")
    if (root / ".storage" / "opencontext").is_dir():
        state_paths.append(".storage/opencontext")
    try:
        xdg = resolve_storage_path(root, StorageMode.user)
        if xdg.is_dir():
            state_paths.append(str(xdg))
    except Exception:
        pass

    if product_version is None:
        try:
            from importlib.metadata import version as _pkg_version

            product_version = _pkg_version("opencontext-cli")
        except Exception:
            product_version = "unknown"

    modified_by_path: dict[str, dict[str, Any]] = {
        str(entry.get("path")): dict(entry)
        for entry in existing.get("modified_files") or []
        if isinstance(entry, dict)
    }
    for entry in changes["modified_files"]:
        previous = modified_by_path.get(entry["path"])
        if previous:
            previous["markers"] = _ordered_union(previous.get("markers") or [], entry["markers"])
        else:
            modified_by_path[entry["path"]] = entry

    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "install_method": existing.get("install_method") or detect_install_method(),
        "product_version": product_version,
        "created_paths": _ordered_union(
            list(existing.get("created_paths") or []), changes["created_paths"]
        ),
        "modified_files": list(modified_by_path.values()),
        "agent_configs": _ordered_union(list(existing.get("agent_configs") or []), agent_configs),
        "state_paths": _ordered_union(list(existing.get("state_paths") or []), state_paths),
        "timestamp": datetime.now(tz=UTC).isoformat(),
    }


def finalize_install_manifest(
    root: Path, snapshot: WorkspaceSnapshot, *, agent_configs: list[str]
) -> dict[str, Any]:
    """Diff, merge with any prior manifest, and persist the v2 fields."""
    from opencontext_core.paths import read_manifest, write_manifest

    root = Path(root)
    workspace = root / ".opencontext"
    existing = read_manifest(workspace)
    fields = build_manifest_fields(root, snapshot, agent_configs=agent_configs, existing=existing)
    write_manifest(workspace, root, fields["product_version"], extra=fields)
    return fields


# ---------------------------------------------------------------------------
# Manifest-driven purge + verify
# ---------------------------------------------------------------------------


def _safe_rel_entries(manifest: dict[str, Any], key: str) -> list[str]:
    """Manifest path entries that are safely inside the project root."""
    out: list[str] = []
    for raw in manifest.get(key) or []:
        rel = str(raw)
        parts = Path(rel).parts
        if Path(rel).is_absolute() or ".." in parts or not parts:
            continue
        out.append(rel)
    return out


def _resolve_state_paths(root: Path, manifest: dict[str, Any]) -> list[tuple[str, Path]]:
    """Resolve state_paths with safety gates: in-root entries pass; absolute
    entries must be OpenContext-owned or clearly OpenContext-named."""
    from opencontext_core.paths import is_owned

    out: list[tuple[str, Path]] = []
    for raw in manifest.get("state_paths") or []:
        rel = str(raw)
        path = Path(rel)
        if not path.is_absolute():
            if ".." in path.parts or not path.parts:
                continue
            out.append((rel, root / path))
            continue
        if "opencontext" in path.parts or is_owned(path):
            out.append((rel, path))
    return out


def _remove_no_follow(path: Path) -> None:
    """Delete *path* without ever following a symlink out of the tree."""
    if path.is_symlink():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        path.unlink()


def _block_managed_paths(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for entry in manifest.get("modified_files") or []:
        if isinstance(entry, dict) and entry.get("path"):
            out[str(entry["path"])] = entry
    return out


def purge_from_manifest(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Delete exactly the manifest-managed paths; report unmanaged leftovers.

    Order: revert managed blocks, unlink created files, remove state roots,
    prune created directories deepest-first. Unmanaged content is reported and
    never deleted (safety rules in INSTALL_UNINSTALL_CONTRACT.md).
    """
    root = Path(root)
    removed: list[str] = []
    reverted: list[str] = []
    unmanaged: list[str] = []

    blocks = _block_managed_paths(manifest)
    for rel, entry in blocks.items():
        if Path(rel).is_absolute() or ".." in Path(rel).parts:
            continue
        target = root / rel
        if not target.is_file():
            continue
        try:
            text = target.read_text(encoding="utf-8")
            markers = [str(m) for m in entry.get("markers") or []] or detect_markers(text)
            stripped = strip_managed_blocks(text, markers)
            if stripped == text:
                continue
            if not stripped.strip() and entry.get("created_by_install"):
                target.unlink()
                removed.append(rel)
            else:
                target.write_text(stripped, encoding="utf-8")
                reverted.append(rel)
        except OSError:
            continue

    state_paths = _resolve_state_paths(root, manifest)
    state_roots = [path for _, path in state_paths]

    created = _safe_rel_entries(manifest, "created_paths")
    created_dirs: list[tuple[str, Path]] = []
    for rel in created:
        if rel in blocks:
            continue  # block-managed: handled by the revert pass above
        target = root / rel
        if any(path == target or path in target.parents for path in state_roots):
            continue  # covered by the state-root removal below
        try:
            if target.is_symlink() or target.is_file():
                target.unlink()
                removed.append(rel)
            elif target.is_dir():
                created_dirs.append((rel, target))
        except OSError:
            pass

    for raw, path in state_paths:
        if not path.exists() and not path.is_symlink():
            continue
        try:
            _remove_no_follow(path)
            removed.append(raw)
        except OSError:
            pass

    created_set = set(created)
    for rel, target in sorted(
        created_dirs, key=lambda item: len(Path(item[0]).parts), reverse=True
    ):
        try:
            target.rmdir()
            removed.append(rel)
        except OSError:
            if target.is_dir():
                leftovers = [
                    _rel(child, root)
                    for child in target.iterdir()
                    if _rel(child, root) not in created_set
                ]
                unmanaged.extend(leftovers)

    # Prune an emptied .storage container dir (legacy layout parent).
    storage = root / ".storage"
    if storage.is_dir() and not any(storage.iterdir()):
        try:
            storage.rmdir()
            removed.append(".storage")
        except OSError:
            pass

    return {
        "removed": removed,
        "reverted": reverted,
        "unmanaged": sorted(dict.fromkeys(unmanaged)),
    }


def verify_from_manifest(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Re-scan the manifest: managed residue vs unmanaged leftovers."""
    root = Path(root)
    residue: list[str] = []
    unmanaged: list[str] = []

    blocks = _block_managed_paths(manifest)
    for rel, entry in blocks.items():
        if Path(rel).is_absolute() or ".." in Path(rel).parts:
            continue
        target = root / rel
        if not target.is_file():
            continue
        try:
            markers = detect_markers(target.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
        wanted = [str(m) for m in entry.get("markers") or []]
        if any(m in markers for m in wanted) or (not wanted and markers):
            residue.append(rel)

    state_paths = _resolve_state_paths(root, manifest)
    state_roots = []
    for raw, path in state_paths:
        state_roots.append(path)
        if path.exists() or path.is_symlink():
            residue.append(raw)

    created = _safe_rel_entries(manifest, "created_paths")
    created_set = set(created)
    for rel in created:
        if rel in blocks:
            continue
        target = root / rel
        if any(path == target or path in target.parents for path in state_roots):
            continue
        if target.is_symlink() or target.is_file():
            residue.append(rel)
        elif target.is_dir():
            children = list(target.iterdir())
            if not children:
                residue.append(rel)
            else:
                unmanaged.extend(
                    _rel(child, root) for child in children if _rel(child, root) not in created_set
                )

    return {
        "residue": sorted(dict.fromkeys(residue)),
        "unmanaged": sorted(dict.fromkeys(unmanaged)),
    }


# ---------------------------------------------------------------------------
# Global (HOME) state roots for product-scope purge/verify
# ---------------------------------------------------------------------------


def global_state_roots() -> list[Path]:
    """The HOME-level OpenContext state dirs a global purge owns.

    Respects XDG env overrides; falls back to the conventional locations
    (mirrors ``resolve_storage_path`` for the state dir).
    """
    import platformdirs

    home = Path.home()
    config_env = os.environ.get("XDG_CONFIG_HOME", "").strip()
    cache_env = os.environ.get("XDG_CACHE_HOME", "").strip()
    state_env = os.environ.get("XDG_STATE_HOME", "").strip()

    config_base = Path(config_env) if config_env else home / ".config"
    cache_base = Path(cache_env) if cache_env else home / ".cache"
    if state_env:
        state_dir = Path(state_env) / "opencontext"
    else:
        state_dir = Path(platformdirs.user_state_path("opencontext"))

    roots = [
        config_base / "opencontext",
        home / ".config" / "opencontext",
        home / ".opencontext",
        state_dir,
        cache_base / "opencontext",
    ]
    return list(dict.fromkeys(roots))
