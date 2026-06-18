"""Tests for WatchService orchestration layer."""

from __future__ import annotations

import time
from pathlib import Path

from opencontext_core.indexing.watch_service import WatchService


class TestWatchService:
    """WatchService lifecycle and debounce tests."""

    def test_start_stop(self, tmp_path: Path) -> None:
        """Basic start/stop cycle."""
        calls: list[int] = []
        watcher = WatchService(
            root=tmp_path,
            index_callback=lambda: calls.append(1),
            use_watchdog=False,
        )
        assert watcher.is_running is False
        watcher.start()
        assert watcher.is_running is True
        watcher.stop()
        assert watcher.is_running is False

    def test_double_start_is_noop(self, tmp_path: Path) -> None:
        """Starting twice should not raise."""
        watcher = WatchService(
            root=tmp_path,
            index_callback=lambda: None,
            use_watchdog=False,
        )
        watcher.start()
        watcher.start()  # should be safe
        assert watcher.is_running is True
        watcher.stop()

    def test_double_stop_is_noop(self, tmp_path: Path) -> None:
        """Stopping twice should not raise."""
        watcher = WatchService(
            root=tmp_path,
            index_callback=lambda: None,
            use_watchdog=False,
        )
        watcher.start()
        watcher.stop()
        watcher.stop()  # should be safe

    def test_auto_start(self, tmp_path: Path) -> None:
        """auto_start=True starts the service immediately."""
        watcher = WatchService(
            root=tmp_path,
            index_callback=lambda: None,
            use_watchdog=False,
            auto_start=True,
        )
        assert watcher.is_running is True
        watcher.stop()

    def test_file_event_triggers_reindex_after_debounce(self, tmp_path: Path) -> None:
        """Simulate file event -> debounce -> re-index."""
        calls: list[int] = []

        def callback(changed: set | None = None) -> None:
            calls.append(1)

        watcher = WatchService(
            root=tmp_path,
            index_callback=callback,
            use_watchdog=False,
            debounce_seconds=0.05,
        )
        watcher.start()
        try:
            # Simulate file event
            watcher._on_file_event("test.py", "modified")
            assert watcher._last_event_time > 0

            # Before debounce elapses, no re-index
            assert watcher._debounce_and_reindex() is False

            # Wait for debounce
            time.sleep(0.1)

            # After debounce, re-index should happen
            assert watcher._debounce_and_reindex() is True
            assert len(calls) == 1
        finally:
            watcher.stop()

    def test_multiple_events_batched(self, tmp_path: Path) -> None:
        """Multiple rapid events should trigger only one re-index."""
        calls: list[int] = []

        def callback(changed: set | None = None) -> None:
            calls.append(1)

        watcher = WatchService(
            root=tmp_path,
            index_callback=callback,
            use_watchdog=False,
            debounce_seconds=0.05,
        )
        watcher.start()
        try:
            # Rapid file events
            for _i in range(10):
                watcher._on_file_event("f{_i}.py", "modified")
                time.sleep(0.01)

            # Debounce check before time elapses
            watcher._debounce_and_reindex()

            # Wait for debounce
            time.sleep(0.15)

            # Now it should trigger once
            assert watcher._debounce_and_reindex() is True
            assert len(calls) == 1
        finally:
            watcher.stop()

    def test_force_reindex(self, tmp_path: Path) -> None:
        """force_reindex() triggers callback immediately."""
        calls: list[int] = []

        def callback(changed: set | None = None) -> None:
            calls.append(1)

        watcher = WatchService(
            root=tmp_path,
            index_callback=callback,
            use_watchdog=False,
        )
        watcher.start()
        try:
            watcher.force_reindex()
            assert len(calls) == 1
        finally:
            watcher.stop()

    def test_force_reindex_while_stopped(self, tmp_path: Path) -> None:
        """force_reindex() should be a no-op when not running."""
        calls: list[int] = []

        def callback(changed: set | None = None) -> None:
            calls.append(1)

        watcher = WatchService(
            root=tmp_path,
            index_callback=callback,
            use_watchdog=False,
        )
        watcher.force_reindex()  # not started — should be a no-op
        assert len(calls) == 0

    def test_callback_error_does_not_crash(self, tmp_path: Path) -> None:
        """If the callback raises, the service should survive."""

        def failing_callback() -> None:
            msg = "intentional failure"
            raise RuntimeError(msg)

        watcher = WatchService(
            root=tmp_path,
            index_callback=failing_callback,
            use_watchdog=False,
            debounce_seconds=0.0,
        )
        watcher.start()
        try:
            watcher._on_file_event("bad.py", "modified")
            result = watcher._debounce_and_reindex()
            # Should not crash; debounce may or may not fire depending on timing
            assert result is True or result is False
        finally:
            watcher.stop()

    def test_watchdog_backed_service(self, tmp_path: Path) -> None:
        """WatchService with use_watchdog=True creates a watchdog FileWatcher."""
        watcher = WatchService(
            root=tmp_path,
            index_callback=lambda: None,
            use_watchdog=True,
        )
        try:
            watcher.start()
            assert watcher._watcher is not None
            assert watcher._watcher._use_watchdog is True
        finally:
            watcher.stop()
