"""Durable session/run on-disk layout + patch/manifest helpers (PR-002, L2).

Materialises the book layout (doc 24 §8)::

    .opencontext/sessions/<session_id>/runs/<run_id>/
        artifacts/  receipts/  checkpoints/  patches/

and provides the ``patch-NNN.diff`` writer, a unified-diff builder over a
reversible checkpoint, and the :class:`RunManifest` index builder that scans a
run root. Everything here is additive and only used on the
``runtime.durable_artifacts`` path.
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Any

from opencontext_core.models.artifact import Checkpoint
from opencontext_core.models.run_manifest import (
    ArtifactRef,
    CheckpointRef,
    ReceiptRef,
    RunManifest,
)


def sessions_root(root: Path | str) -> Path:
    """Return the runtime sessions directory under the project workspace."""
    from opencontext_core.paths import StorageMode, resolve_workspace_path

    return resolve_workspace_path(root, StorageMode.local) / "sessions"


def session_root(root: Path | str, session_id: str) -> Path:
    """Return the directory holding one session's runs."""
    return sessions_root(root) / session_id


def run_root(root: Path | str, session_id: str, run_id: str) -> Path:
    """Return ``.../sessions/<session_id>/runs/<run_id>``."""
    return session_root(root, session_id) / "runs" / run_id


def ensure_layout(root: Path | str, session_id: str, run_id: str) -> Path:
    """Create (only) the per-run root directory and return it.

    The ``{artifacts,receipts,checkpoints,patches}`` subdirs are created lazily
    by their own writers (ArtifactStore, ReceiptStore, ``next_patch_path``, the
    checkpoint writers) on first real write, so a run that produces only some
    evidence kinds leaves no empty placeholder directories. Idempotent.
    """
    base = run_root(root, session_id, run_id)
    base.mkdir(parents=True, exist_ok=True)
    return base


def find_run_root(root: Path | str, run_id: str) -> Path | None:
    """Locate a run's durable root by scanning ``sessions/*/runs/<run_id>``.

    Avoids a separate run->session index: there is exactly one run dir per id.
    Returns ``None`` when no durable run exists for *run_id* (e.g. legacy run).
    """
    base = sessions_root(root)
    if not base.exists():
        return None
    for session_dir in base.iterdir():
        candidate = session_dir / "runs" / run_id
        if candidate.is_dir():
            return candidate
    return None


def next_patch_path(run_dir: Path | str) -> Path:
    """Return the next ``patches/patch-NNN.diff`` path (1-based, zero-padded)."""
    patches = Path(run_dir) / "patches"
    patches.mkdir(parents=True, exist_ok=True)
    existing = sorted(patches.glob("patch-*.diff"))
    index = len(existing) + 1
    return patches / f"patch-{index:03d}.diff"


def build_unified_diff(checkpoint: Any) -> str:
    """Build a unified diff from a reversible checkpoint's pre/post file bytes.

    Reads each captured file's pre-apply bytes from the checkpoint blob and its
    current bytes from disk, emitting one ``difflib.unified_diff`` block per
    changed file. Binary or undecodable content is summarised, never corrupted.
    """
    content_dir = Path(checkpoint.dir) / "files"
    blocks: list[str] = []
    for snap in checkpoint.files:
        path = Path(snap.path)
        before = b""
        if snap.existed and snap.blob:
            before = (content_dir / snap.blob).read_bytes()
        after = path.read_bytes() if path.exists() and path.is_file() else b""
        if before == after:
            continue
        try:
            before_lines = before.decode("utf-8").splitlines(keepends=True)
            after_lines = after.decode("utf-8").splitlines(keepends=True)
        except UnicodeDecodeError:
            blocks.append(f"Binary file {path} changed\n")
            continue
        rel = str(path)
        diff = difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
        )
        block = "".join(diff)
        if block and not block.endswith("\n"):
            block += "\n"
        blocks.append(block)
    return "".join(blocks)


def build_run_manifest(
    run_dir: Path | str,
    *,
    session_id: str,
    run_id: str,
    workflow_id: str = "",
    status: str = "unknown",
    events_path: str = "",
    summary_path: str | None = None,
) -> RunManifest:
    """Scan a run root's evidence subdirs and build the immutable index.

    Reads every ``artifacts/*.ref.json`` (ArtifactRef), the
    ``receipts/receipts.jsonl`` book receipts, and ``checkpoints/*.json``
    (Checkpoint records), projecting each onto its manifest ref type.
    """
    base = Path(run_dir)

    artifacts: list[ArtifactRef] = []
    for ref_path in sorted((base / "artifacts").glob("*.ref.json")):
        try:
            artifacts.append(ArtifactRef.model_validate_json(ref_path.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            continue

    receipts: list[ReceiptRef] = []
    receipts_jsonl = base / "receipts" / "receipts.jsonl"
    if receipts_jsonl.exists():
        rel = receipts_jsonl.relative_to(base).as_posix()
        for line in receipts_jsonl.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            rid = data.get("receipt_id")
            if not rid:
                continue
            receipts.append(ReceiptRef(receipt_id=rid, path=rel, kind=data.get("kind")))

    checkpoints: list[CheckpointRef] = []
    for cp_path in sorted((base / "checkpoints").glob("*.json")):
        try:
            model = Checkpoint.model_validate_json(cp_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        checkpoints.append(
            CheckpointRef(
                checkpoint_id=model.checkpoint_id,
                path=cp_path.relative_to(base).as_posix(),
            )
        )

    return RunManifest(
        session_id=session_id,
        run_id=run_id,
        workflow_id=workflow_id,
        status=status,
        artifacts=artifacts,
        receipts=receipts,
        checkpoints=checkpoints,
        events_path=events_path,
        summary_path=summary_path,
    )


def write_run_manifest(run_dir: Path | str, manifest: RunManifest) -> Path:
    """Write ``manifest.json`` at the run root and return its path."""
    path = Path(run_dir) / "manifest.json"
    path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return path
