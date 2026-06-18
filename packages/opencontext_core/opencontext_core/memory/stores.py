"""Project memory store abstractions and local JSON implementation."""

from __future__ import annotations

import contextlib
import os
from collections.abc import Generator
from pathlib import Path
from typing import Protocol

from opencontext_core.errors import MemoryStoreError
from opencontext_core.models.project import ProjectManifest
from opencontext_core.safety.redaction import SinkGuard


@contextlib.contextmanager
def _manifest_write_lock(lock_path: Path) -> Generator[None, None, None]:
    """Cross-process write lock for the project manifest JSON.

    Uses fcntl on POSIX and a lockfile fallback on Windows.
    Read operations do not need the lock (reads are atomic for JSON files
    this size and WAL handles the SQLite side).
    """
    lock_file = lock_path.with_suffix(".lock")
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        import fcntl

        with open(lock_file, "w") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)
    except ImportError:
        # Windows fallback: busy-wait on a lockfile (good enough for CLI use)
        import time

        deadline = time.monotonic() + 30
        while True:
            try:
                fd = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                break
            except FileExistsError:
                if time.monotonic() > deadline:
                    break  # give up rather than hang forever
                time.sleep(0.1)
        try:
            yield
        finally:
            with contextlib.suppress(OSError):
                lock_file.unlink()


class ProjectMemoryStore(Protocol):
    """Storage interface for project manifests."""

    def save_manifest(self, manifest: ProjectManifest) -> Path:
        """Persist a project manifest and return the storage path."""

    def load_manifest(self) -> ProjectManifest:
        """Load the latest project manifest."""


class LocalProjectMemoryStore:
    """Local JSON-backed project memory store."""

    def __init__(self, base_path: Path | str = ".storage/opencontext") -> None:
        self.base_path = Path(base_path)
        self.manifest_path = self.base_path / "project_manifest.json"

    def save_manifest(self, manifest: ProjectManifest) -> Path:
        """Persist a project manifest as JSON."""

        guard = SinkGuard()
        sanitized_files = []
        for file in manifest.files:
            summary, redacted = guard.redact(file.summary)
            metadata = dict(file.metadata)
            if redacted:
                metadata["summary_redacted"] = True
            sanitized_files.append(
                file.model_copy(update={"summary": summary, "metadata": metadata})
            )
        sanitized_manifest = manifest.model_copy(update={"files": sanitized_files})
        self.base_path.mkdir(parents=True, exist_ok=True)
        with _manifest_write_lock(self.manifest_path):
            self.manifest_path.write_text(
                sanitized_manifest.model_dump_json(indent=2),
                encoding="utf-8",
            )
        return self.manifest_path

    def load_manifest(self) -> ProjectManifest:
        """Load a project manifest from JSON."""

        if not self.manifest_path.exists():
            raise MemoryStoreError(
                f"Project manifest not found at {self.manifest_path}. "
                "Run `opencontext index .` first."
            )
        try:
            return ProjectManifest.model_validate_json(
                self.manifest_path.read_text(encoding="utf-8")
            )
        except Exception as exc:
            raise MemoryStoreError(f"Could not load project manifest: {exc}") from exc


class NullProjectMemoryStore:
    """In-memory store useful for tests and custom embeddings."""

    def __init__(self) -> None:
        self.manifest: ProjectManifest | None = None

    def save_manifest(self, manifest: ProjectManifest) -> Path:
        """Store a manifest in memory."""

        self.manifest = manifest
        return Path("<memory>")

    def load_manifest(self) -> ProjectManifest:
        """Load an in-memory manifest."""

        if self.manifest is None:
            raise MemoryStoreError("No in-memory project manifest has been stored.")
        return self.manifest
