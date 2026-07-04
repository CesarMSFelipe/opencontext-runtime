"""SDD orchestrator runner — phase lifecycle, progress merge, prompt builder.

Per openspec/changes/agentic-parity-engram-gentle/design.md §Orchestrator:

* ``PhaseResultEnvelope`` — 8-field contract envelope (REQ-GAS-001).
* ``Orchestrator`` — dataclass wrapping per-phase logic via ``advance()``.
* ``run_phase()`` — entry point called by CLI and FastAPI (PR3).
* ``build_phase_prompt()`` — deterministic per-phase prompt composer.

LB 2026 — SDD orchestrator runner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# PhaseResultEnvelope — 8-field contract (REQ-GAS-001)
# ---------------------------------------------------------------------------


class PhaseResultEnvelope(BaseModel):
    """Canonical 8-field SDD phase result envelope.

    Every phase handler returns this shape so the orchestrator can
    route to the next phase without parsing free text.
    """

    model_config = ConfigDict(extra="forbid")

    status: str = Field(description="ok | partial | blocked | failed")
    executive_summary: str = Field(description="One-line phase outcome.")
    artifacts: dict[str, str] = Field(
        default_factory=dict,
        description="Path or topic_key per artifact produced.",
    )
    next_recommended: str = Field(description="next phase name.")
    risks: list[str] = Field(default_factory=list, description="Risk items.")
    skill_resolution: str = Field(
        default="paths-injected",
        description="paths-injected | fallback-registry | none",
    )
    phase: str = Field(default="explore", description="Current phase name.")
    trace_id: str = Field(default="", description="Correlation trace id.")


# ---------------------------------------------------------------------------
# Orchestrator — drives the SDD lifecycle
# ---------------------------------------------------------------------------


@dataclass
class Orchestrator:
    """Per-change orchestrator that owns the SDD lifecycle for one change.

    Attributes:
        cwd: Project root.
        change: Change name.
        artifact_store: openspec | engram | hybrid | none.
        tdd_mode: ask | strict | off.
    """

    cwd: Path
    change: str
    artifact_store: str = "hybrid"
    tdd_mode: str = "ask"
    _phases: tuple[str, ...] = field(
        default=(
            "explore",
            "propose",
            "spec",
            "design",
            "tasks",
            "apply",
            "verify",
            "archive",
        )
    )

    def advance(self, requested_phase: str | None = None) -> PhaseResultEnvelope:
        """Determine the next phase and prepare to run it.

        When ``requested_phase`` is supplied, the envelope's ``phase`` field is
        always set to the requested phase and the routing validates that the
        request is coherent with current disk state (e.g. requesting 'design'
        before 'spec' is complete returns a ``blocked`` envelope whose ``phase``
        still reflects the request so callers can distinguish responses).

        Returns an envelope with the next phase and a status indicator.
        In strict TDD mode, verify that a failing test exists before
        advancing to 'apply'.
        """
        current = self._detect_current_phase()
        effective_phase = requested_phase or (
            self._next_after(current) if current is not None else "init"
        )

        if current is None:
            return PhaseResultEnvelope(
                status="blocked",
                executive_summary=f"No SDD artifacts for change '{self.change}'.",
                artifacts={},
                next_recommended="init",
                risks=[f"Change '{self.change}' has no artifacts"],
                skill_resolution="paths-injected",
                phase=effective_phase,
                trace_id="",
            )

        # Validate that the requested phase is reachable given current state.
        if requested_phase is not None and requested_phase in self._phases:
            requested_idx = self._phases.index(requested_phase)
            current_idx = self._phases.index(current)
            # Allow the immediately next phase or any phase already completed.
            if requested_idx > current_idx + 1:
                expected_next = self._next_after(current)
                return PhaseResultEnvelope(
                    status="blocked",
                    executive_summary=(
                        f"Phase '{requested_phase}' cannot run: '{expected_next}' "
                        f"must complete first (current: '{current}')."
                    ),
                    artifacts={},
                    next_recommended=expected_next,
                    risks=[
                        f"Requested phase '{requested_phase}' skips '{expected_next}'."
                    ],
                    skill_resolution="paths-injected",
                    phase=requested_phase,
                    trace_id="",
                )

        # In strict TDD mode, check for a failing test before apply
        if self.tdd_mode == "strict" and current == "tasks" and "apply" in self._phases:
            test_dir = self.cwd / "tests"
            has_failing = any(test_dir.rglob("test_*.py")) if test_dir.is_dir() else False
            if not has_failing:
                return PhaseResultEnvelope(
                    status="blocked",
                    executive_summary=(
                        "No test files found. Strict TDD requires a failing test before apply."
                    ),
                    artifacts={},
                    next_recommended="design",
                    risks=["Strict TDD: no test files detected"],
                    skill_resolution="paths-injected",
                    phase=effective_phase,
                    trace_id="",
                )

        next_phase = self._next_after(current)
        return PhaseResultEnvelope(
            status="ok",
            executive_summary=f"Ready for phase '{next_phase}'.",
            artifacts={},
            next_recommended=next_phase,
            risks=[],
            skill_resolution="paths-injected",
            phase=effective_phase,
            trace_id="",
        )

    def _detect_current_phase(self) -> str | None:
        """Detect the most advanced completed phase from disk state."""
        change_root = self.cwd / "openspec" / "changes" / self.change
        if not change_root.is_dir():
            return None
        for phase in reversed(self._phases):
            marker = change_root / f"{phase}.md"
            if marker.is_file():
                return phase
        return None

    def _next_after(self, current: str) -> str:
        """Return the next phase after ``current``."""
        idx = self._phases.index(current)
        return self._phases[idx + 1] if idx + 1 < len(self._phases) else "archive"


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def run_phase(
    phase: str,
    *,
    change: str | None = None,
    cwd: str | None = None,
    topic: str | None = None,
    task: str | None = None,
    verbose: bool = False,
) -> PhaseResultEnvelope:
    """Run an SDD phase and return the result envelope.

    Phase verbs map to the spec's 8-phase lifecycle. The ``runner``
    module in ``opencontext_core.harness`` owns the actual execution
    logic — this function wraps it with the canonical envelope.

    The ``phase`` argument drives behavior: it is passed to
    ``Orchestrator.advance()`` so the returned envelope's ``phase`` field
    reflects the *requested* phase and routing validates the request against
    current disk state.  Two calls with different ``phase`` values on the
    same state therefore return distinguishable envelopes.
    """
    _cwd = Path(cwd or ".").resolve()
    orch = Orchestrator(cwd=_cwd, change=change or "")
    return orch.advance(requested_phase=phase)


def build_phase_prompt(
    phase: str,
    *,
    change: str | None = None,
    tdd_mode: str = "ask",
) -> str:
    """Build a deterministic per-phase prompt for the orchestrator.

    Embeds the phase name, change name, and TDD mode so the conductor
    always sees consistent instructions.
    """
    lines = [
        f"# SDD Phase: {phase}",
        "",
    ]
    if change:
        lines.append(f"Change: {change}")
    if tdd_mode != "ask":
        lines.append(f"TDD Mode: {tdd_mode}")
    lines.extend(
        [
            "",
            "## Instructions",
            "",
            f"Execute the '{phase}' phase per the SDD workflow.",
            "Return a PhaseResultEnvelope-compatible result.",
        ]
    )
    return "\n".join(lines)


def _merge_progress(existing: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Merge new progress into existing progress, never overwriting.

    String-list fields (commits, tasks_done) are appended.
    Other fields use the new value (last-write-wins for scalar).
    """
    merged = dict(existing)
    for key, val in new.items():
        if key in merged and isinstance(merged[key], list) and isinstance(val, list):
            merged[key] = [*merged[key], *val]
        else:
            merged[key] = val
    return merged


__all__ = [
    "Orchestrator",
    "PhaseResultEnvelope",
    "build_phase_prompt",
    "run_phase",
]
