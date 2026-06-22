"""B2 — phase-handoff compaction (B2-REQ-1).

When ``DesignPhase`` (spec->design) and ``TasksPhase`` (tasks->apply) forward the
prior-phase artifact, the artifact text is compacted through
``summarize_to_budget`` (``memory/rehydration.py``) toward the per-phase token
budget. Compaction MUST be deterministic with no live gateway (the existing safe
fallback) and MUST be a no-op when the artifact already fits.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.context.budgeting import estimate_tokens
from opencontext_core.harness.models import BudgetMode, GateStatus
from opencontext_core.harness.phases import DesignPhase, TasksPhase, _compact_artifact
from opencontext_core.harness.runner import HarnessRunner

# --- _compact_artifact helper (the core seam) --------------------------------


class _NoState:
    """A state with no delegate -> gateway is None -> deterministic trim."""

    delegate = None


def test_compact_under_budget_is_noop() -> None:
    """B2-1c: text already within budget is returned unchanged (no lossy trim)."""
    text = "line one\nline two\nline three\n"
    out = _compact_artifact(text, _NoState(), target_tokens=10_000)
    assert out == text


def test_compact_no_gateway_is_deterministic_and_shrinks() -> None:
    """B2-1b: with no gateway, compaction is deterministic and reduces toward budget."""
    # Build an over-budget multi-line artifact.
    text = "\n".join(f"requirement line number {i} with some words" for i in range(400))
    assert estimate_tokens(text) > 50

    out1 = _compact_artifact(text, _NoState(), target_tokens=50)
    out2 = _compact_artifact(text, _NoState(), target_tokens=50)

    # Deterministic: identical inputs -> identical output.
    assert out1 == out2
    # Reduced toward the budget (line-boundary trim keeps it at/under budget).
    assert estimate_tokens(out1) <= estimate_tokens(text)
    assert len(out1) < len(text)
    # Never raises, never empties a non-empty input entirely.
    assert out1.strip()


def test_compact_handles_missing_delegate_attr() -> None:
    """Degrades when state has no 'delegate' attribute at all (getattr default None)."""

    class _Bare:
        pass

    text = "\n".join(f"line {i}" for i in range(200))
    out = _compact_artifact(text, _Bare(), target_tokens=20)
    assert out  # produced a deterministic trim, did not raise


def test_compact_empty_text_is_noop() -> None:
    """Empty / whitespace input round-trips unchanged (matches summarizer contract)."""
    assert _compact_artifact("", _NoState(), target_tokens=100) == ""


# --- Integration: the phases actually compact the forwarded artifact ----------


def _run_dir(runner: HarnessRunner, state) -> Path:
    d = state.root / ".opencontext" / "runs" / state.run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_design_phase_compacts_oversized_spec(tmp_path: Path, monkeypatch) -> None:
    """spec->design: an over-budget spec.md is compacted before being forwarded."""
    captured: dict[str, str] = {}

    import opencontext_core.harness.phases as phases_mod

    real = phases_mod._compact_artifact

    def _spy(text, state, **kw):
        out = real(text, state, **kw)
        captured["in"] = text
        captured["out"] = out
        return out

    monkeypatch.setattr(phases_mod, "_compact_artifact", _spy)

    runner = HarnessRunner(root=tmp_path)
    state = runner.create_run("sdd", "compaction task")
    state.delegate = None  # force deterministic fallback
    run_dir = _run_dir(runner, state)
    big_spec = "\n".join(f"### Requirement {i}: do thing {i}" for i in range(500))
    (run_dir / "spec.md").write_text(big_spec, encoding="utf-8")

    cfg = runner.config.phases.get("design")
    DesignPhase(cfg, BudgetMode.OFF).run(state)

    assert captured, "_compact_artifact was not called by DesignPhase"
    assert captured["in"] == big_spec
    # Deterministic trim shrank it.
    assert estimate_tokens(captured["out"]) <= estimate_tokens(big_spec)


def test_tasks_phase_compacts_oversized_design(tmp_path: Path, monkeypatch) -> None:
    """tasks->apply: an over-budget design.md is compacted before being forwarded."""
    captured: dict[str, str] = {}

    import opencontext_core.harness.phases as phases_mod

    real = phases_mod._compact_artifact

    def _spy(text, state, **kw):
        out = real(text, state, **kw)
        captured["in"] = text
        captured["out"] = out
        return out

    monkeypatch.setattr(phases_mod, "_compact_artifact", _spy)

    runner = HarnessRunner(root=tmp_path)
    state = runner.create_run("sdd", "compaction task")
    state.delegate = None
    run_dir = _run_dir(runner, state)
    big_design = "\n".join(f"## Section {i}: architecture detail {i}" for i in range(500))
    (run_dir / "design.md").write_text(big_design, encoding="utf-8")

    cfg = runner.config.phases.get("tasks")
    result = TasksPhase(cfg, BudgetMode.OFF).run(state)

    assert result.phase == "tasks"
    assert result.status != GateStatus.FAILED
    assert captured, "_compact_artifact was not called by TasksPhase"
    assert captured["in"] == big_design
    assert estimate_tokens(captured["out"]) <= estimate_tokens(big_design)
