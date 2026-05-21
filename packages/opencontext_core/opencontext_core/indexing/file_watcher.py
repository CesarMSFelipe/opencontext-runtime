"""File watcher for auto-syncing the knowledge graph on file changes.

Uses a polling-based fallback approach since inotify/FSEvents
require platform-specific dependencies. For production use,
consider integrating with watchdog (a Python package).
"""

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any


class FileWatcher:
    """Watch files for changes and trigger callbacks.

    Uses a polling-based approach with debouncing. For production
    deployments, integrate with the `watchdog` package for OS-level
    file events.
    """

    def __init__(
        self,
        root: str | Path,
        callback: Callable[[str, str], None],
        debounce_seconds: float = 2.0,
        poll_interval: float = 1.0,
        exclude_patterns: list[str] | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.callback = callback
        self.debounce_seconds = debounce_seconds
        self.poll_interval = poll_interval
        self.exclude_patterns = exclude_patterns or []
        self._file_states: dict[str, tuple[int, str]] = {}
        self._pending: dict[str, float] = {}
        self._running = False

    def start(self) -> None:
        """Start watching files."""

        self._running = True
        self._scan_all()

        # In a real implementation, this would spawn a background thread
        # or use watchdog's Observer. For now, we provide a scan method
        # that can be called periodically.

    def stop(self) -> None:
        """Stop watching files."""

        self._running = False

    def scan(self) -> list[tuple[str, str]]:
        """Scan for changes and return pending callbacks.

        Returns:
            List of (file_path, event_type) tuples where event_type
            is "modified", "created", or "deleted".
        """

        if not self._running:
            return []

        events: list[tuple[str, str]] = []
        now = time.time()

        # Check for modified/created files
        current_files: set[str] = set()
        for file_path in self._iter_files():
            rel_path = str(file_path.relative_to(self.root))
            current_files.add(rel_path)

            mtime = file_path.stat().st_mtime
            content_hash = self._hash_file(file_path)

            if rel_path in self._file_states:
                _old_mtime, old_hash = self._file_states[rel_path]
                if old_hash != content_hash:
                    # File changed
                    self._pending[rel_path] = now
                    self._file_states[rel_path] = (mtime, content_hash)
            else:
                # New file
                self._pending[rel_path] = now
                self._file_states[rel_path] = (mtime, content_hash)

        # Check for deleted files
        for rel_path in list(self._file_states):
            if rel_path not in current_files:
                events.append((rel_path, "deleted"))
                del self._file_states[rel_path]
                if rel_path in self._pending:
                    del self._pending[rel_path]

        # Process debounced events
        for rel_path, timestamp in list(self._pending.items()):
            if now - timestamp >= self.debounce_seconds:
                events.append((rel_path, "modified"))
                del self._pending[rel_path]
                self.callback(rel_path, "modified")

        return events

    def _iter_files(self) -> Any:
        """Iterate over files in the watched directory."""

        if not self.root.exists():
            return

        for dirpath, _dirnames, filenames in os.walk(self.root):
            for filename in filenames:
                file_path = Path(dirpath) / filename
                rel_path = str(file_path.relative_to(self.root))

                # Skip excluded patterns
                skip = False
                for pattern in self.exclude_patterns:
                    if self._match_pattern(rel_path, pattern):
                        skip = True
                        break
                if skip:
                    continue

                yield file_path

    def _scan_all(self) -> None:
        """Initial scan to populate file states."""

        for file_path in self._iter_files():
            rel_path = str(file_path.relative_to(self.root))
            mtime = file_path.stat().st_mtime
            content_hash = self._hash_file(file_path)
            self._file_states[rel_path] = (mtime, content_hash)

    @staticmethod
    def _hash_file(file_path: Path) -> str:
        """Compute MD5 hash of file content."""

        try:
            with open(file_path, "rb") as f:
                return hashlib.md5(f.read()).hexdigest()
        except OSError:
            return ""

    @staticmethod
    def _match_pattern(file_path: str, pattern: str) -> bool:
        """Match a file path against a glob pattern."""

        import fnmatch

        if fnmatch.fnmatch(file_path, pattern):
            return True
        if pattern.endswith("/**"):
            prefix = pattern[:-3]
            if file_path.startswith(prefix + "/") or file_path == prefix:
                return True
        return False
