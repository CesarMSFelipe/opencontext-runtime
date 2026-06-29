"""Reversible file checkpoints around harness writes.

Before :class:`ApplyPhase` edits files it snapshots exactly those files into a
checkpoint under a harness-owned location (``<root>/.opencontext/checkpoints/``).
A checkpoint records, per file, either the prior bytes or the fact that the file
did not exist. From a checkpoint the harness can:

- compute the :meth:`Checkpoint.diff` of what changed since the snapshot, and
- :meth:`Checkpoint.restore` the captured files back to their pre-apply state.

So a write becomes ``snapshot -> apply -> (on failure) restore`` and a failed or
unapproved apply leaves the workspace byte-identical to before.

This mirrors :class:`opencontext_core.configurator.backup.BackupStore` but is
scoped to a harness-supplied root rather than ``$HOME``, so it can checkpoint a
run's working tree (including temp dirs in tests) without a home-dir guard. Every
write goes through temp-file-plus-rename so a partial snapshot or restore can
never leave a truncated file behind.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from opencontext_core.agentic.receipt import sha256_file
from opencontext_core.models.artifact import Checkpoint as CheckpointModel


@dataclass(frozen=True)
class CheckpointFile:
    """One file captured before a change: its path and prior existence."""

    path: Path
    existed: bool
    blob: str | None = None


@dataclass(frozen=True)
class FileChange:
    """A single observed difference between a checkpoint and current disk."""

    path: str
    change: str  # "created" | "modified" | "deleted"


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".opencontext.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


class Checkpoint:
    """A single persisted snapshot of files about to change, with diff/restore."""

    def __init__(self, checkpoint_dir: Path, files: list[CheckpointFile]) -> None:
        self.dir = Path(checkpoint_dir)
        self.files = files

    @property
    def id(self) -> str:
        return self.dir.name

    @property
    def paths(self) -> list[Path]:
        return [f.path for f in self.files]

    # -- diff -----------------------------------------------------------------

    def diff(self) -> list[FileChange]:
        """Compute what changed on disk since the snapshot was taken.

        Compares each captured file's prior state against its current bytes:
        an absent-then-present file is ``created``, a present-then-absent file is
        ``deleted``, and a present file whose bytes differ is ``modified``.
        Unchanged files are omitted. Ordering follows the snapshot order.
        """
        content_dir = self.dir / "files"
        changes: list[FileChange] = []
        for snap in self.files:
            exists_now = snap.path.exists() and snap.path.is_file()
            if not snap.existed:
                if exists_now:
                    changes.append(FileChange(path=str(snap.path), change="created"))
                continue
            if not exists_now:
                changes.append(FileChange(path=str(snap.path), change="deleted"))
                continue
            original = (content_dir / snap.blob).read_bytes() if snap.blob else b""
            if snap.path.read_bytes() != original:
                changes.append(FileChange(path=str(snap.path), change="modified"))
        return changes

    # -- restore --------------------------------------------------------------

    def restore(self) -> dict[str, Any]:
        """Restore every captured file to its pre-snapshot state.

        Files that existed are rewritten with their prior bytes; files recorded
        as absent are deleted (recreating the "did-not-exist" state). After this
        returns, the captured paths are byte-identical to the moment the
        checkpoint was created.
        """
        content_dir = self.dir / "files"
        restored = 0
        deleted = 0
        for snap in self.files:
            if snap.existed:
                blob = snap.blob or ""
                data = (content_dir / blob).read_bytes()
                _atomic_write_bytes(snap.path, data)
                restored += 1
            elif snap.path.exists() and snap.path.is_file():
                snap.path.unlink()
                deleted += 1
        return {
            "status": "restored",
            "checkpoint_id": self.id,
            "files_restored": restored,
            "files_deleted": deleted,
        }


class CheckpointStore:
    """Create file checkpoints under a harness-owned root directory."""

    def __init__(self, root: Path) -> None:
        # Checkpoints live alongside other run artifacts, scoped to this root.
        self.root = Path(root) / ".opencontext" / "checkpoints"

    def create(self, paths: Iterable[Path], *, source: str = "apply") -> Checkpoint | None:
        """Snapshot ``paths`` before they change. Return ``None`` if empty.

        Existing files have their prior bytes copied into the checkpoint; files
        that do not exist are recorded so :meth:`Checkpoint.restore` can delete
        them again. Duplicate paths are collapsed, preserving first-seen order.
        """
        unique: list[Path] = []
        seen: set[Path] = set()
        for raw in paths:
            path = Path(raw)
            if path not in seen:
                seen.add(path)
                unique.append(path)

        if not unique:
            return None

        checkpoint_id = datetime.now().strftime("%Y%m%dT%H%M%S_%f") + "_" + uuid.uuid4().hex[:6]
        checkpoint_dir = self.root / checkpoint_id
        content_dir = checkpoint_dir / "files"
        content_dir.mkdir(parents=True, exist_ok=True)

        snapshots: list[CheckpointFile] = []
        manifest_files: list[dict[str, Any]] = []
        for index, path in enumerate(unique):
            existed = path.exists() and path.is_file()
            entry: dict[str, Any] = {"path": str(path), "existed": existed}
            blob_name: str | None = None
            if existed:
                blob_name = f"{index}.blob"
                _atomic_write_bytes(content_dir / blob_name, path.read_bytes())
                entry["blob"] = blob_name
            snapshots.append(CheckpointFile(path=path, existed=existed, blob=blob_name))
            manifest_files.append(entry)

        manifest = {
            "id": checkpoint_id,
            "created_at": datetime.now(UTC).isoformat(),
            "source": source,
            "files": manifest_files,
        }
        _atomic_write_bytes(
            checkpoint_dir / "manifest.json",
            (json.dumps(manifest, indent=2) + "\n").encode("utf-8"),
        )
        return Checkpoint(checkpoint_dir, snapshots)


class CheckpointManager:
    """Wraps :class:`CheckpointStore` to record per-file checksums (CHK-02).

    The existing :class:`CheckpointStore`/:class:`Checkpoint` keep doing the
    atomic snapshot/restore (CHK-01 untouched). This manager additionally embeds,
    per captured file, the sha256 of its *pre-apply* bytes (the snapshot blob) and
    the blob path into the checkpoint ``manifest.json``, and can project the
    on-disk checkpoint onto the durable :class:`CheckpointModel`
    (schema ``opencontext.checkpoint.v1``) so it links into the run manifest.
    """

    def __init__(self, root: Path) -> None:
        self._store = CheckpointStore(root)

    def create(
        self,
        paths: Iterable[Path],
        *,
        session_id: str = "",
        run_id: str = "",
        source: str = "apply",
    ) -> Checkpoint | None:
        """Snapshot ``paths`` and record per-file checksums. ``None`` if empty."""
        checkpoint = self._store.create(paths, source=source)
        if checkpoint is None:
            return None
        self._augment_manifest(checkpoint, session_id=session_id, run_id=run_id)
        return checkpoint

    @staticmethod
    def _checksums(checkpoint: Checkpoint) -> tuple[dict[str, str], dict[str, str]]:
        content_dir = checkpoint.dir / "files"
        checksums: dict[str, str] = {}
        snapshot_paths: dict[str, str] = {}
        for snap in checkpoint.files:
            if snap.existed and snap.blob:
                blob_path = content_dir / snap.blob
                digest = sha256_file(blob_path)
                if digest is not None:
                    checksums[str(snap.path)] = digest
                snapshot_paths[str(snap.path)] = str(blob_path)
        return checksums, snapshot_paths

    def _augment_manifest(self, checkpoint: Checkpoint, *, session_id: str, run_id: str) -> None:
        manifest_path = checkpoint.dir / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {"id": checkpoint.id, "files": []}
        checksums, snapshot_paths = self._checksums(checkpoint)
        manifest["checksums"] = checksums
        manifest["snapshot_paths"] = snapshot_paths
        manifest["session_id"] = session_id
        manifest["run_id"] = run_id
        _atomic_write_bytes(manifest_path, (json.dumps(manifest, indent=2) + "\n").encode("utf-8"))

    def model(
        self, checkpoint: Checkpoint, *, session_id: str = "", run_id: str = ""
    ) -> CheckpointModel:
        """Project the on-disk checkpoint onto the durable Checkpoint model."""
        manifest_path = checkpoint.dir / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}
        return CheckpointModel(
            checkpoint_id=str(manifest.get("id", checkpoint.id)),
            session_id=session_id or str(manifest.get("session_id", "")),
            run_id=run_id or str(manifest.get("run_id", "")),
            files=[str(f.path) for f in checkpoint.files],
            checksums=manifest.get("checksums", {}),
            snapshot_paths=manifest.get("snapshot_paths", {}),
            created_at=str(manifest.get("created_at", datetime.now(UTC).isoformat())),
        )
