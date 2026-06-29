"""Parity-gated flag-flip mechanism + evidence bundle (AVH-007 / B3 / AVH-010).

Covers the flip MACHINERY (not the live default state, which is recorded honestly in
``.opencontext/flips/*.json`` by the flip driver). Each test drives the machinery with
synthetic evidence in an isolated ``tmp_path`` repo so it is independent of whichever
subsystems actually flipped on this branch:

* per-subsystem ``compat.parity.check_parity`` gates the flip (failing parity reverts);
* before/after benchmark comparison reverts a regression, accepts a non-regression;
* the documented flip order is enforced (an out-of-sequence accepted flip is a violation);
* a bundle missing any of the four artifacts is rejected and the missing artifact named;
* a complete, accepted bundle is read by ``release acceptance`` and its ACTIVE flag is
  verified to match ``config_after``.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.compat.flags import flag_catalog
from opencontext_core.compat.flip_evidence import (
    FLIP_SEQUENCE,
    SUBSYSTEM_FLAGS,
    FlipEvidence,
    active_flag_value,
    benchmark_not_worse,
    emit_flip_evidence,
    evaluate_flip,
    read_flip_bundles,
    sequence_violation,
)
from opencontext_core.compat.parity import check_parity
from opencontext_core.evaluation.models import GateStatus
from opencontext_core.operating_model.release_gate import AcceptanceEvaluator

_GREEN = {"tests": {"passed": 10, "failed": 0, "errors": 0}}


def _bundle(root: Path, subsystem: str, **over: object) -> FlipEvidence:
    """Emit a complete, accepted-by-default flip bundle, overriding fields as needed."""
    flag = SUBSYSTEM_FLAGS[subsystem]
    parity = check_parity(subsystem, flag, legacy=0, vnext=0, equals=lambda a, b: b <= a)
    kwargs: dict[str, object] = dict(
        config_before={flag: False},
        config_after={flag: True},
        benchmark_before=_GREEN,
        benchmark_after=_GREEN,
        parity=parity,
        rollback_flag=flag,
        rollback_path="packages/opencontext_core/opencontext_core/config.py",
    )
    kwargs.update(over)
    return emit_flip_evidence(root, subsystem, flag, **kwargs)  # type: ignore[arg-type]


# ── the documented sequence is the catalog's vNext subsystems ─────────────────


def test_flip_sequence_matches_flag_catalog_subsystems() -> None:
    """Every subsystem in the documented order maps to a real catalog flag."""
    catalog = {spec.name for spec in flag_catalog()}
    for subsystem in FLIP_SEQUENCE:
        assert subsystem in SUBSYSTEM_FLAGS, subsystem
        assert SUBSYSTEM_FLAGS[subsystem] in catalog, SUBSYSTEM_FLAGS[subsystem]


# ── parity gates the flip ─────────────────────────────────────────────────────


def test_failing_parity_auto_reverts(tmp_path: Path) -> None:
    flag = SUBSYSTEM_FLAGS["memory"]
    # vNext introduced 3 failures where legacy had 0 -> parity diverges.
    parity = check_parity("memory", flag, legacy=0, vnext=3, equals=lambda a, b: b <= a)
    bundle = _bundle(
        tmp_path,
        "memory",
        parity=parity,
        benchmark_after={"tests": {"passed": 7, "failed": 3, "errors": 0}},
    )
    assert bundle.accepted is False
    assert bundle.reverted is True
    assert "parity failed" in bundle.reason


def test_parity_pass_and_no_regression_accepts(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path, "workflow_registry")
    assert bundle.accepted is True
    assert bundle.reverted is False


# ── before/after benchmark comparison ─────────────────────────────────────────


def test_worse_benchmark_auto_reverts(tmp_path: Path) -> None:
    bundle = _bundle(
        tmp_path,
        "knowledge_graph",
        benchmark_before={"suites": {"kg-retrieval-precision": "met"}, "tests": _GREEN["tests"]},
        benchmark_after={"suites": {"kg-retrieval-precision": "failed"}, "tests": _GREEN["tests"]},
    )
    assert bundle.accepted is False and bundle.reverted is True
    assert "regressed" in bundle.reason


def test_benchmark_not_worse_helper() -> None:
    met = {"suites": {"s": "met"}, "tests": {"failed": 0}}
    assert benchmark_not_worse(met, met)[0] is True
    worse_suite = {"suites": {"s": "failed"}, "tests": {"failed": 0}}
    assert benchmark_not_worse(met, worse_suite)[0] is False
    worse_tests = {"suites": {"s": "met"}, "tests": {"failed": 2}}
    assert benchmark_not_worse(met, worse_tests)[0] is False


# ── documented flip order is enforced ─────────────────────────────────────────


def test_in_order_accepted_prefix_is_valid() -> None:
    prefix = list(FLIP_SEQUENCE[:3])
    assert sequence_violation(prefix) is None
    assert sequence_violation([]) is None  # the honest all-reverted outcome


def test_out_of_sequence_accept_is_a_violation() -> None:
    # Accept the 3rd subsystem while skipping the 1st/2nd -> violation.
    out_of_order = [FLIP_SEQUENCE[0], FLIP_SEQUENCE[2]]
    violation = sequence_violation(out_of_order)
    assert violation is not None
    assert FLIP_SEQUENCE[2] in violation


# ── the four-artifact completeness rule ───────────────────────────────────────


def test_bundle_missing_artifact_is_rejected(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path, "artifact_store", rollback_flag="")  # drop artifact (4)
    assert bundle.missing_artifacts() == ["rollback flag"]
    evaluate_flip(bundle)
    assert bundle.accepted is False and bundle.reverted is True
    assert "rollback flag" in bundle.reason


def test_each_missing_artifact_named() -> None:
    flag = "runtime.kg_v2_enabled"
    base = dict(
        subsystem="knowledge_graph",
        flag=flag,
        config_before={flag: False},
        config_after={flag: True},
        benchmark_before=_GREEN,
        benchmark_after=_GREEN,
        parity={"passed": True},
        rollback_flag=flag,
        rollback_path="config.py",
    )
    miss = lambda **o: FlipEvidence(**{**base, **o}).missing_artifacts()  # noqa: E731
    assert miss(config_after={}) == ["config snapshot"]
    assert miss(benchmark_after={}) == ["benchmark record"]
    assert miss(parity={}) == ["parity result"]
    assert miss(rollback_flag="") == ["rollback flag"]


# ── release acceptance reads the bundles ──────────────────────────────────────


def test_release_acceptance_rejects_incomplete_bundle(tmp_path: Path) -> None:
    _bundle(tmp_path, "artifact_store", rollback_flag="")
    verdict = AcceptanceEvaluator(repo_root=tmp_path).evaluate()
    flip_gate = next(g for g in verdict.gates if g.gate == "flip-artifact_store")
    assert flip_gate.status is GateStatus.FAILED
    assert "missing" in flip_gate.detail


def test_release_acceptance_accepts_reverted_bundle_as_honest(tmp_path: Path) -> None:
    """An auto-reverted flip whose ACTIVE flag is the legacy default is MET (honest)."""
    flag = SUBSYSTEM_FLAGS["memory"]
    parity = check_parity("memory", flag, legacy=0, vnext=5, equals=lambda a, b: b <= a)
    bundle = _bundle(tmp_path, "memory", parity=parity)
    assert bundle.reverted is True
    # ACTIVE default for memory_v2 is legacy/off, matching config_before.
    assert active_flag_value(flag) == bundle.config_before[flag]
    verdict = AcceptanceEvaluator(repo_root=tmp_path).evaluate()
    flip_gate = next(g for g in verdict.gates if g.gate == "flip-memory")
    assert flip_gate.status is GateStatus.MET
    assert "auto-reverted" in flip_gate.detail


def test_release_acceptance_flags_active_mismatch(tmp_path: Path) -> None:
    """An accepted bundle whose ACTIVE flag does NOT match config_after is FAILED."""
    # workflow_registry default is off on this branch; an 'accepted' bundle claiming
    # config_after=True therefore mismatches the ACTIVE (legacy) state.
    flag = SUBSYSTEM_FLAGS["workflow_registry"]
    if active_flag_value(flag) is True:  # branch already flipped this subsystem
        return
    _bundle(tmp_path, "workflow_registry")  # accepted, config_after={flag: True}
    verdict = AcceptanceEvaluator(repo_root=tmp_path).evaluate()
    flip_gate = next(g for g in verdict.gates if g.gate == "flip-workflow_registry")
    assert flip_gate.status is GateStatus.FAILED
    assert "ACTIVE" in flip_gate.detail


def test_no_bundles_adds_no_flip_gates(tmp_path: Path) -> None:
    verdict = AcceptanceEvaluator(repo_root=tmp_path).evaluate()
    assert not [g for g in verdict.gates if g.gate.startswith("flip-")]
    assert read_flip_bundles(tmp_path) == []
