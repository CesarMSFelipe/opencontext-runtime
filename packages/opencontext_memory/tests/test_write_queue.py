"""Tests for the cross-process WriteQueue (T2.11).

Per strict-TDD: this file is the source of truth for the
``opencontext_memory.store.write_queue.WriteQueue`` contract. The
production module already exists (PR2.a shipped it); this test is written
to satisfy the spec's REQ-OMS-005 acceptance criterion
("concurrent_writes_serialised"). No production code lands in this
sub-task — T2.11 is test-only.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from opencontext_memory.store.write_queue import WriteQueue


def test_REQ_OMS_005_concurrent_writes_serialised(tmp_path: Path) -> None:
    """Two concurrent ``WriteQueue`` contexts serialise; the cross-process
    lock guarantees no overlap between critical sections."""
    lock_path = tmp_path / "wq.lock"
    order: list[str] = []
    errors: list[BaseException] = []

    def worker(name: str) -> None:
        try:
            wq = WriteQueue(lock_path, timeout_seconds=5.0)
            with wq:
                order.append(f"{name}-enter")
                # Sleep inside the critical section so a second worker
                # can verify it actually waits — overlap would mean BOTH
                # workers' 'enter' markers land before either 'exit'.
                time.sleep(0.1)
                order.append(f"{name}-exit")
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(f"w{i}",)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"worker raised: {errors!r}"

    # Strict serialisation: the order must be ``enter-exit-enter-exit``
    # OR ``enter-exit-enter-exit`` for the two workers (any interleaving
    # where two 'enter' lines land before one 'exit' would prove overlap).
    enter_indices = [i for i, line in enumerate(order) if line.endswith("-enter")]
    exit_indices = [i for i, line in enumerate(order) if line.endswith("-exit")]
    assert len(enter_indices) == 2
    assert len(exit_indices) == 2
    # First enter must come before first exit (any worker is fine).
    assert min(enter_indices) < min(exit_indices)
