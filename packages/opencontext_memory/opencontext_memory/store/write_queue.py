"""WriteQueue — per-process + cross-process advisory lock for memory writes.

The queue is a context manager. Concurrent writers in the **same process**
serialise through a per-instance :class:`threading.Lock` so an inner SQLite
write can never interleave with itself. Writers across **processes** acquire
the matching ``fcntl.flock`` advisory lock on POSIX or the ``os.O_EXCL``
lockfile on Windows — same pattern as ``opencontext_core/memory/stores.py``
(PR1 already uses it for ``project_manifest.json``; reusing the shape keeps
ops behaviour identical).

The class is constructed lazily: ``lock_path`` is created with ``mkdir -p``
the first time the queue is entered, then ``flock`` (or ``os.O_EXCL``) is
acquired on the lockfile. Cleanup removes the 0-byte lockfile so the repo
is not littered with stale lockfiles after every successful write batch.
"""

from __future__ import annotations

import contextlib
import os
import threading
import time
from collections.abc import Generator
from pathlib import Path


class WriteQueue:
    """Context-managed advisory lock for store writes.

    Parameters
    ----------
    lock_path:
        Filesystem path the cross-process lockfile will live at. The file is
        created on first entry and removed on exit. Parent directories are
        ``mkdir -p``'d.
    timeout_seconds:
        Maximum time a cross-process acquisition may wait before giving up.
        Defaults to 30 s, matching ``opencontext_core/memory/stores.py``.
    """

    def __init__(self, lock_path: Path, *, timeout_seconds: float = 30.0) -> None:
        self._lock_path = Path(lock_path)
        self._timeout = timeout_seconds
        self._inproc = threading.Lock()
        self._cross_fd: int | None = None

    @property
    def lock_path(self) -> Path:
        return self._lock_path

    def __enter__(self) -> WriteQueue:
        # Same-process first: cheap, immediate, no syscall.
        self._inproc.acquire()
        # Cross-process second: POSIX flock or Windows O_EXCL spin.
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            import fcntl  # POSIX only — Windows hits ImportError below.

            fh = open(self._lock_path, "w", encoding="utf-8")
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            except Exception:
                fh.close()
                raise
            # Keep the handle alive for the lifetime of the lock; close on exit.
            self._cross_fd = fh.fileno()
            self._cross_handle = fh
        except ImportError:
            # Windows fallback: spin on a 0-byte lockfile using O_CREAT|O_EXCL.
            deadline = time.monotonic() + self._timeout
            while True:
                try:
                    self._cross_fd = os.open(
                        str(self._lock_path),
                        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    )
                    break
                except FileExistsError:
                    if time.monotonic() > deadline:
                        break
                    time.sleep(0.05)
        return self

    def __exit__(self, *_: object) -> None:
        try:
            try:
                import fcntl  # POSIX-only — Windows hits ImportError below.

                if getattr(self, "_cross_handle", None) is not None:
                    fcntl.flock(self._cross_fd or -1, fcntl.LOCK_UN)
                    self._cross_handle.close()
            except ImportError:
                if self._cross_fd is not None:
                    with contextlib.suppress(OSError):
                        os.close(self._cross_fd)
            finally:
                self._cross_fd = None
                if hasattr(self, "_cross_handle"):
                    self._cross_handle = None  # type: ignore[assignment]
            with contextlib.suppress(OSError):
                self._lock_path.unlink()
        finally:
            self._inproc.release()


@contextlib.contextmanager
def write_queue(lock_path: Path) -> Generator[WriteQueue, None, None]:
    """Functional helper mirroring ``opencontext_core/memory/stores.py``."""
    queue = WriteQueue(lock_path)
    with queue:
        yield queue
