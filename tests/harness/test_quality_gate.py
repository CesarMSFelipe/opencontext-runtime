"""Architecture & code-quality harness gate wiring (T6).

Covers the verify-phase ``architecture_clean`` + ``quality_standards`` gates that
wire :class:`~opencontext_core.quality.evaluator.QualityEvaluator` into the
harness via ``runner._dispatch_one_gate`` + the explore-phase baseline snapshot.

Invariants asserted here:

* The gates are declared on the verify phase and auto-dispatch through the
  existing ``_dispatch_declared_gates`` router (no new phase class).
* ExplorePhase captures the zero-config architecture-health baseline; the verify
  gate diffs the post-apply graph against it.
* The check path is DETERMINISTIC and makes ZERO model calls — the gate uses only
  the deterministic evaluator (graph analysis + subprocess), never ``state.delegate``.
* WARN-by-default / FAIL-under-STRICT: a health regression is a WARNING under the
  default posture and a FAILED gate under ``BudgetMode.STRICT``.
* Degrade honestly: no baseline -> SKIPPED (reason); a stale graph -> SKIPPED
  (reason); never a false "clean".
* Findings fed to the gate metadata are compact ``file/line/rule`` rows (the
  Builder-feedback + trace payload), not raw tool dumps.

Every test is ``tmp_path``-isolated: the project root, the graph DB
(``tmp_path/.storage/opencontext/context_graph.db``) and any ``quality.toml`` /
baseline live under ``tmp_path``. The real ``~/.opencontext`` and the repo's own
``.opencontext`` are never read or written.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from opencontext_core.config import default_config_data
from opencontext_core.harness.config import HarnessConfig, PhaseConfig
from opencontext_core.harness.models import (
    BudgetMode,
    GateStatus,
    PhaseGate,
)
from opencontext_core.harness.phases import ExplorePhase, PhaseResult
from opencontext_core.harness.runner import HarnessRunner, HarnessState
from opencontext_core.quality.models import HealthScore, QualityMetrics

# --------------------------------------------------------------------------- #
# Fixtures / helpers (all tmp-isolated)
# --------------------------------------------------------------------------- #


def _git_init(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, capture_output=True)


def _write_config(root: Path) -> None:
    (root / "opencontext.yaml").write_text(yaml.safe_dump(default_config_data()), encoding="utf-8")


def _index(root: Path) -> None:
    """Build the real ``context_graph.db`` under ``root/.storage/opencontext``."""
    from opencontext_core.runtime import OpenContextRuntime

    runtime = OpenContextRuntime(
        config_path=str(root / "opencontext.yaml"),
        storage_path=root / ".storage" / "opencontext",
    )
    runtime.index_project(root)


def _clean_repo(root: Path) -> None:
    """A trivially clean Python repo (perfect health: no cycles/god-files/cc)."""
    _git_init(root)
    (root / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    _write_config(root)
    _index(root)


def _degraded_repo(root: Path) -> None:
    """A repo with a file-level import cycle + a high-complexity function.

    Deterministically scores below perfect (cycle penalty + complexity penalty),
    so the snapshot is a stable, non-perfect health value for regression tests.
    """
    _git_init(root)
    (root / "mod_a.py").write_text(
        "from mod_b import beta\n\n\ndef alpha():\n    return beta()\n", encoding="utf-8"
    )
    (root / "mod_b.py").write_text(
        "from mod_a import alpha\n\n\ndef beta():\n    return alpha()\n", encoding="utf-8"
    )
    deep = (
        "def tangled(x):\n"
        + "".join(
            f"    if x == {i} and x > {i - 1} or x < {i + 1}:\n        x += {i}\n"
            for i in range(30)
        )
        + "    return x\n"
    )
    (root / "complex_mod.py").write_text(deep, encoding="utf-8")
    _write_config(root)
    _index(root)


def _state(root: Path, *, delegate: Any = None) -> HarnessState:
    state = HarnessState(run_id="rq", root=root, task="quality gate")
    state.delegate = delegate
    return state


def _verify_result() -> PhaseResult:
    return PhaseResult(phase="verify", status=GateStatus.PASSED)


class _ExplodingDelegate:
    """A model delegate that fails loudly if the gate ever touches it.

    The check path must be deterministic and model-free; if any gate code reaches
    for ``state.delegate`` (the LLM executor) this raises and the test fails.
    """

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(
            f"quality gate touched the model delegate (attr {name!r}); "
            "the check path must be deterministic + model-free"
        )

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("quality gate invoked the model delegate")


# --------------------------------------------------------------------------- #
# Config wiring
# --------------------------------------------------------------------------- #


def test_verify_phase_declares_both_quality_gates() -> None:
    """The two gate ids are declared on the default verify phase config."""
    cfg = HarnessConfig()
    verify_gates = cfg.phases["verify"].gates
    assert "architecture_clean" in verify_gates
    assert "quality_standards" in verify_gates


# --------------------------------------------------------------------------- #
# Explore baseline snapshot
# --------------------------------------------------------------------------- #


def test_explore_captures_architecture_baseline(tmp_path: Path) -> None:
    """ExplorePhase populates ``state.architecture_baseline`` from the graph."""
    _clean_repo(tmp_path)
    cfg = HarnessConfig()
    phase = ExplorePhase(cfg.phases["explore"], BudgetMode.WARN)
    state = _state(tmp_path)
    phase.run(state)

    assert state.architecture_baseline is not None
    assert isinstance(state.architecture_baseline, HealthScore)
    # A clean repo is a perfect 10000; the dict mirror carries the score.
    assert state.architecture_baseline.score == 10000
    assert state.architecture_baseline_dict.get("score") == 10000
    assert "cycles" in state.architecture_baseline_dict


def test_explore_baseline_captures_without_prebuilt_db(tmp_path: Path) -> None:
    """The snapshot scans source, so explore still captures a baseline w/o a DB.

    The architecture snapshot does not strictly require a pre-built graph — it
    falls back to scanning the source tree — so even an un-indexed repo gets a
    health baseline. This is resilient-by-design, not a degraded path.
    """
    _git_init(tmp_path)
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a\n", encoding="utf-8")
    _write_config(tmp_path)
    # NOTE: deliberately NOT indexed — there is no context_graph.db.
    cfg = HarnessConfig()
    phase = ExplorePhase(cfg.phases["explore"], BudgetMode.WARN)
    state = _state(tmp_path)
    result = phase.run(state)
    assert result.phase == "explore"
    assert isinstance(state.architecture_baseline, HealthScore)


def test_explore_baseline_is_best_effort_on_snapshot_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A snapshot exception is swallowed: explore completes, baseline stays None."""
    _clean_repo(tmp_path)

    def _boom(self: Any, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("snapshot exploded")

    monkeypatch.setattr("opencontext_core.quality.evaluator.QualityEvaluator.snapshot", _boom)
    cfg = HarnessConfig()
    phase = ExplorePhase(cfg.phases["explore"], BudgetMode.WARN)
    state = _state(tmp_path)
    result = phase.run(state)
    # The explore phase must not crash; the baseline is simply absent.
    assert result.phase == "explore"
    assert state.architecture_baseline is None


# --------------------------------------------------------------------------- #
# Dispatch routing + clean end-to-end
# --------------------------------------------------------------------------- #


def test_quick_run_dispatches_both_gates_clean(tmp_path: Path) -> None:
    """A clean indexed repo: both gates dispatch on verify and PASS."""
    _clean_repo(tmp_path)
    result = HarnessRunner(root=tmp_path).run("quick", "describe the add function", BudgetMode.WARN)
    by_id = {g.id: g for g in result.gates}
    assert "architecture_clean" in by_id
    assert "quality_standards" in by_id
    assert by_id["architecture_clean"].status == GateStatus.PASSED
    assert by_id["quality_standards"].status == GateStatus.PASSED
    # The architecture gate's message is the compact health delta one-liner.
    assert by_id["architecture_clean"].message.startswith("architecture ")
    # Clean run is not failed by the quality gates.
    assert result.status in (GateStatus.PASSED, GateStatus.WARNING)


def test_clean_repo_is_not_reported_stale(tmp_path: Path) -> None:
    """Regression: ``.storage`` sidecars (WAL/shm/memory.db) must NOT mark stale.

    ``_git_changed_files`` returns the DB's own sidecar files, which are written
    after the graph and are naturally newer. The staleness check must ignore
    internal byproduct paths and only consider changed SOURCE files.
    """
    _clean_repo(tmp_path)
    changed = HarnessRunner._git_changed_files(tmp_path)
    # Sanity: the raw changed set DOES include internal storage byproducts.
    assert any(c.startswith(".storage/") for c in changed)
    # ...but the staleness check ignores them -> not stale.
    assert HarnessRunner._graph_is_stale(tmp_path, changed) is False


# --------------------------------------------------------------------------- #
# Degrade honestly
# --------------------------------------------------------------------------- #


def test_architecture_gate_skipped_without_baseline(tmp_path: Path) -> None:
    """No explore baseline -> SKIPPED with a reason (never a false clean)."""
    _clean_repo(tmp_path)
    runner = HarnessRunner(root=tmp_path)
    state = _state(tmp_path)
    state.architecture_baseline = None  # explore never snapshotted
    gate = runner._eval_architecture_gate(state, _verify_result())
    assert isinstance(gate, PhaseGate)
    assert gate.status == GateStatus.SKIPPED
    assert gate.metadata.get("reason") == "no-baseline"


def test_architecture_gate_skipped_on_stale_graph(tmp_path: Path) -> None:
    """A source file newer than the graph -> SKIPPED (reindex incomplete)."""
    _clean_repo(tmp_path)
    runner = HarnessRunner(root=tmp_path)
    state = _state(tmp_path)
    state.architecture_baseline = HealthScore(score=10000, metrics=QualityMetrics(), components={})
    # Make a tracked SOURCE file newer than the DB (simulates a failed reindex).
    db = tmp_path / ".storage" / "opencontext" / "context_graph.db"
    future = db.stat().st_mtime + 1000
    src = tmp_path / "calc.py"
    os.utime(src, (future, future))
    gate = runner._eval_architecture_gate(state, _verify_result())
    assert gate.status == GateStatus.SKIPPED
    assert gate.metadata.get("reason") == "stale-graph"


def test_quality_standards_gate_skipped_on_stale_graph(tmp_path: Path) -> None:
    """quality_standards also degrades to SKIPPED on a stale graph."""
    _clean_repo(tmp_path)
    runner = HarnessRunner(root=tmp_path)
    state = _state(tmp_path)
    db = tmp_path / ".storage" / "opencontext" / "context_graph.db"
    future = db.stat().st_mtime + 1000
    os.utime(tmp_path / "calc.py", (future, future))
    gate = runner._eval_quality_standards_gate(state, _verify_result())
    assert gate.status == GateStatus.SKIPPED
    assert gate.metadata.get("reason") == "stale-graph"


# --------------------------------------------------------------------------- #
# Regression: WARN by default, FAIL under STRICT
# --------------------------------------------------------------------------- #


def test_architecture_regression_warns_by_default(tmp_path: Path) -> None:
    """A health drop is a WARNING under the default (ratchet) posture.

    Baseline is a perfect 10000 (captured on a clean tree); the post-change graph
    is the degraded repo (cycle + complexity) so ``current.score < baseline`` and
    the gate WARNs with the compact delta + new findings in metadata.
    """
    _degraded_repo(tmp_path)
    runner = HarnessRunner(root=tmp_path)
    state = _state(tmp_path, delegate=_ExplodingDelegate())
    state.architecture_baseline = HealthScore(score=10000, metrics=QualityMetrics(), components={})
    gate = runner._eval_architecture_gate(state, _verify_result())

    assert gate.status == GateStatus.WARNING
    assert gate.metadata["current"] < gate.metadata["baseline"]
    assert gate.metadata["delta"] < 0
    assert gate.message.startswith("architecture 10000 -> ")
    # The Builder/trace payload is compact file/line/rule rows, not raw dumps.
    new = gate.metadata["new_findings"]
    assert new and all({"rule", "severity", "message"} <= set(row) for row in new)


def test_architecture_regression_fails_under_strict(tmp_path: Path) -> None:
    """Under ``mode = strict`` a health drop is a FAILED gate."""
    _degraded_repo(tmp_path)
    (tmp_path / ".opencontext").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".opencontext" / "quality.toml").write_text('mode = "strict"\n', encoding="utf-8")
    runner = HarnessRunner(root=tmp_path)
    state = _state(tmp_path, delegate=_ExplodingDelegate())
    state.architecture_baseline = HealthScore(score=10000, metrics=QualityMetrics(), components={})
    gate = runner._eval_architecture_gate(state, _verify_result())
    assert gate.status == GateStatus.FAILED
    assert gate.metadata["delta"] < 0


def test_strict_regression_fails_the_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: a regression makes the dispatched gate FAIL the run under STRICT.

    Stages a clean->degraded change across the run: ``snapshot`` returns a perfect
    baseline at explore and a degraded score at verify (both through the REAL gate
    + dispatch code), so the architecture_clean gate sees a genuine drop. Under
    ``BudgetMode.STRICT`` the dispatch loop escalates the FAILED gate to a FAILED
    run — the WARN-by-default / FAIL-under-STRICT posture owned by the loop, not
    the gate helper.
    """
    _clean_repo(tmp_path)
    (tmp_path / ".opencontext").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".opencontext" / "quality.toml").write_text('mode = "strict"\n', encoding="utf-8")

    # Stateful snapshot: 1st call (explore) = perfect baseline; later calls
    # (verify) = a degraded score, i.e. the change regressed architecture.
    calls = {"n": 0}
    perfect = HealthScore(score=10000, metrics=QualityMetrics(), components={})
    degraded = HealthScore(score=9100, metrics=QualityMetrics(cycles=1), components={"cycles": 400})

    def _staged_snapshot(self: Any, *, changed_files: Any = None) -> HealthScore:
        calls["n"] += 1
        return perfect if calls["n"] == 1 else degraded

    monkeypatch.setattr(
        "opencontext_core.quality.evaluator.QualityEvaluator.snapshot",
        _staged_snapshot,
    )

    cfg = HarnessConfig()
    cfg.phases["apply"] = PhaseConfig(budget_tokens=12000, gates=[])
    cfg.phases["verify"] = PhaseConfig(budget_tokens=4000, gates=["architecture_clean"])
    result = HarnessRunner(root=tmp_path, config=cfg).run(
        "quick", "regress architecture", BudgetMode.STRICT
    )

    arch_gates = [g for g in result.gates if g.id == "architecture_clean"]
    assert arch_gates, "architecture_clean dispatched on verify"
    assert arch_gates[0].status == GateStatus.FAILED
    assert arch_gates[0].metadata["delta"] < 0
    assert result.status == GateStatus.FAILED


# --------------------------------------------------------------------------- #
# quality_standards report mapping + determinism + zero-model
# --------------------------------------------------------------------------- #


def test_quality_standards_maps_report_status(tmp_path: Path) -> None:
    """The gate status mirrors the QualityReport status; findings are compact."""
    _degraded_repo(tmp_path)
    runner = HarnessRunner(root=tmp_path)
    state = _state(tmp_path, delegate=_ExplodingDelegate())
    gate = runner._eval_quality_standards_gate(state, _verify_result())
    # Degraded repo under default ratchet/warn -> WARNING (surfaces, never blocks).
    assert gate.status in (GateStatus.WARNING, GateStatus.PASSED)
    assert "health" in gate.metadata
    # Findings (if any) are compact rows, never raw tool output strings.
    for row in gate.metadata.get("findings", []):
        assert {"rule", "severity", "message", "file", "line"} <= set(row)


def test_gate_is_deterministic(tmp_path: Path) -> None:
    """Same inputs -> identical gate verdict + metadata (no wall-clock/randomness)."""
    _degraded_repo(tmp_path)
    runner = HarnessRunner(root=tmp_path)
    base = HealthScore(score=10000, metrics=QualityMetrics(), components={})

    def _run() -> PhaseGate:
        st = _state(tmp_path)
        st.architecture_baseline = base
        return runner._eval_architecture_gate(st, _verify_result())

    g1, g2 = _run(), _run()
    assert g1.status == g2.status
    assert g1.message == g2.message
    assert g1.metadata["current"] == g2.metadata["current"]
    assert g1.metadata["new_findings"] == g2.metadata["new_findings"]


def test_gates_never_touch_the_model_delegate(tmp_path: Path) -> None:
    """Zero model calls: both gates run with an exploding delegate present."""
    _degraded_repo(tmp_path)
    runner = HarnessRunner(root=tmp_path)
    state = _state(tmp_path, delegate=_ExplodingDelegate())
    state.architecture_baseline = HealthScore(score=10000, metrics=QualityMetrics(), components={})
    # Neither call may reach for state.delegate (would raise AssertionError).
    arch = runner._eval_architecture_gate(state, _verify_result())
    qual = runner._eval_quality_standards_gate(state, _verify_result())
    assert arch.id == "architecture_clean"
    assert qual.id == "quality_standards"


# --------------------------------------------------------------------------- #
# tmp isolation guard
# --------------------------------------------------------------------------- #


def test_gate_run_does_not_touch_real_or_repo_opencontext(tmp_path: Path) -> None:
    """The whole gate path stays under tmp_path; real/repo .opencontext untouched."""
    repo_oc = Path(__file__).resolve().parents[2] / ".opencontext"
    home_oc = Path.home() / ".opencontext"

    def _snapshot(p: Path) -> set[str]:
        if not p.exists():
            return set()
        return {str(x.relative_to(p)) for x in p.rglob("*")}

    repo_before = _snapshot(repo_oc)
    home_before = _snapshot(home_oc)

    _degraded_repo(tmp_path)
    runner = HarnessRunner(root=tmp_path)
    state = _state(tmp_path)
    state.architecture_baseline = HealthScore(score=10000, metrics=QualityMetrics(), components={})
    runner._eval_architecture_gate(state, _verify_result())
    runner._eval_quality_standards_gate(state, _verify_result())

    assert _snapshot(repo_oc) == repo_before, "gate wrote into the repo .opencontext"
    assert _snapshot(home_oc) == home_before, "gate wrote into ~/.opencontext"
    # And the work all landed under tmp_path.
    assert (tmp_path / ".storage" / "opencontext" / "context_graph.db").exists()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
