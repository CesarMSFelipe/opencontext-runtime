"""Backup system for OpenContext configurations.

Features:
- Compressed (tar.gz)
- Deduplicated (identical configs not re-backed up)
- Auto-pruned (keeps 5 most recent)
- Pin important backups
"""

from __future__ import annotations

import hashlib
import json
import tarfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class BackupInfo:
    """Information about a backup."""

    id: str
    timestamp: str
    size_bytes: int
    hash: str
    pinned: bool
    files: list[str]


class BackupManager:
    """Manages configuration backups.

    Creates compressed, deduplicated backups of agent configs
    and OpenContext project settings.
    """

    MAX_BACKUPS = 5
    BACKUP_DIR = ".opencontext/backups"

    def __init__(self, project_root: str | Path = ".") -> None:
        self.project_root = Path(project_root).resolve()
        self.backup_dir = self.project_root / self.BACKUP_DIR
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.backup_dir / "index.json"

    def create_backup(
        self,
        name: str | None = None,
        paths: list[str] | None = None,
    ) -> BackupInfo:
        """Create a new backup.

        Args:
            name: Optional backup name. Defaults to timestamp.
            paths: Paths to backup. Defaults to common config paths.

        Returns:
            Backup info.
        """

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_id = name or f"backup_{timestamp}"

        if paths is None:
            paths = self._default_paths()

        # Collect files
        files_to_backup: list[Path] = []
        for pattern in paths:
            for path in self.project_root.rglob(pattern):
                if path.is_file():
                    files_to_backup.append(path)

        # Deduplication: check if identical backup already exists
        content_hash = self._compute_hash(files_to_backup)
        existing = self._find_by_hash(content_hash)
        if existing is not None:
            return existing

        # Create tar.gz
        backup_path = self.backup_dir / f"{backup_id}.tar.gz"
        with tarfile.open(backup_path, "w:gz") as tar:
            for file_path in files_to_backup:
                arcname = file_path.relative_to(self.project_root)
                tar.add(file_path, arcname=str(arcname))

        # Build info
        info = BackupInfo(
            id=backup_id,
            timestamp=timestamp,
            size_bytes=backup_path.stat().st_size,
            hash=content_hash,
            pinned=False,
            files=[str(f.relative_to(self.project_root)) for f in files_to_backup],
        )

        # Save to index
        self._add_to_index(info)

        # Auto-prune
        self._prune()

        return info

    def list_backups(self) -> list[BackupInfo]:
        """List all backups."""

        index = self._load_index()
        backups = []
        for item in index.get("backups", []):
            backups.append(
                BackupInfo(
                    id=item["id"],
                    timestamp=item["timestamp"],
                    size_bytes=item["size_bytes"],
                    hash=item["hash"],
                    pinned=item.get("pinned", False),
                    files=item.get("files", []),
                )
            )
        return backups

    def pin_backup(self, backup_id: str) -> bool:
        """Pin a backup to protect from pruning."""

        index = self._load_index()
        for item in index.get("backups", []):
            if item["id"] == backup_id:
                item["pinned"] = True
                self._save_index(index)
                return True
        return False

    def unpin_backup(self, backup_id: str) -> bool:
        """Unpin a backup."""

        index = self._load_index()
        for item in index.get("backups", []):
            if item["id"] == backup_id:
                item["pinned"] = False
                self._save_index(index)
                return True
        return False

    def restore_backup(self, backup_id: str, target: str | Path | None = None) -> dict[str, Any]:
        """Restore a backup.

        Args:
            backup_id: Backup to restore.
            target: Target directory. Defaults to project root.

        Returns:
            Restore report.
        """

        backup_path = self.backup_dir / f"{backup_id}.tar.gz"
        if not backup_path.exists():
            return {"status": "error", "message": f"Backup not found: {backup_id}"}

        target_dir = Path(target) if target else self.project_root
        target_dir.mkdir(parents=True, exist_ok=True)

        restored_files = []
        with tarfile.open(backup_path, "r:gz") as tar:
            for member in tar.getmembers():
                tar.extract(member, path=target_dir)
                restored_files.append(member.name)

        return {
            "status": "restored",
            "backup_id": backup_id,
            "target": str(target_dir),
            "files_restored": len(restored_files),
        }

    def delete_backup(self, backup_id: str) -> bool:
        """Delete a backup."""

        backup_path = self.backup_dir / f"{backup_id}.tar.gz"
        if backup_path.exists():
            backup_path.unlink()

        index = self._load_index()
        index["backups"] = [b for b in index.get("backups", []) if b["id"] != backup_id]
        self._save_index(index)
        return True

    def _default_paths(self) -> list[str]:
        """Default paths to backup."""

        return [
            "opencontext.yaml",
            ".opencontext/config.yaml",
            ".opencontext/agents/**",
            ".cursor/rules/**",
            ".claude/CLAUDE.md",
            ".claude/mcp.json",
            ".config/opencode/**",
        ]

    def _compute_hash(self, files: list[Path]) -> str:
        """Compute hash of file contents for deduplication."""

        hasher = hashlib.sha256()
        for file_path in sorted(files):
            hasher.update(file_path.read_bytes())
        return hasher.hexdigest()[:16]

    def _find_by_hash(self, content_hash: str) -> BackupInfo | None:
        """Find existing backup with same hash."""

        for backup in self.list_backups():
            if backup.hash == content_hash:
                return backup
        return None

    def _load_index(self) -> dict[str, Any]:
        """Load backup index."""

        if self.index_path.exists():
            try:
                return json.loads(self.index_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"backups": []}

    def _save_index(self, index: dict[str, Any]) -> None:
        """Save backup index."""

        self.index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")

    def _add_to_index(self, info: BackupInfo) -> None:
        """Add backup to index."""

        index = self._load_index()
        index["backups"].append(
            {
                "id": info.id,
                "timestamp": info.timestamp,
                "size_bytes": info.size_bytes,
                "hash": info.hash,
                "pinned": info.pinned,
                "files": info.files,
            }
        )
        self._save_index(index)

    def _prune(self) -> None:
        """Remove old backups, keeping MAX_BACKUPS unpinned."""

        backups = self.list_backups()
        unpinned = [b for b in backups if not b.pinned]

        # Sort by timestamp (newest first)
        unpinned.sort(key=lambda b: b.timestamp, reverse=True)

        # Remove excess unpinned backups
        to_remove = unpinned[self.MAX_BACKUPS :]
        for backup in to_remove:
            self.delete_backup(backup.id)
