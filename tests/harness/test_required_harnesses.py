"""PR-004 REQ-05: first-class per-phase ``required_harnesses`` on both spines."""

from __future__ import annotations

from opencontext_core.agents.sdd_orchestrator import (
    phase_required_harnesses,
    resolve_phase_harness_modes,
)
from opencontext_core.harness.config import HarnessConfig
from opencontext_core.harness.matrix import SDD_HARNESS_MATRIX
from opencontext_core.oc_new.flow import OC_NEW_FLOW


def test_harness_config_gated_phase_exposes_required_harnesses() -> None:
    # REQ-05: a phase that declares gates exposes a non-empty required_harnesses
    # list defaulting to those gate ids (one source of truth, zero behaviour drift).
    cfg = HarnessConfig()
    for name, phase in cfg.phases.items():
        if phase.gates:
            assert phase.required_harnesses, f"{name} declares gates but no required_harnesses"
            assert phase.required_harnesses == phase.gates


def test_required_harnesses_explicit_override_is_kept() -> None:
    from opencontext_core.harness.config import PhaseConfig

    pc = PhaseConfig(budget_tokens=1000, gates=["g1"], required_harnesses=["mutation"])
    assert pc.required_harnesses == ["mutation"]  # explicit value not overwritten


def test_oc_new_flow_gated_phases_declare_known_harnesses() -> None:
    # REQ-05 + "consumed from the PR-006 harness matrix": every declared harness
    # on the oc_new spine is a real SDD harness subsystem the matrix knows.
    gated = {
        "explore",
        "propose",
        "spec",
        "design",
        "tasks",
        "apply",
        "verify",
        "review",
        "archive",
    }
    for phase in OC_NEW_FLOW:
        if phase.name in gated:
            assert phase.required_harnesses, f"{phase.name} has no required_harnesses"
        for harness in phase.required_harnesses:
            assert harness in SDD_HARNESS_MATRIX, f"{harness} unknown to SDD harness matrix"


def test_resolve_phase_harness_modes_consumes_matrix_read_only() -> None:
    # The resolver reads the PR-006 matrix (read-only) to map each required
    # harness to its effective mode — strictness is matrix/profile driven.
    modes = resolve_phase_harness_modes("verify")
    assert set(modes) == set(phase_required_harnesses("verify"))
    for mode in modes.values():
        assert mode in {"strict", "warn", "off"}
    # 'review' is strict in the SDD baseline matrix.
    assert modes.get("review") == "strict"
