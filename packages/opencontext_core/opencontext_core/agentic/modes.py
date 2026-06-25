"""Pure mode-query functions for the agentic flow.

All three functions are deterministic and side-effect-free. They read from
FlowMode values only; no state is mutated or stored.
"""

from __future__ import annotations

from opencontext_core.agentic.config import FlowMode

# NOTE: Phases that HYBRID mode pauses at in addition to "approval".
_HYBRID_PAUSE_PHASES = frozenset({"spec", "design", "tasks", "approval", "verify", "review"})

# NOTE: Modes that disable all code execution.
_NO_EXECUTE_MODES = frozenset({FlowMode.ENGRAM_ONLY, FlowMode.OPENSPEC_ONLY, FlowMode.OBSERVE_ONLY})

# NOTE: Modes that disable writing OpenSpec artifacts.
_NO_OPENSPEC_MODES = frozenset({FlowMode.ENGRAM_ONLY, FlowMode.OBSERVE_ONLY})


def should_pause_after_phase(mode: FlowMode, phase: str) -> bool:
    """Return True if the conductor should pause for human input after *phase*.

    - AUTOMATIC: never pause (run all phases autonomously).
    - STEPWISE: always pause after every phase.
    - HYBRID: pause at spec/design/tasks/approval/verify/review.
    - ENGRAM_ONLY / OPENSPEC_ONLY / OBSERVE_ONLY: always pause.
    """
    if mode == FlowMode.AUTOMATIC:
        return False
    if mode == FlowMode.STEPWISE:
        return True
    if mode == FlowMode.HYBRID:
        return phase in _HYBRID_PAUSE_PHASES
    # ENGRAM_ONLY, OPENSPEC_ONLY, OBSERVE_ONLY
    return True


def should_execute_code(mode: FlowMode) -> bool:
    """Return True if the conductor is allowed to execute code (apply phase writes).

    ENGRAM_ONLY, OPENSPEC_ONLY, and OBSERVE_ONLY are read/observe modes only.
    """
    return mode not in _NO_EXECUTE_MODES


def should_write_openspec(mode: FlowMode) -> bool:
    """Return True if the conductor should persist artifacts to OpenSpec files.

    ENGRAM_ONLY and OBSERVE_ONLY suppress all OpenSpec writes.
    """
    return mode not in _NO_OPENSPEC_MODES


if __name__ == "__main__":
    assert not should_pause_after_phase(FlowMode.AUTOMATIC, "spec")
    assert not should_pause_after_phase(FlowMode.AUTOMATIC, "explore")
    assert should_pause_after_phase(FlowMode.STEPWISE, "explore")
    assert should_pause_after_phase(FlowMode.STEPWISE, "archive")
    assert should_pause_after_phase(FlowMode.HYBRID, "spec")
    assert not should_pause_after_phase(FlowMode.HYBRID, "explore")
    assert not should_execute_code(FlowMode.OBSERVE_ONLY)
    assert not should_execute_code(FlowMode.ENGRAM_ONLY)
    assert should_execute_code(FlowMode.AUTOMATIC)
    assert should_write_openspec(FlowMode.OPENSPEC_ONLY)
    assert not should_write_openspec(FlowMode.ENGRAM_ONLY)
    assert not should_write_openspec(FlowMode.OBSERVE_ONLY)
    print("agentic/modes.py self-check passed.")
