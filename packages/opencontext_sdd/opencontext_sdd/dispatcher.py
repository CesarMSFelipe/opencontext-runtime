"""Dispatcher markdown + native phase prompt (REQ-OSS-004/005, REQ-GAS-005).

Pure functions — no I/O, no LLM. Deterministic: same inputs → same output.
"""

from __future__ import annotations

from opencontext_sdd.status import Status

# Map ``Status.nextRecommended`` to the artifact path the host should write
# next. Kept inline (vs in Status) because the mapping is a dispatcher
# concern, not a Status concern.
_NEXT_ARTIFACT: dict[str, str] = {
    "propose": "openspec/changes/<change>/proposal.md",
    "spec": "openspec/changes/<change>/specs/<cap>/spec.md",
    "design": "openspec/changes/<change>/design.md",
    "tasks": "openspec/changes/<change>/tasks.md",
    "apply": "(continue apply-phase; write or update code + tests)",
    "verify": "openspec/changes/<change>/verify-report.md",
    "archive": "openspec/changes/<change>/archive.md",
}


def RenderDispatcherMarkdown(status: Status) -> str:
    """Render a markdown block the host agent can paste verbatim.

    Includes change name, current ``nextRecommended``, ``blockedReasons``,
    and a pointer to the next artifact to write.
    """
    change = status.changeName or "<unset>"
    lines: list[str] = []
    lines.append(f"Change: {change}")
    lines.append("")
    lines.append(f"Next: {status.nextRecommended}")
    next_artifact = _NEXT_ARTIFACT.get(status.nextRecommended, "(none)")
    if change != "<unset>":
        next_artifact = next_artifact.replace("<change>", change)
    lines.append(f"Next artifact: `{next_artifact}`")
    lines.append(f"Apply state: `{status.applyState}`")
    if status.artifactStore:
        lines.append(f"Artifact store: `{status.artifactStore}`")
    if status.blockedReasons:
        lines.append("")
        lines.append("Blocked:")
        for reason in status.blockedReasons:
            lines.append(f"- {reason}")
    else:
        lines.append("")
        lines.append("Blocked: _(none)_")
    lines.append("")
    return "\n".join(lines)


_TDD_STRICT_RULE = "tdd-strict: write the closest failing test first"
_VALID_PHASES = (
    "explore",
    "propose",
    "spec",
    "design",
    "tasks",
    "apply",
    "verify",
    "review",
    "archive",
)


def RenderNativePhasePrompt(
    phase: str,
    *,
    change: str | None = None,
    trace_id: str | None = None,
    tdd_mode: str = "ask",
) -> str:
    """Return a deterministic per-phase prompt the conductor uses verbatim.

    Embeds ``trace_id=<id>``, ``phase=<p>``, and (when ``tdd_mode='strict'``)
    the test-first rule string. The output is stable for a given input tuple
    (REQ-GAS-005 invariant).
    """
    if phase not in _VALID_PHASES:
        # Still emit, but normalise via a fallback to keep determinism.
        phase = phase.lower()
    parts: list[str] = [
        f"phase={phase}",
    ]
    if change is not None:
        parts.append(f"change={change}")
    if trace_id is not None:
        parts.append(f"trace_id={trace_id}")
    if tdd_mode == "strict":
        parts.append(_TDD_STRICT_RULE)
    header = " ".join(parts)
    body = _PHASE_BODY.get(phase, _PHASE_BODY_DEFAULT)
    return f"{header}\n\n{body}"


_PHASE_BODY_DEFAULT = (
    "Follow the SDD orchestrator contract: read the Status JSON, "
    "act on the current phase, and persist any progress before yielding."
)


_PHASE_BODY: dict[str, str] = {
    "explore": (
        "Clarify the user's intent. Surface ambiguity; do not commit to a change yet. "
        "Do NOT mutate disk state."
    ),
    "propose": (
        "Write `proposal.md` for the chosen change. Capture intent, scope, "
        "non-goals, and the rough shape of the next 3-5 phases."
    ),
    "spec": (
        "Write per-capability `specs/<cap>/spec.md` files. Use EARS-form "
        "requirements and BDD scenarios. No implementation, no design."
    ),
    "design": (
        "Write `design.md` with architecture, module map, data model, and "
        "interfaces. Reference the spec REQ-IDs you are satisfying."
    ),
    "tasks": (
        "Decompose the design into ordered, file-level tasks in `tasks.md`. "
        "Each task is one PR. Group by sub-PR for chained-PR execution."
    ),
    "apply": (
        "Execute the tasks in `tasks.md`. Per task: read the spec scenario, "
        "match the design decision, write the code, mark `[x]` in tasks.md. "
        "Persist `apply-progress` to the topic key."
    ),
    "verify": (
        "Run the verification suite (pytest, ruff, mypy, coverage gate). "
        "Write `verify-report.md` with a `verdict: PASS|FAIL` line and a "
        "bullet list of any failures. Unicode marks (✅/❌/⚠️) are stripped by "
        "the parser before scoring."
    ),
    "review": (
        "Cross-review the change against the 25-point acceptance matrix. "
        "Surface drift between spec, design, and code."
    ),
    "archive": (
        "Sync delta specs and write `archive.md`. Once archived, the change "
        "becomes the new baseline."
    ),
}


__all__ = ["RenderDispatcherMarkdown", "RenderNativePhasePrompt"]
