"""Foundation-reuse tests (SPEC MP-011/012/013): reuse, do not duplicate."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.agentic.receipt import AgenticReceipt
from opencontext_core.agents.artifact_store import ArtifactStore, OpenSpecStore
from opencontext_core.context.planning.risk import (
    RiskClassifier as ContextRiskClassifier,
)
from opencontext_core.planning import program as program_module
from opencontext_core.planning import risk as planning_risk
from opencontext_core.planning.program import MetaPlanner
from opencontext_core.verify.compliance import ComplianceMatrix


def test_convergence_map_builds_on_compliance_matrix() -> None:
    # ConvergenceMap reuses the shipped ComplianceMatrix primitive (no parallel model).
    plan = MetaPlanner().build(
        intent="reuse compliance", requirements=["R1", "R2"], persist=False
    )
    matrix = plan.convergence.to_compliance_matrix()
    assert isinstance(matrix, ComplianceMatrix)
    assert {e.requirement_id for e in matrix.iter_entries()} == {"R1", "R2"}
    # program.py imports the reused primitive directly.
    assert program_module.ComplianceMatrix is ComplianceMatrix


def test_planning_risk_reuses_context_risk_classifier() -> None:
    # planning/risk.py imports and re-exports the single RiskClassifier.
    assert planning_risk.RiskClassifier is ContextRiskClassifier


def test_plan_receipt_is_agentic_receipt(tmp_path: Path) -> None:
    planner = MetaPlanner(store=OpenSpecStore(root=tmp_path))
    planner.build(intent="receipt reuse", requirements=["R1"], persist=True)
    assert isinstance(planner.last_receipt, AgenticReceipt)
    # No new receipt model: it comes from agentic/receipt.py.
    assert type(planner.last_receipt).__module__ == "opencontext_core.agentic.receipt"


def test_persistence_uses_existing_artifact_store(tmp_path: Path) -> None:
    store = OpenSpecStore(root=tmp_path)
    # OpenSpecStore is the shipped ArtifactStore; no new store class is introduced.
    assert isinstance(store, ArtifactStore)
    assert program_module.ArtifactStore is ArtifactStore
    planner = MetaPlanner(store=store)
    planner.build(intent="store reuse", requirements=["R1"], persist=True)
    assert (tmp_path / "changes").exists()
