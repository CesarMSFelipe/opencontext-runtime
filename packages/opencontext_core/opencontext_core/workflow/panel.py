"""Pure renderers for TUI cockpit panels that derive from ``WorkflowState``.

These helpers are intentionally dependency-free (no Textual) so the
panel logic can be unit-tested without pulling in the textual stack.
The cockpit screen imports them lazily at refresh time.
"""

from __future__ import annotations

from opencontext_core.workflow.state import WorkflowState

DIM = "dim"
PRIMARY = "primary"
WARNING = "warning"


def render_workflow_panel(workflow: WorkflowState) -> str:
    """Render the workflow-state panel for the cockpit screen.

    Pure function — same input always produces the same output. Reads
    ONLY from ``WorkflowState``; holds no independent state.
    """
    current = workflow.current_phase or "idle"
    gate_blocked = workflow.gate.blocked
    gate_reason = workflow.gate.reason or ""
    blocked_marker = "BLOCKED" if gate_blocked else "ok"
    lines = [
        f"[{PRIMARY}]Workflow Phase[/]: {current}",
        f"[{WARNING}]Gate[/]: {blocked_marker}" + (f" — {gate_reason}" if gate_reason else ""),
    ]
    return "\n".join(lines)


__all__ = ["render_workflow_panel"]
