"""CoordinatorPolicy — enforces main-thread isolation for coordination logic.

The conductor (OcNewConductor / WorkflowState) is single-threaded by design:
its gate evaluation and approval routing mutate shared state, so concurrent
worker writes would corrupt it. This policy is the *only* identifier check
the conductor needs — no locking, no orchestration, no IO. Worker threads
calling into the conductor surface a RuntimeError naming the constraint.

    if not CoordinatorPolicy().assert_allowed(threading.get_ident()):
        return  # unreachable; assert_allowed raises
"""

from __future__ import annotations

import threading


class CoordinatorPolicy:
    """Identifier-only main-thread guard."""

    def assert_allowed(self, thread_id: int) -> None:
        """Raise RuntimeError when called from any thread other than the main thread."""
        main_id = threading.main_thread().ident
        if thread_id != main_id:
            raise RuntimeError(
                "CoordinatorPolicy: coordination decisions must run on the "
                f"conductor main thread (ident={main_id}); got thread ident={thread_id}."
            )


__all__ = ["CoordinatorPolicy"]


if __name__ == "__main__":  # NOTE: tiny executable sanity check
    p = CoordinatorPolicy()
    p.assert_allowed(threading.get_ident())  # main thread ok
    try:
        p.assert_allowed(-1)
    except RuntimeError as exc:
        assert "thread" in str(exc).lower()
        print("workflow/coordinator_policy.py self-check passed.")
