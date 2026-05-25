"""Tests for harness gate implementations."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.harness.gates import (
    ArtifactPersistedGate,
    ContextPackCreatedGate,
    ProjectIndexExistsGate,
    SecurityScanPassedGate,
    TokenBudgetGate,
    TraceIdCreatedGate,
)
from opencontext_core.harness.models import BudgetMode, GateStatus, PhaseLedger


class TestProjectIndexExistsGate:
    def test_passes_when_manifest_exists(self, tmp_path: Path) -> None:
        manifest = (
            tmp_path / ".storage" / "opencontext" / "project_manifest.json"
        )
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("{}")
        gate = ProjectIndexExistsGate()
        result = gate.evaluate(tmp_path)
        assert result.status == GateStatus.PASSED

    def test_fails_when_manifest_missing(self, tmp_path: Path) -> None:
        gate = ProjectIndexExistsGate()
        result = gate.evaluate(tmp_path)
        assert result.status == GateStatus.FAILED
        assert "missing" in result.message.lower()


class TestContextPackCreatedGate:
    def test_passes_with_items(self) -> None:
        gate = ContextPackCreatedGate()
        result = gate.evaluate(included_count=5)
        assert result.status == GateStatus.PASSED

    def test_fails_when_empty(self) -> None:
        gate = ContextPackCreatedGate()
        result = gate.evaluate(included_count=0)
        assert result.status == GateStatus.FAILED

    def test_edge_one_item(self) -> None:
        gate = ContextPackCreatedGate()
        result = gate.evaluate(included_count=1)
        assert result.status == GateStatus.PASSED


class TestTraceIdCreatedGate:
    def test_passes_with_trace_id(self) -> None:
        gate = TraceIdCreatedGate()
        result = gate.evaluate(trace_id="abc-123")
        assert result.status == GateStatus.PASSED

    def test_fails_without_trace_id(self) -> None:
        gate = TraceIdCreatedGate()
        result = gate.evaluate(trace_id=None)
        assert result.status == GateStatus.FAILED

    def test_fails_with_empty_string(self) -> None:
        gate = TraceIdCreatedGate()
        result = gate.evaluate(trace_id="")
        assert result.status == GateStatus.FAILED


class TestSecurityScanPassedGate:
    def test_passes_with_no_findings(self) -> None:
        gate = SecurityScanPassedGate()
        result = gate.evaluate(findings=[])
        assert result.status == GateStatus.PASSED

    def test_warns_with_findings(self) -> None:
        gate = SecurityScanPassedGate()
        result = gate.evaluate(findings=["leak"])
        assert result.status == GateStatus.WARNING
        assert result.metadata.get("finding_count") == 1

    def test_multiple_findings(self) -> None:
        gate = SecurityScanPassedGate()
        result = gate.evaluate(findings=["a", "b", "c"])
        assert result.status == GateStatus.WARNING
        assert result.metadata.get("finding_count") == 3


class TestTokenBudgetGate:
    def test_passed_ledger(self) -> None:
        ledger = PhaseLedger(
            phase="explore",
            used_tokens=3000,
            budget_tokens=6000,
            budget_mode=BudgetMode.WARN,
        )
        gate = TokenBudgetGate()
        result = gate.evaluate(ledger)
        assert result.status == GateStatus.PASSED
        assert result.metadata["used_tokens"] == 3000

    def test_failed_ledger(self) -> None:
        ledger = PhaseLedger(
            phase="apply",
            used_tokens=15000,
            budget_tokens=12000,
            budget_mode=BudgetMode.STRICT,
            status=GateStatus.FAILED,
            message="Token budget exceeded: 15000/12000.",
        )
        gate = TokenBudgetGate()
        result = gate.evaluate(ledger)
        assert result.status == GateStatus.FAILED


class TestArtifactPersistedGate:
    def test_passes_when_path_exists(self, tmp_path: Path) -> None:
        path = tmp_path / "artifact.json"
        path.write_text("{}")
        gate = ArtifactPersistedGate()
        result = gate.evaluate(path)
        assert result.status == GateStatus.PASSED

    def test_fails_when_path_missing(self, tmp_path: Path) -> None:
        gate = ArtifactPersistedGate()
        result = gate.evaluate(tmp_path / "nonexistent.json")
        assert result.status == GateStatus.FAILED

    def test_fails_when_none(self) -> None:
        gate = ArtifactPersistedGate()
        result = gate.evaluate(None)
        assert result.status == GateStatus.FAILED
