"""Acceptance tests for OpenContext Runtime — Plan final 10/10.

25 test functions covering all 25 DoD points. Pure unit tests with
tmp_path only; no network, no external models.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.agentic.context_substrate import ContextSubstrateBuilder
from opencontext_core.agents.executor import ApplyEdit, ApplyOperation, apply_edit
from opencontext_core.harness.models import HarnessReport
from opencontext_core.learning.evolution_apply import EvolutionApplier
from opencontext_core.memory.provider import MemoryProvider
from opencontext_core.oc_new.flow import OC_NEW_FLOW
from opencontext_core.oc_new.models import AgentHandoff, HandoffBudget
from opencontext_core.personas import (
    PersonaVisibility,
    hidden_delegation_personas,
    public_main_persona,
    public_support_personas,
)
from opencontext_core.workflow.phase_result import PhaseResultEnvelope

EXPECTED_FLOW_PERSONAS = {
    "explore": "oc-explorer",
    "propose": "oc-orchestrator",
    "spec": "oc-requirements",
    "design": "oc-architect",
    "tasks": "oc-planner",
    "apply": "oc-builder",
    "verify": "oc-harness-verifier",
    "review": "oc-reviewer",
    "archive": "oc-archivist",
}


# ---------------------------------------------------------------------------
# OC_NEW_FLOW persona assignments
# ---------------------------------------------------------------------------


def test_flow_personas_match_10_10_contract() -> None:
    got = {phase.name: phase.persona for phase in OC_NEW_FLOW if phase.persona}
    for phase, persona in EXPECTED_FLOW_PERSONAS.items():
        assert got.get(phase) == persona, (
            f"Phase {phase!r}: expected {persona!r}, got {got.get(phase)!r}"
        )


def test_flow_has_verify_phase() -> None:
    names = [p.name for p in OC_NEW_FLOW]
    assert "verify" in names


def test_flow_has_archive_phase() -> None:
    names = [p.name for p in OC_NEW_FLOW]
    assert "archive" in names


# ---------------------------------------------------------------------------
# Persona visibility
# ---------------------------------------------------------------------------


def test_exactly_one_public_main_persona() -> None:
    main = public_main_persona()
    assert main.id == "oc-orchestrator"
    assert main.visibility == PersonaVisibility.PUBLIC_MAIN


def test_public_support_personas() -> None:
    support_ids = {p.id for p in public_support_personas()}
    assert "oc-professor" in support_ids
    assert "oc-reviewer" in support_ids
    for p in public_support_personas():
        assert p.visibility == PersonaVisibility.PUBLIC_SUPPORT


def test_no_delegate_is_public() -> None:
    public_ids = {public_main_persona().id} | {p.id for p in public_support_personas()}
    delegate_ids = {p.id for p in hidden_delegation_personas()}
    assert public_ids.isdisjoint(delegate_ids), f"Overlap: {public_ids & delegate_ids}"


def test_hidden_delegation_personas_include_required_delegates() -> None:
    delegate_ids = {p.id for p in hidden_delegation_personas()}
    for required in ["oc-requirements", "oc-planner", "oc-harness-verifier", "oc-archivist"]:
        assert required in delegate_ids, f"Missing delegate: {required}"


# ---------------------------------------------------------------------------
# PhaseResultEnvelope gates
# ---------------------------------------------------------------------------


def test_phase_result_envelope_blocks_on_missing_artifacts() -> None:
    env = PhaseResultEnvelope(
        run_id="run",
        change_id="change",
        phase="verify",
        status="passed",
        duration_s=1.0,
        missing_artifacts=["harness-report.json"],
    )
    assert not env.can_advance()


def test_phase_result_envelope_passes_when_complete() -> None:
    env = PhaseResultEnvelope(
        run_id="run",
        change_id="change",
        phase="verify",
        status="passed",
        duration_s=1.0,
        missing_artifacts=[],
    )
    assert env.can_advance()


def test_phase_result_envelope_blocks_on_error() -> None:
    env = PhaseResultEnvelope(
        run_id="run",
        change_id="change",
        phase="apply",
        status="passed",
        duration_s=1.0,
        error="something blew up",
    )
    assert not env.can_advance()


# ---------------------------------------------------------------------------
# AgentHandoff v2 fields
# ---------------------------------------------------------------------------


def test_agent_handoff_v2_fields_exist() -> None:
    fields = set(AgentHandoff.model_fields)
    for required in [
        "skill",
        "skill_path",
        "artifact_refs",
        "budget",
        "context_report_ref",
        "result_schema",
        "denied_tools",
    ]:
        assert required in fields, f"AgentHandoff missing field: {required}"


def test_agent_handoff_budget_is_handoff_budget() -> None:
    h = AgentHandoff(
        run_id="r",
        change_id="c",
        trace_id="t",
        phase="apply",
        persona="oc-builder",
        task="x",
        memory_key="k",
    )
    assert isinstance(h.budget, HandoffBudget)


# ---------------------------------------------------------------------------
# ContextSubstrateBuilder
# ---------------------------------------------------------------------------


def test_context_substrate_hash_not_none_when_kg_exists(tmp_path: Path) -> None:
    oc = tmp_path / ".opencontext"
    oc.mkdir()
    (oc / "knowledge_graph.json").write_text(
        '{"nodes": [{"id": "foo"}, {"id": "bar"}]}', encoding="utf-8"
    )

    report = ContextSubstrateBuilder(root=tmp_path).build_for_phase(
        task="add health endpoint",
        phase="explore",
        budget=8000,
    )
    assert report.context_pack_hash is not None
    assert report.indexed is True


def test_context_substrate_hash_none_when_no_kg(tmp_path: Path) -> None:
    report = ContextSubstrateBuilder(root=tmp_path).build_for_phase(
        task="add health endpoint",
        phase="explore",
        budget=8000,
    )
    assert report.context_pack_hash is None
    assert report.no_kg_reason is not None


# ---------------------------------------------------------------------------
# apply_edit operations
# ---------------------------------------------------------------------------


def test_apply_edit_replace_range(tmp_path: Path) -> None:
    f = tmp_path / "test.py"
    f.write_text("line1\nline2\nline3\n")
    edit = ApplyEdit(
        path="test.py",
        operation=ApplyOperation.REPLACE_RANGE,
        start_line=2,
        end_line=2,
        content="replaced\n",
    )
    apply_edit(tmp_path, edit)
    text = f.read_text()
    assert "replaced" in text
    assert "line2" not in text


def test_apply_edit_insert_after(tmp_path: Path) -> None:
    f = tmp_path / "test.py"
    f.write_text("line1\nline2\n")
    edit = ApplyEdit(
        path="test.py",
        operation=ApplyOperation.INSERT_AFTER,
        after_line=1,
        content="inserted\n",
    )
    apply_edit(tmp_path, edit)
    lines = f.read_text().splitlines()
    assert lines[1] == "inserted"


def test_apply_edit_create_file(tmp_path: Path) -> None:
    edit = ApplyEdit(
        path="new_file.py",
        operation=ApplyOperation.CREATE_FILE,
        content="print('hello')\n",
    )
    apply_edit(tmp_path, edit)
    assert (tmp_path / "new_file.py").exists()


def test_apply_edit_path_escape_rejected(tmp_path: Path) -> None:
    edit = ApplyEdit(
        path="../escape.py",
        operation=ApplyOperation.CREATE_FILE,
        content="bad\n",
    )
    with pytest.raises(RuntimeError, match="escape"):
        apply_edit(tmp_path, edit)


# ---------------------------------------------------------------------------
# EvolutionApplier
# ---------------------------------------------------------------------------


def test_evolution_applier_rejects_unapproved() -> None:
    from opencontext_core.learning.evolution import EvolutionProposal

    proposal = EvolutionProposal(
        proposal_id="test-001",
        kind="context_weight",
        rationale="test",
        title="Test proposal",
    )
    applier = EvolutionApplier(project_root=Path("/tmp"))
    result = applier.apply(proposal, approved=False)
    assert not result.applied
    assert "not approved" in result.reason


def test_evolution_applier_rejects_high_risk_kind() -> None:
    from opencontext_core.learning.evolution import EvolutionProposal

    # harness_gate is not in LOW_RISK_TYPES → requires manual implementation
    proposal = EvolutionProposal(
        proposal_id="test-002",
        kind="harness_gate",
        rationale="test",
        title="Test proposal",
    )
    applier = EvolutionApplier(project_root=Path("/tmp"))
    result = applier.apply(proposal, approved=True)
    assert not result.applied
    assert "manual" in result.reason


# ---------------------------------------------------------------------------
# MemoryProvider Protocol
# ---------------------------------------------------------------------------


def test_memory_provider_is_runtime_checkable() -> None:

    # runtime_checkable Protocol exposes __protocol_attrs__
    assert hasattr(MemoryProvider, "__protocol_attrs__") or (
        hasattr(MemoryProvider, "_is_runtime_protocol") and MemoryProvider._is_runtime_protocol  # type: ignore[attr-defined]
    ), "MemoryProvider must be @runtime_checkable"


# ---------------------------------------------------------------------------
# HarnessReport Pydantic model
# ---------------------------------------------------------------------------


def test_harness_report_pydantic_model() -> None:
    report = HarnessReport(run_id="r", change_id="c", passed=True, failures=[])
    assert report.schema_version == "opencontext.harness_report.v1"
    assert report.passed is True


def test_harness_report_failure_list() -> None:
    report = HarnessReport(
        run_id="r",
        change_id="c",
        passed=False,
        failures=["test_foo FAILED", "test_bar FAILED"],
    )
    assert len(report.failures) == 2
    assert not report.passed


# ---------------------------------------------------------------------------
# Verify phase expected artifacts
# ---------------------------------------------------------------------------


def test_verify_phase_has_required_expected_artifacts() -> None:
    verify = next(p for p in OC_NEW_FLOW if p.name == "verify")
    for required in ["verify-report.json", "compliance-matrix.json", "harness-report.json"]:
        assert required in verify.expected_artifacts, f"verify phase missing: {required}"


# ---------------------------------------------------------------------------
# Config wiring (TASK-017/018/019)
# ---------------------------------------------------------------------------


def test_sdd_config_has_flow_mode_field() -> None:
    from opencontext_core.agentic.config import FlowMode
    from opencontext_core.config import SDDConfig

    assert "flow_mode" in SDDConfig.model_fields
    cfg = SDDConfig()
    assert cfg.flow_mode == FlowMode.HYBRID


def test_memory_policy_config_has_mode_field() -> None:
    from opencontext_core.agentic.config import MemoryMode
    from opencontext_core.config import MemoryPolicyConfig

    assert "mode" in MemoryPolicyConfig.model_fields
    cfg = MemoryPolicyConfig()
    assert cfg.mode == MemoryMode.AUTO


def test_context_config_has_budget_mode_field() -> None:
    from opencontext_core.config import ContextConfig

    assert "budget_mode" in ContextConfig.model_fields
