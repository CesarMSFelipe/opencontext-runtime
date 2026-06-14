"""Tests for harness gate implementations."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.harness.gates import (
    ApprovalRequiredForWritesGate,
    ArtifactPersistedGate,
    ContextPackCreatedGate,
    IncludedSourcesPresentGate,
    NoHighRiskExportsGate,
    NoSecretLeakageGate,
    OmissionsRecordedGate,
    ProjectIndexExistsGate,
    ProviderPolicyPassedGate,
    ReviewArtifactCreatedGate,
    SecurityScanPassedGate,
    TokenBudgetGate,
    TraceIdCreatedGate,
)
from opencontext_core.harness.models import BudgetMode, GateStatus, PhaseLedger


class TestProjectIndexExistsGate:
    def test_passes_when_manifest_exists(self, tmp_path: Path) -> None:
        manifest = tmp_path / ".storage" / "opencontext" / "project_manifest.json"
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


class TestNoSecretLeakageGate:
    def test_passes_on_clean_content(self) -> None:
        gate = NoSecretLeakageGate()
        result = gate.evaluate("This is normal content without secrets.")
        assert result.status == GateStatus.PASSED

    def test_message_on_pass(self) -> None:
        gate = NoSecretLeakageGate()
        result = gate.evaluate("clean text")
        assert "sensitive" in result.message.lower() or "detected" in result.message.lower()


class TestIncludedSourcesPresentGate:
    def test_warning_when_source_missing(self) -> None:
        gate = IncludedSourcesPresentGate()
        result = gate.evaluate(
            required_sources=["AuthMiddleware"],
            included_sources={"OtherClass"},
        )
        assert result.status == GateStatus.WARNING
        assert "AuthMiddleware" in result.message

    def test_passes_when_all_present(self) -> None:
        gate = IncludedSourcesPresentGate()
        result = gate.evaluate(
            required_sources=["AuthMiddleware"],
            included_sources={"AuthMiddleware", "OtherClass"},
        )
        assert result.status == GateStatus.PASSED


class TestOmissionsRecordedGate:
    def test_warning_when_omitted_without_recording(self) -> None:
        gate = OmissionsRecordedGate()
        result = gate.evaluate(omitted_count=5, omissions_recorded=0)
        assert result.status == GateStatus.WARNING

    def test_passes_when_omissions_recorded(self) -> None:
        gate = OmissionsRecordedGate()
        result = gate.evaluate(omitted_count=5, omissions_recorded=5)
        assert result.status == GateStatus.PASSED

    def test_passes_when_nothing_omitted(self) -> None:
        gate = OmissionsRecordedGate()
        result = gate.evaluate(omitted_count=0, omissions_recorded=0)
        assert result.status == GateStatus.PASSED


class TestProviderPolicyPassedGate:
    def test_warning_for_external_provider(self) -> None:
        gate = ProviderPolicyPassedGate()
        result = gate.evaluate(provider="some-external", is_external=True, items_count=10)
        assert result.status == GateStatus.WARNING

    def test_passes_for_local_provider(self) -> None:
        gate = ProviderPolicyPassedGate()
        result = gate.evaluate(provider="local", is_external=False, items_count=10)
        assert result.status == GateStatus.PASSED

    def test_passes_when_no_items(self) -> None:
        gate = ProviderPolicyPassedGate()
        result = gate.evaluate(provider="external", is_external=True, items_count=0)
        assert result.status == GateStatus.PASSED


class TestApprovalRequiredForWritesGate:
    def test_fails_strict_without_approval(self) -> None:
        gate = ApprovalRequiredForWritesGate()
        result = gate.evaluate(budget_mode="strict", approved=False)
        assert result.status == GateStatus.FAILED

    def test_passes_strict_with_approval(self) -> None:
        gate = ApprovalRequiredForWritesGate()
        result = gate.evaluate(budget_mode="strict", approved=True)
        assert result.status == GateStatus.PASSED

    def test_passes_non_strict_without_approval(self) -> None:
        gate = ApprovalRequiredForWritesGate()
        result = gate.evaluate(budget_mode="warn", approved=False)
        assert result.status == GateStatus.PASSED


class TestNoHighRiskExportsGate:
    def test_fails_confidential_plus_external(self) -> None:
        gate = NoHighRiskExportsGate()
        result = gate.evaluate(has_confidential=True, is_external_provider=True)
        assert result.status == GateStatus.FAILED

    def test_passes_confidential_local(self) -> None:
        gate = NoHighRiskExportsGate()
        result = gate.evaluate(has_confidential=True, is_external_provider=False)
        assert result.status == GateStatus.PASSED

    def test_passes_no_confidential_external(self) -> None:
        gate = NoHighRiskExportsGate()
        result = gate.evaluate(has_confidential=False, is_external_provider=True)
        assert result.status == GateStatus.PASSED


class TestReviewArtifactCreatedGate:
    def test_fails_when_no_review_json(self, tmp_path: Path) -> None:
        gate = ReviewArtifactCreatedGate()
        result = gate.evaluate(run_dir=tmp_path)
        assert result.status == GateStatus.FAILED

    def test_passes_when_review_json_exists(self, tmp_path: Path) -> None:
        (tmp_path / "review.json").write_text("{}")
        gate = ReviewArtifactCreatedGate()
        result = gate.evaluate(run_dir=tmp_path)
        assert result.status == GateStatus.PASSED
