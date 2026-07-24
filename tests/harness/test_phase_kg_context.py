"""Rodaja 3 — middle SDD phases build FRESH, KG-grounded, token-budgeted context.

Rodaja 1 folded recalled ``phase_memory`` into the middle phases' executor
context. Rodaja 3 gives spec / design / tasks / apply a FRESH context pack built
with the SAME builder ``ExplorePhase`` uses (``OpenContextRuntime.build_context_pack``),
but with a query DERIVED from THAT phase's own input artifact and capped to the
phase's own token budget (``PhaseConfig.budget_tokens``). The fresh pack is folded
into ``state.context_pack`` ALONGSIDE the prior artifact + ``state.phase_memory``
(composed, not replaced) so it reaches the executor.

These tests assert behavior, not exact token counts:

* each of spec/design/tasks/apply issues a fresh ``build_context_pack`` whose QUERY
  is derived from its input artifact (recorded via a fake runtime);
* the phase's own ``budget_tokens`` is passed as the pack budget (not unbounded);
* the KG-derived content reaches the executor context (captured via a fake delegate);
* Rodaja-1 ``phase_memory`` folding still works (no regression).

The fake runtime records every ``build_context_pack(query, budget)`` call and
returns a canned pack carrying a KG sentinel, so we can assert both the query
derivation and that the sentinel flows through to the model-facing context.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

import opencontext_core.harness.phases as phases_mod
from opencontext_core.harness.models import BudgetMode, GateStatus
from opencontext_core.harness.phases import (
    DesignPhase,
    SpecPhase,
    TasksPhase,
    _fold_kg_context,
)
from opencontext_core.harness.runner import HarnessRunner
from opencontext_core.paths.execution_state import runs_root

KG_SENTINEL = "KG-FRESH-CONTEXT-SENTINEL authenticate bcrypt"


# --- fakes -------------------------------------------------------------------


@dataclass
class _FakeItem:
    """Minimal context-pack item: only the fields the renderer reads."""

    source: str
    content: str


@dataclass
class _FakePack:
    """Minimal ContextPackResult stand-in for the renderer + budget path."""

    included: list[_FakeItem]
    used_tokens: int = 40


@dataclass
class RecordingRuntime:
    """Records every build_context_pack(query, budget) and returns a canned pack.

    Mirrors the real ``OpenContextRuntime`` surface the middle phases use: a
    ``build_context_pack(query, max_tokens=...)`` returning a pack whose
    ``included`` items carry the KG sentinel so we can trace it to the executor.
    """

    calls: list[tuple[str, int | None]] = field(default_factory=list)

    def __init__(self, *_a: Any, **_k: Any) -> None:
        self.calls = []

    def build_context_pack(self, query: str, max_tokens: int | None = None, **_k: Any) -> _FakePack:
        self.calls.append((query, max_tokens))
        return _FakePack(included=[_FakeItem(source="auth.py", content=KG_SENTINEL)])

    # index_project is only used by ExplorePhase; middle phases never call it, but
    # keep it present so a stray call degrades gracefully instead of AttributeError.
    def index_project(self, *_a: Any, **_k: Any) -> Any:  # pragma: no cover - safety
        raise AssertionError("middle phases must not re-index")


@dataclass
class CapturingDelegate:
    """Fake executor: records the context dict handed to each phase and succeeds."""

    contexts: dict[str, dict[str, Any]] = field(default_factory=dict)

    def delegate(self, phase: str, context: dict[str, Any]) -> Any:
        self.contexts[phase] = context

        class _R:
            status = "success"
            output = f"executor output for {phase}"
            error = None

        return _R()


# --- fixtures ----------------------------------------------------------------


@pytest.fixture
def wired(tmp_path: Path, monkeypatch):
    """A runner + run whose middle phases resolve the RecordingRuntime + a delegate.

    Patches ``phases_mod.OpenContextRuntime`` so ``_fold_kg_context`` builds the
    recording fake instead of a real runtime (which would need a real index).
    """
    (tmp_path / "auth.py").write_text("def auth(u, p):\n    return u == p\n", encoding="utf-8")
    runtime = RecordingRuntime()
    monkeypatch.setattr(phases_mod, "OpenContextRuntime", lambda *a, **k: runtime)

    runner = HarnessRunner(root=tmp_path)
    state = runner.create_run("sdd", "improve authenticate password hashing")
    delegate = CapturingDelegate()
    state.delegate = delegate
    return runner, state, runtime, delegate


def _run_dir(state: Any) -> Path:
    d = runs_root(state.root) / state.run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _seed_proposal(state: Any) -> None:
    run_dir = _run_dir(state)
    (run_dir / "proposal.json").write_text(
        json.dumps(
            {
                "task": state.task,
                "approach": {"method": "incremental"},
                "scope": {"required_symbols": ["authenticate"], "affected_files": ["auth.py"]},
                "required_symbols": ["authenticate"],
                "affected_files": ["auth.py"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _seed_spec(state: Any) -> None:
    run_dir = _run_dir(state)
    (run_dir / "spec.md").write_text(
        "# Delta Spec: improve authenticate password hashing\n\n"
        "## ADDED Requirements\n\n"
        "### Requirement: Hash passwords with bcrypt\n"
        "MUST hash via bcrypt in authenticate.\n",
        encoding="utf-8",
    )


def _seed_design(state: Any) -> None:
    run_dir = _run_dir(state)
    (run_dir / "design.md").write_text(
        "# Design: improve authenticate password hashing\n\n"
        "## Files to Create/Modify\n\n"
        "- auth.py\n\n"
        "## Components\n- bcrypt hashing in authenticate\n",
        encoding="utf-8",
    )


def _seed_tasks(state: Any) -> None:
    run_dir = _run_dir(state)
    (run_dir / "tasks.json").write_text(
        json.dumps(
            [
                {
                    "id": "task-1",
                    "description": "Implement bcrypt in authenticate",
                    "file_paths": ["auth.py"],
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )


# --- _fold_kg_context helper (the core seam) ---------------------------------


def test_fold_kg_context_appends_pack_and_records_query(tmp_path: Path, monkeypatch) -> None:
    runtime = RecordingRuntime()
    monkeypatch.setattr(phases_mod, "OpenContextRuntime", lambda *a, **k: runtime)

    class _S:
        root = tmp_path
        context_pack = "EXISTING EXPLORE PACK"
        delegate = None

    state = _S()
    _fold_kg_context(state, "spec", "authenticate bcrypt hashing", 3000)

    # Recorded the query + budget.
    assert runtime.calls == [("authenticate bcrypt hashing", 3000)]
    # Appended the KG sentinel WITHOUT dropping the existing explore pack (compose).
    assert "EXISTING EXPLORE PACK" in state.context_pack
    assert KG_SENTINEL in state.context_pack


def test_fold_kg_context_never_raises_on_runtime_failure(tmp_path: Path, monkeypatch) -> None:
    def _boom(*_a: Any, **_k: Any):
        raise RuntimeError("no index")

    monkeypatch.setattr(phases_mod, "OpenContextRuntime", _boom)

    class _S:
        root = tmp_path
        context_pack = "ORIGINAL"
        delegate = None

    state = _S()
    # Best-effort: a runtime failure leaves the original context untouched, no raise.
    _fold_kg_context(state, "design", "some query", 4000)
    assert state.context_pack == "ORIGINAL"


def test_fold_kg_context_caps_to_budget(tmp_path: Path, monkeypatch) -> None:
    from opencontext_core.context.budgeting import estimate_tokens

    big = "word " * 5000

    class _BigRuntime(RecordingRuntime):
        def build_context_pack(self, query: str, max_tokens: int | None = None, **_k: Any):
            self.calls.append((query, max_tokens))
            return _FakePack(included=[_FakeItem(source="auth.py", content=big)], used_tokens=5000)

    runtime = _BigRuntime()
    monkeypatch.setattr(phases_mod, "OpenContextRuntime", lambda *a, **k: runtime)

    class _S:
        root = tmp_path
        context_pack = ""
        delegate = None

    state = _S()
    budget = 500
    _fold_kg_context(state, "spec", "q", budget)
    # The folded block is capped toward the phase budget (compresión adecuada),
    # so a huge pack cannot blow the phase's token budget.
    assert estimate_tokens(state.context_pack) <= budget * 2


# --- anti-bloat: NO cross-phase KG accumulation (the load-bearing invariant) ---


def test_fold_kg_context_no_cross_phase_accumulation(tmp_path: Path, monkeypatch) -> None:
    """Folding spec→design→tasks on ONE state must NOT stack prior phases' KG blocks.

    Each fold rebuilds ``state.context_pack`` from the STABLE explore base + this
    phase's fresh block. So after the tasks fold the context carries the tasks
    block and the explore base, but NOT the spec or design blocks — otherwise the
    per-phase total grows unbounded across the pipeline (the "compresión adecuada"
    violation this change fixes).
    """

    # Per-phase distinct sentinels so we can tell which blocks survived.
    class _PhaseRuntime(RecordingRuntime):
        def build_context_pack(self, query: str, max_tokens: int | None = None, **_k: Any):
            self.calls.append((query, max_tokens))
            # The query encodes the phase (we pass "<phase>-QUERY"); echo a
            # phase-specific sentinel so the rendered block is identifiable.
            marker = query.split("-", 1)[0].upper()
            return _FakePack(included=[_FakeItem(source="auth.py", content=f"KG-{marker}-BLOCK")])

    runtime = _PhaseRuntime()
    monkeypatch.setattr(phases_mod, "OpenContextRuntime", lambda *a, **k: runtime)

    class _S:
        root = tmp_path
        context_pack = "EXPLORE-BASE-PACK"
        delegate = None

    state = _S()
    _fold_kg_context(state, "spec", "spec-QUERY", 3000)
    _fold_kg_context(state, "design", "design-QUERY", 3000)
    _fold_kg_context(state, "tasks", "tasks-QUERY", 3000)

    ctx = state.context_pack
    # The explore base is ALWAYS preserved (composed, never dropped).
    assert "EXPLORE-BASE-PACK" in ctx
    # The current (tasks) phase's fresh block is present, tagged as such.
    assert "### fresh tasks context" in ctx
    assert "KG-TASKS-BLOCK" in ctx
    # PRIOR phases' KG blocks must NOT accumulate into the tasks-stage context.
    assert "### fresh spec context" not in ctx
    assert "### fresh design context" not in ctx
    assert "KG-SPEC-BLOCK" not in ctx
    assert "KG-DESIGN-BLOCK" not in ctx


def test_fold_kg_context_bound_is_base_plus_one_block_not_sum(tmp_path: Path, monkeypatch) -> None:
    """After N folds the context stays ~ (explore base + ONE phase block), not the sum.

    A per-BLOCK cap alone does not bound the per-PHASE total when blocks
    accumulate; this asserts the total after three folds is close to base + a
    single block, far below base + 3*block.
    """
    from opencontext_core.context.budgeting import estimate_tokens

    block_body = "token " * 400  # a non-trivial per-phase block

    class _FatRuntime(RecordingRuntime):
        def build_context_pack(self, query: str, max_tokens: int | None = None, **_k: Any):
            self.calls.append((query, max_tokens))
            return _FakePack(included=[_FakeItem(source="auth.py", content=block_body)])

    runtime = _FatRuntime()
    monkeypatch.setattr(phases_mod, "OpenContextRuntime", lambda *a, **k: runtime)

    base = "explore " * 200

    class _S:
        root = tmp_path
        context_pack = base
        delegate = None

    state = _S()
    budget = 5000  # generous so the cap does not mask accumulation
    _fold_kg_context(state, "spec", "spec q", budget)
    _fold_kg_context(state, "design", "design q", budget)
    _fold_kg_context(state, "tasks", "tasks q", budget)

    total = estimate_tokens(state.context_pack)
    one_block = estimate_tokens(block_body)
    base_tokens = estimate_tokens(base)
    # Bounded by base + ONE block (+ small heading/formatting headroom), NOT the
    # sum of every folded block (base + 3*block).
    assert total <= base_tokens + one_block * 2
    assert total < base_tokens + one_block * 3


# --- spec: query derived from the proposal -----------------------------------


def test_spec_builds_fresh_pack_from_proposal(wired) -> None:
    runner, state, runtime, delegate = wired
    _seed_proposal(state)

    cfg = runner.config.phases["spec"]
    SpecPhase(cfg, BudgetMode.OFF).run(state)

    # A fresh pack was built with the spec phase's budget (not unbounded).
    assert runtime.calls, "spec did not build a fresh KG context pack"
    query, budget = runtime.calls[-1]
    assert budget == cfg.budget_tokens
    # The query is derived from the proposal's scope: the required symbol appears.
    assert "authenticate" in query.lower()
    # The KG content reached the spec executor's context.
    assert "spec" in delegate.contexts
    assert KG_SENTINEL in str(delegate.contexts["spec"].get("context", ""))


# --- design: query derived from the spec -------------------------------------


def test_design_builds_fresh_pack_from_spec(wired) -> None:
    runner, state, runtime, delegate = wired
    _seed_spec(state)

    cfg = runner.config.phases["design"]
    DesignPhase(cfg, BudgetMode.OFF).run(state)

    assert runtime.calls, "design did not build a fresh KG context pack"
    query, budget = runtime.calls[-1]
    assert budget == cfg.budget_tokens
    # Derived from the spec's requirement heading.
    assert "bcrypt" in query.lower() or "authenticate" in query.lower()
    assert "design" in delegate.contexts
    assert KG_SENTINEL in str(delegate.contexts["design"].get("context", ""))


# --- tasks: query derived from the design ------------------------------------


def test_tasks_builds_fresh_pack_from_design(wired) -> None:
    runner, state, runtime, delegate = wired
    _seed_design(state)

    cfg = runner.config.phases["tasks"]
    TasksPhase(cfg, BudgetMode.OFF).run(state)

    assert runtime.calls, "tasks did not build a fresh KG context pack"
    query, budget = runtime.calls[-1]
    assert budget == cfg.budget_tokens
    # Derived from the design's components/files.
    assert "auth" in query.lower() or "bcrypt" in query.lower()
    assert "tasks" in delegate.contexts
    assert KG_SENTINEL in str(delegate.contexts["tasks"].get("context", ""))


# --- apply: ONE fresh pack derived from the task list's symbols --------------


def test_apply_builds_one_fresh_pack_from_tasks(wired, monkeypatch) -> None:
    runner, state, runtime, _delegate = wired
    _seed_tasks(state)

    # Apply reads state.context_pack for codegen; drive the apply-context fold
    # directly (the runner wires codegen separately). Assert a SINGLE pack build
    # (not a per-task loop) whose query is derived from the task list.
    from opencontext_core.harness.phases import _fold_apply_kg_context

    cfg = runner.config.phases["apply"]
    _fold_apply_kg_context(state, cfg.budget_tokens)

    # Exactly one fresh build — NOT a per-task loop.
    assert len(runtime.calls) == 1, f"apply must build ONE pack, got {len(runtime.calls)}"
    query, budget = runtime.calls[-1]
    assert budget == cfg.budget_tokens
    # Derived from the task list's file_paths / description.
    assert "auth" in query.lower() or "authenticate" in query.lower()
    assert KG_SENTINEL in state.context_pack


# --- end-to-end: real spec→design→tasks flow does NOT accumulate KG blocks ----


def test_real_phase_flow_no_cross_phase_kg_accumulation(wired) -> None:
    """Drive the REAL spec→design→tasks phases on one state; the tasks-stage
    context must carry the tasks KG block but NOT the spec/design KG blocks.

    Each middle phase's fold rebuilds ``state.context_pack`` from the stable
    explore base + THIS phase's block, so the executor context is bounded by
    (explore base + one phase block + prior_artifact + phase_memory), never the
    running sum of every phase's KG block.
    """
    runner, state, _runtime, delegate = wired
    # Seed the whole chain so each phase's input artifact exists.
    _seed_proposal(state)
    _seed_spec(state)
    _seed_design(state)

    # Give the explore base a recognisable marker (ExplorePhase would set this).
    state.context_pack = "### explore base\nEXPLORE-BASE-MARKER"

    SpecPhase(runner.config.phases["spec"], BudgetMode.OFF).run(state)
    DesignPhase(runner.config.phases["design"], BudgetMode.OFF).run(state)
    TasksPhase(runner.config.phases["tasks"], BudgetMode.OFF).run(state)

    # The context the TASKS executor actually saw.
    tasks_ctx = str(delegate.contexts["tasks"].get("context", ""))
    # Explore base survives every phase (composed, never dropped).
    assert "EXPLORE-BASE-MARKER" in tasks_ctx
    # This phase's fresh block is present.
    assert "### fresh tasks context" in tasks_ctx
    # PRIOR phases' KG blocks did NOT accumulate into the tasks context.
    assert "### fresh spec context" not in tasks_ctx
    assert "### fresh design context" not in tasks_ctx
    # And the persisted state.context_pack itself carries no prior-phase KG block.
    assert "### fresh spec context" not in state.context_pack
    assert "### fresh design context" not in state.context_pack


# --- regression: Rodaja-1 phase_memory folding still works --------------------


def test_phase_memory_still_reaches_executor_alongside_kg(wired) -> None:
    runner, state, _runtime, delegate = wired
    _seed_spec(state)

    # Rodaja-1: the runner sets state.phase_memory before the phase; simulate it.
    state.phase_memory = "## Recalled memory\n- [FAILURE] RODAJA1-MEMORY-SENTINEL"

    cfg = runner.config.phases["design"]
    DesignPhase(cfg, BudgetMode.OFF).run(state)

    blob = str(delegate.contexts["design"].get("context", ""))
    # BOTH the fresh KG context AND the recalled memory must be present (composed).
    assert KG_SENTINEL in blob, "fresh KG context missing"
    assert "RODAJA1-MEMORY-SENTINEL" in blob, "Rodaja-1 phase_memory folding regressed"


def test_spec_status_not_failed_with_fresh_context(wired) -> None:
    """Folding fresh context must not break the phase's normal success path."""
    runner, state, _runtime, _delegate = wired
    _seed_proposal(state)

    cfg = runner.config.phases["spec"]
    result = SpecPhase(cfg, BudgetMode.OFF).run(state)
    assert result.status != GateStatus.FAILED
