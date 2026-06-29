"""PR-006 Harness Registry tests (AC-HA1..HA5 + REG-CONV CONV.4/5/6 + determinism)."""

from __future__ import annotations

import pytest

from opencontext_core.harness.config import HarnessConfig
from opencontext_core.harness.definition import HarnessDefinition
from opencontext_core.harness.gates import NoSecretLeakageGate
from opencontext_core.harness.matrix import (
    SDD_HARNESS_MATRIX,
    mode_blocks,
    resolve_harness_mode,
)
from opencontext_core.harness.models import GateSeverity, GateStatus, PhaseGate
from opencontext_core.harness.registry import HarnessNotFound, HarnessRegistry
from opencontext_core.harness.results import GateResult, HarnessResult, harness_result_from_run

_HARNESS_IDS = {
    "context",
    "planning",
    "protocol",
    "mutation",
    "inspection",
    "diagnosis",
    "review",
    "security",
    "escalation",
    "memory",
    "kg",
    "consolidation",
    "evaluation",
}


# --- AC-HA1: HarnessRegistry + HarnessDefinition -------------------------------


def test_registry_lists_all_thirteen() -> None:
    reg = HarnessRegistry.with_builtins()
    assert set(reg.list_ids()) == _HARNESS_IDS
    assert len(reg.list()) == 13


def test_harness_definition_declares_default_mode() -> None:
    mode = HarnessRegistry.with_builtins().get("mutation").default_mode
    assert mode in {"off", "warn", "strict"}
    assert mode == "strict"


def test_unknown_harness_raises() -> None:
    with pytest.raises(HarnessNotFound):
        HarnessRegistry.with_builtins().get("nope")


# --- AC-HA2: HarnessResult aggregates status + gates ---------------------------


def test_harness_result_aggregates_status_and_gates() -> None:
    res = HarnessResult(
        harness_id="mutation",
        status=GateStatus.PASSED,
        gates=[GateResult(gate_id="path_policy_passed", status=GateStatus.PASSED)],
    )
    assert res.status == GateStatus.PASSED
    assert res.gates[0].gate_id == "path_policy_passed"
    assert res.schema_version == "opencontext.harness_result.v1"


# --- AC-HA3: GateResult severity/evidence/blocking + legacy default ------------


def test_gate_result_exposes_severity_and_blocking() -> None:
    gr = GateResult(
        gate_id="no_secret_leakage",
        status=GateStatus.FAILED,
        severity=GateSeverity.CRITICAL,
        blocking=True,
        evidence_refs=["src/x.py:10"],
    )
    assert gr.severity == "critical"
    assert gr.blocking is True
    assert gr.evidence_refs == ["src/x.py:10"]


def test_legacy_phasegate_still_constructs_with_defaults() -> None:
    g = PhaseGate(id="g", phase="verify", status=GateStatus.FAILED, message="m")
    assert g.severity == GateSeverity.WARNING  # sane default
    assert g.evidence_refs == []
    assert g.blocking is False
    # adapter round-trips onto the book GateResult.
    gr = g.to_gate_result()
    assert gr.gate_id == "g"
    assert gr.status == GateStatus.FAILED
    assert gr.severity == GateSeverity.WARNING


# --- AC-HA4: thirteen named harnesses + diagnosis gates ------------------------


def test_all_thirteen_register_with_at_least_one_gate() -> None:
    reg = HarnessRegistry.with_builtins()
    for hid in _HARNESS_IDS:
        assert reg.get(hid).gates, f"{hid} declares no gates"


def test_diagnosis_harness_declares_its_gates() -> None:
    gates = HarnessRegistry.with_builtins().get("diagnosis").gates
    assert "hypothesis_count_valid" in gates
    assert "attempt_budget_respected" in gates


# --- AC-HA5: phase->gate matrix + strict-blocks --------------------------------


def test_sdd_matrix_and_verify_phase_gates() -> None:
    assert SDD_HARNESS_MATRIX["context"] == "strict"
    assert SDD_HARNESS_MATRIX["mutation"] == "strict"
    verify_gates = HarnessConfig().phases["verify"].gates
    assert "security_scan_passed" in verify_gates
    assert "quality_standards" in verify_gates


def test_strict_blocks_warn_advisory() -> None:
    assert mode_blocks("strict") is True
    assert mode_blocks("warn") is False
    assert mode_blocks("off") is False


# --- CONV.4: harness false-positive metric ------------------------------------


def test_harness_result_carries_false_positive_metric() -> None:
    res = HarnessResult(harness_id="security")
    assert res.false_positive_rate == 0.0
    res2 = HarnessResult(harness_id="security", false_positive_rate=0.25)
    assert res2.false_positive_rate == 0.25


def test_run_result_carries_false_positive_metric() -> None:
    from opencontext_core.harness.models import HarnessRunResult

    run = HarnessRunResult(run_id="r", workflow="sdd", task="t", status=GateStatus.PASSED)
    assert run.false_positive_rate == 0.0
    out = harness_result_from_run(run, harness_id="mutation", mode="strict")
    assert out.harness_id == "mutation"
    assert out.mode == "strict"


# --- CONV.5: strictness by profile --------------------------------------------


def test_enterprise_profile_raises_security_to_strict() -> None:
    assert resolve_harness_mode("security", "enterprise") == "strict"


def test_low_cost_profile_keeps_security_warn() -> None:
    assert resolve_harness_mode("security", "low-cost") == "warn"


def test_default_mode_falls_back_to_definition() -> None:
    # An id absent from the SDD matrix falls back to the harness definition mode.
    reg = HarnessRegistry.with_builtins()
    reg.register(HarnessDefinition(id="custom", default_mode="strict", gates=["g"]))
    assert resolve_harness_mode("custom", registry=reg) == "strict"


# --- CONV.6: plugin metadata + cross-ref validation ----------------------------


def test_registry_entries_expose_source_and_trust() -> None:
    defn = HarnessRegistry.with_builtins().get("mutation")
    assert defn.metadata.source == "builtin"
    assert defn.metadata.trust == "trusted"


def test_cross_references_resolve_across_registries() -> None:
    from opencontext_core.personas import PersonaRegistry
    from opencontext_core.registries.validation import validate_cross_references
    from opencontext_core.skills.registry import SkillRegistryV2

    report = validate_cross_references(
        PersonaRegistry.with_builtins().list(),
        SkillRegistryV2.with_builtins().list(),
        HarnessRegistry.with_builtins().list(),
    )
    assert report.ok is True
    assert report.checked > 0
    assert report.dangling == []


def test_dangling_reference_fails_validation() -> None:
    from opencontext_core.registries.validation import (
        CrossReferenceError,
        ensure_cross_references,
    )
    from opencontext_core.skills.definition import SkillDefinition

    bad_skill = SkillDefinition(
        id="oc-bad", tier="T2", category="Mutation", required_harnesses=["nonexistent-harness"]
    )
    with pytest.raises(CrossReferenceError):
        ensure_cross_references([], [bad_skill], HarnessRegistry.with_builtins().list())


# --- REG-CONV AC fold: harness gates are deterministic -------------------------


def test_gate_is_deterministic() -> None:
    gate = NoSecretLeakageGate()
    content = "def f():\n    return 1\n"
    first = gate.evaluate(content)
    second = gate.evaluate(content)
    assert first.status == second.status
    assert first.message == second.message
