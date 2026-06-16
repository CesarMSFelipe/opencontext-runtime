"""Reversible safety for agent configuration.

Before the configurator rewrites an agent's files it snapshots the exact files
that are about to change into a timestamped backup under
``~/.opencontext/backups/<id>/``. Each snapshot records, per file, either the
prior bytes or the fact that the file did not exist, alongside a small JSON
manifest. Restoring puts those files back -- recreating "did-not-exist" entries
by deleting them again -- so a failed or unwanted configuration leaves the
developer's tree exactly as it was.

Paths are validated to stay under ``$HOME`` on restore, and every write goes
through a temp-file-plus-rename so a partial backup or restore can never leave a
truncated file behind.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FileSnapshot:
    """One file captured before a change: its path and prior existence."""

    path: Path
    existed: bool


@dataclass(frozen=True)
class BackupRecord:
    """A persisted backup: its id, when it was taken, and what it covers."""

    id: str
    created_at: str
    agents: list[str]
    source: str
    files: list[FileSnapshot]


def _backups_root() -> Path:
    """Resolve the backups directory under the current home.

    Read lazily so a monkeypatched ``Path.home`` is honored in tests.
    """

    return Path.home() / ".opencontext" / "backups"


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".opencontext.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _new_backup_id() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S_%f")


def plan_actions(paths: Iterable[Path]) -> list[dict[str, str]]:
    """Classify each path as ``create`` or ``modify`` for a dry-run plan."""

    plan: list[dict[str, str]] = []
    for path in paths:
        action = "modify" if Path(path).exists() else "create"
        plan.append({"path": str(path), "action": action})
    return plan


class BackupStore:
    """Create, list, and restore per-file configuration snapshots."""

    def __init__(self) -> None:
        self.root = _backups_root()

    # -- create ---------------------------------------------------------------

    def create(
        self,
        agents: list[str],
        paths: Iterable[Path],
        *,
        source: str = "configure",
    ) -> BackupRecord | None:
        """Snapshot ``paths`` before they change. Return ``None`` if empty.

        Files that exist have their prior bytes copied into the backup; files
        that do not exist are recorded so restore can delete them again. When
        ``paths`` is empty (nothing will change) no backup is written.
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

        backup_id = _new_backup_id()
        backup_dir = self.root / backup_id
        content_dir = backup_dir / "files"
        content_dir.mkdir(parents=True, exist_ok=True)

        snapshots: list[FileSnapshot] = []
        manifest_files: list[dict[str, Any]] = []
        for index, path in enumerate(unique):
            existed = path.exists()
            entry: dict[str, Any] = {"path": str(path), "existed": existed}
            if existed:
                blob_name = f"{index}.blob"
                _atomic_write_bytes(content_dir / blob_name, path.read_bytes())
                entry["blob"] = blob_name
            snapshots.append(FileSnapshot(path=path, existed=existed))
            manifest_files.append(entry)

        created_at = datetime.now(UTC).isoformat()
        manifest = {
            "id": backup_id,
            "created_at": created_at,
            "agents": list(agents),
            "source": source,
            "files": manifest_files,
        }
        _atomic_write_bytes(
            backup_dir / "manifest.json",
            (json.dumps(manifest, indent=2) + "\n").encode("utf-8"),
        )

        return BackupRecord(
            id=backup_id,
            created_at=created_at,
            agents=list(agents),
            source=source,
            files=snapshots,
        )

    # -- list -----------------------------------------------------------------

    def list(self) -> list[BackupRecord]:
        """Return all backups, newest first."""

        if not self.root.exists():
            return []
        records: list[BackupRecord] = []
        for entry in self.root.iterdir():
            manifest = entry / "manifest.json"
            if not manifest.is_file():
                continue
            record = self._read_record(manifest)
            if record is not None:
                records.append(record)
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records

    # -- restore --------------------------------------------------------------

    def restore(self, backup_id: str) -> dict[str, Any]:
        """Restore the files captured in ``backup_id``.

        ``backup_id`` may be the literal ``"latest"`` to restore the most recent
        backup. Files that existed are rewritten with their prior bytes; files
        recorded as absent are deleted. Every target path is validated to stay
        under ``$HOME`` before anything is touched.
        """

        record = self._resolve(backup_id)
        if record is None:
            return {"status": "error", "message": f"backup not found: {backup_id}"}

        home = Path.home().resolve()
        # Validate up front so a bad manifest restores nothing at all.
        for snap in record.files:
            self._ensure_under_home(snap.path, home)

        backup_dir = self.root / record.id
        content_dir = backup_dir / "files"
        blobs = self._manifest_blobs(backup_dir)

        restored = 0
        deleted = 0
        for index, snap in enumerate(record.files):
            if snap.existed:
                blob_name = blobs.get(index, f"{index}.blob")
                data = (content_dir / blob_name).read_bytes()
                _atomic_write_bytes(snap.path, data)
                restored += 1
            elif snap.path.exists():
                snap.path.unlink()
                deleted += 1

        return {
            "status": "restored",
            "backup_id": record.id,
            "files_restored": restored,
            "files_deleted": deleted,
        }

    # -- internals ------------------------------------------------------------

    def _resolve(self, backup_id: str) -> BackupRecord | None:
        if backup_id == "latest":
            records = self.list()
            return records[0] if records else None
        manifest = self.root / backup_id / "manifest.json"
        if not manifest.is_file():
            return None
        return self._read_record(manifest)

    def _read_record(self, manifest_path: Path) -> BackupRecord | None:
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        files = [
            FileSnapshot(path=Path(f["path"]), existed=bool(f["existed"]))
            for f in data.get("files", [])
        ]
        return BackupRecord(
            id=data["id"],
            created_at=data.get("created_at", ""),
            agents=list(data.get("agents", [])),
            source=data.get("source", ""),
            files=files,
        )

    def _manifest_blobs(self, backup_dir: Path) -> dict[int, str]:
        """Map file index to its stored blob name, per the manifest."""

        try:
            data = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        blobs: dict[int, str] = {}
        for index, entry in enumerate(data.get("files", [])):
            blob = entry.get("blob")
            if blob:
                blobs[index] = blob
        return blobs

    @staticmethod
    def _ensure_under_home(path: Path, home: Path) -> None:
        # Resolve the parent so non-existent targets (did-not-exist entries) and
        # symlink tricks still resolve to a real on-disk location.
        candidate = path.parent.resolve() / path.name
        try:
            candidate.relative_to(home)
        except ValueError:
            raise ValueError(f"refusing to restore path outside home: {path}") from None


def list_backups() -> list[BackupRecord]:
    """Module-level convenience: all backups, newest first."""

    return BackupStore().list()


def restore(backup_id: str) -> dict[str, Any]:
    """Module-level convenience: restore ``backup_id`` (or ``"latest"``)."""

    return BackupStore().restore(backup_id)
