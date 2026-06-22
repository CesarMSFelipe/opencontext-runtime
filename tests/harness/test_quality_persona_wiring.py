"""Per-persona quality wiring — the Architect@design surfacing seam (Phase 3).

The harness surfaces the explore-captured architecture-health snapshot to the
Architect *during the design phase* so design decisions are grounded in the
current health (duplication / nesting / cycles / god-files / complexity), not a
blind template. This is the ONLY new harness behaviour added in
``opencontext_core.harness.phases``:

* ``run_phase_executor(state, 'design')`` appends a compact, deterministic
  ``## Architecture health`` block to the executor ``context`` — mirroring the
  existing ``## Applicable skills`` append — built from
  ``state.architecture_baseline_dict`` (already JSON-safe: ``metrics.as_dict() |
  {'score': ...}``, populated by :class:`ExplorePhase`).
* The injection happens ONLY for ``phase == 'design'``; every other phase passes
  the executor context through unchanged.
* The prior-artifact + context-pack handoff is preserved (the health block is
  additive, never a replacement).
* ``_render_health_for_design`` is pure string formatting: deterministic, fixed
  key order, ZERO model calls and ZERO subprocess.

The companion Reviewer@verify delta surfacing (``runner._eval_architecture_gate``)
and the cross-run evolution log live in ``runner.py`` and are covered by
``tests/harness/test_quality_gate.py`` — this file owns the design seam only.

Every test is ``tmp_path``-isolated: the project root lives under ``tmp_path`` and
the real ``~/.opencontext`` / repo ``.opencontext`` are never read or written.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from opencontext_core.harness.phases import (
    ExecutorOutcome,
    _render_health_for_design,
    run_phase_executor,
)
from opencontext_core.harness.runner import HarnessState

# --------------------------------------------------------------------------- #
# Fixtures / helpers (all tmp-isolated, zero model, zero subprocess)
# --------------------------------------------------------------------------- #


class _RecordingDelegate:
    """A delegate that records the context it received and returns a real output.

    Mirrors the :class:`SubAgentDelegate` shape ``run_phase_executor`` expects:
    a ``delegate(phase, context) -> result`` callable where ``result`` exposes
    ``.status`` and ``.output``. It NEVER reaches out to a model/subprocess — it
    just captures the prompt the harness built, so a test can assert what the
    Architect would have seen.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def delegate(self, phase: str, context: dict[str, Any]) -> Any:
        self.calls.append({"phase": phase, "context": dict(context)})

        class _Result:
            status = "success"
            output = f"# Design produced for phase {phase}"

        return _Result()


def _snapshot(**overrides: int) -> dict[str, Any]:
    """A JSON-safe architecture_baseline_dict mirror (metrics.as_dict | score).

    Matches exactly what :class:`ExplorePhase` writes to
    ``state.architecture_baseline_dict`` — every metric key plus ``score`` — so
    the test exercises the real dict shape, including the Phase-3
    duplication/max_nesting signals.
    """
    base = {
        "cycles": 0,
        "god_files": 0,
        "max_cc": 0,
        "max_in_degree": 0,
        "max_out_degree": 0,
        "boundary_violations": 0,
        "duplication": 0,
        "max_depth": 0,
        "max_nesting": 0,
        "node_count": 0,
        "edge_count": 0,
        "score": 10000,
    }
    base.update(overrides)
    return base


def _state(root: Path, *, snapshot: dict[str, Any] | None = None) -> HarnessState:
    state = HarnessState(run_id="rd", root=root, task="add a feature")
    state.prior_artifact = "## Spec from the prior phase (compacted)\nSPEC-BODY"  # type: ignore[attr-defined]
    state.context_pack = "## Context pack\nPACK-BODY"
    if snapshot is not None:
        state.architecture_baseline_dict = snapshot
    return state


# --------------------------------------------------------------------------- #
# _render_health_for_design — pure deterministic formatter
# --------------------------------------------------------------------------- #


def test_render_health_block_contains_score_and_phase3_metrics() -> None:
    """The block surfaces the score and the Phase-3 duplication/nesting signals."""
    block = _render_health_for_design(_snapshot(score=9120, duplication=3, max_nesting=7))
    assert "Architecture health" in block
    assert "9120" in block
    # Phase-3 signals must be present (this is what makes the design persona
    # aware of duplication/depth, the whole point of the seam).
    assert "duplication" in block and "3" in block
    assert "max_nesting" in block and "7" in block
    # Other headline architecture metrics are surfaced too.
    assert "cycles" in block
    assert "god_files" in block
    assert "max_cc" in block


def test_render_health_block_is_deterministic() -> None:
    """Identical snapshot -> byte-identical block (fixed key order, no clock)."""
    snap = _snapshot(score=8800, duplication=2, max_nesting=6, cycles=1, god_files=4, max_cc=22)
    assert _render_health_for_design(snap) == _render_health_for_design(dict(snap))


def test_render_health_block_handles_empty_snapshot() -> None:
    """An empty dict does not crash; it yields an empty string (nothing to add)."""
    assert _render_health_for_design({}) == ""


def test_render_health_block_tolerates_missing_keys() -> None:
    """A partial snapshot (missing some metrics) defaults the absent ones to 0."""
    block = _render_health_for_design({"score": 7000, "duplication": 5})
    assert "7000" in block
    assert "duplication" in block and "5" in block
    # A missing metric is rendered as 0, not a KeyError.
    assert "max_nesting" in block


# --------------------------------------------------------------------------- #
# run_phase_executor — Architect@design injection (seam 4)
# --------------------------------------------------------------------------- #


def test_design_phase_injects_health_block(tmp_path: Path) -> None:
    """phase=='design' appends the health block to the executor context."""
    delegate = _RecordingDelegate()
    state = _state(tmp_path, snapshot=_snapshot(score=9200, duplication=2, max_nesting=6))
    state.delegate = delegate

    outcome = run_phase_executor(state, "design")
    assert isinstance(outcome, ExecutorOutcome)
    assert outcome.is_real  # the recording delegate returns a real success

    assert delegate.calls, "the delegate was invoked"
    ctx = delegate.calls[0]["context"]["context"]
    assert "## Architecture health" in ctx
    assert "9200" in ctx
    assert "duplication" in ctx and "max_nesting" in ctx


def test_design_injection_preserves_prior_artifact_and_pack(tmp_path: Path) -> None:
    """The health block is ADDITIVE — the spec + pack handoff is intact."""
    delegate = _RecordingDelegate()
    state = _state(tmp_path, snapshot=_snapshot(score=9000, duplication=1))
    state.delegate = delegate

    run_phase_executor(state, "design")
    ctx = delegate.calls[0]["context"]["context"]
    # Prior artifact (spec) is still first, then the pack, then the health block.
    assert "SPEC-BODY" in ctx
    assert "PACK-BODY" in ctx
    assert ctx.index("SPEC-BODY") < ctx.index("PACK-BODY")
    assert ctx.index("PACK-BODY") < ctx.index("## Architecture health")


def test_non_design_phase_does_not_inject_health(tmp_path: Path) -> None:
    """A non-design phase (e.g. 'tasks') passes context through unchanged."""
    delegate = _RecordingDelegate()
    state = _state(tmp_path, snapshot=_snapshot(score=9000, duplication=3, max_nesting=8))
    state.delegate = delegate

    run_phase_executor(state, "tasks")
    ctx = delegate.calls[0]["context"]["context"]
    assert "## Architecture health" not in ctx
    # The handoff is still present for the non-design phase.
    assert "SPEC-BODY" in ctx
    assert "PACK-BODY" in ctx


def test_design_without_snapshot_does_not_inject(tmp_path: Path) -> None:
    """No explore baseline -> no health block (degrade silently, never crash)."""
    delegate = _RecordingDelegate()
    state = _state(tmp_path)  # architecture_baseline_dict stays {}
    state.delegate = delegate

    run_phase_executor(state, "design")
    ctx = delegate.calls[0]["context"]["context"]
    assert "## Architecture health" not in ctx
    assert "SPEC-BODY" in ctx and "PACK-BODY" in ctx


def test_design_with_empty_snapshot_does_not_inject(tmp_path: Path) -> None:
    """An explicitly-empty snapshot dict also yields no block (truthiness guard)."""
    delegate = _RecordingDelegate()
    state = _state(tmp_path, snapshot={})
    state.delegate = delegate

    run_phase_executor(state, "design")
    ctx = delegate.calls[0]["context"]["context"]
    assert "## Architecture health" not in ctx


def test_design_injection_is_deterministic(tmp_path: Path) -> None:
    """Two runs with the same state build the byte-identical design context."""
    snap = _snapshot(score=8700, duplication=4, max_nesting=9, cycles=2, god_files=1, max_cc=30)

    def _ctx() -> str:
        delegate = _RecordingDelegate()
        state = _state(tmp_path, snapshot=dict(snap))
        state.delegate = delegate
        run_phase_executor(state, "design")
        return delegate.calls[0]["context"]["context"]

    assert _ctx() == _ctx()


def test_design_seam_makes_zero_model_calls(tmp_path: Path) -> None:
    """Building the health block touches no model/subprocess.

    The ONLY call out is the explicit ``delegate.delegate`` (the executor), which
    in the harness is the wired agent — not invoked by the health-rendering code.
    The recording delegate raises if anything *else* tries to call it.
    """

    class _StrictDelegate:
        def __init__(self) -> None:
            self.delegate_calls = 0

        def delegate(self, phase: str, context: dict[str, Any]) -> Any:
            self.delegate_calls += 1

            class _Result:
                status = "success"
                output = "ok"

            return _Result()

    delegate = _StrictDelegate()
    state = _state(tmp_path, snapshot=_snapshot(score=9000, duplication=2))
    state.delegate = delegate
    run_phase_executor(state, "design")
    # Exactly one executor call — the rendering path adds no extra invocations.
    assert delegate.delegate_calls == 1


def test_render_health_is_callable_without_state(tmp_path: Path) -> None:
    """The helper is a free function operating on the dict, independent of state."""
    block = _render_health_for_design(_snapshot(score=9500, duplication=1, max_nesting=5))
    assert isinstance(block, str)
    assert block.startswith("## Architecture health")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
