"""CoordinatorPolicy — main-thread guard for coordination decisions.

The conductor's coordination logic (gate evaluation, approval routing) mutates
WorkflowState. Concurrent mutation from worker threads corrupts state, so the
policy rejects any call from a thread whose ident is not the main thread's.
"""

from __future__ import annotations

import threading

import pytest

from opencontext_core.workflow.coordinator_policy import CoordinatorPolicy


def test_assert_allowed_passes_on_main_thread() -> None:
    """Calling from the main thread (the conductor's thread) must not raise."""
    policy = CoordinatorPolicy()
    policy.assert_allowed(threading.main_thread().ident)  # type: ignore[arg-type]
    policy.assert_allowed(threading.get_ident())


def test_assert_allowed_raises_from_non_main_thread() -> None:
    """A worker thread invoking the guard receives RuntimeError naming the constraint."""
    policy = CoordinatorPolicy()
    captured: list[BaseException] = []

    def worker() -> None:
        try:
            policy.assert_allowed(threading.get_ident())
        except RuntimeError as exc:
            captured.append(exc)

    t = threading.Thread(target=worker, name="worker-not-main")
    t.start()
    t.join(timeout=2.0)
    assert not t.is_alive(), "worker thread hung"

    assert len(captured) == 1, "expected exactly one RuntimeError from worker"
    msg = str(captured[0]).lower()
    assert "thread" in msg, f"error must mention thread constraint, got: {captured[0]}"


def test_assert_allowed_distinguishes_main_from_worker_id() -> None:
    """Triangulation: passing the main thread's id succeeds; a fake id fails."""
    policy = CoordinatorPolicy()
    main_id = threading.main_thread().ident  # type: ignore[assignment]
    fake_id = main_id + 10_000_000
    assert fake_id != main_id

    policy.assert_allowed(main_id)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError):
        policy.assert_allowed(fake_id)  # type: ignore[arg-type]
