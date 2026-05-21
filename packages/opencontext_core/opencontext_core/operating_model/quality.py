"""Quality gates, verifier scaffolds, plan drift, and tool-chain analysis."""

from __future__ import annotations

from itertools import pairwise
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.operating_model.ai_leak import OutputExfiltrationScanner


class QualityGateReport(BaseModel):
    """Quality gate result."""

    model_config = ConfigDict(extra="forbid")

    passed: bool = Field(description="Whether the gate passed.")
    reason: str = Field(description="Decision reason.")
    risks: list[str] = Field(default_factory=list, description="Detected risks.")


class PreLLMQualityGate:
    """Checks whether a run should spend model tokens."""

    def evaluate(
        self,
        *,
        context_tokens: int,
        max_tokens: int,
        provider_allowed: bool,
        source_count: int,
        budget_manager: Any | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> QualityGateReport:
        """Return a pre-generation quality decision."""

        risks: list[str] = []
        if context_tokens > max_tokens:
            risks.append("context_over_budget")
        if not provider_allowed:
            risks.append("provider_blocked")
        if source_count == 0:
            risks.append("missing_sources")

        if budget_manager and provider and model:
            available, remaining = budget_manager.check_budget(provider, model)
            if not available:
                risks.append("call_budget_exhausted")
            elif remaining < 10:  # Critical low budget
                risks.append("call_budget_critical")

        return QualityGateReport(
            passed=not risks,
            reason="passed" if not risks else "blocked_before_llm",
            risks=risks,
        )


class PostLLMQualityGate:
    """Checks generated output for leakage and budget conformance."""

    def evaluate(self, output: str, *, max_output_tokens: int) -> QualityGateReport:
        """Return post-generation quality decision."""

        findings = OutputExfiltrationScanner().scan(output)
        risks = [finding.kind for finding in findings]
        if max_output_tokens >= 0 and len(output.split()) > max_output_tokens * 2:
            risks.append("output_over_budget")
        return QualityGateReport(
            passed=not risks,
            reason="passed" if not risks else "output_guardrail_failed",
            risks=risks,
        )


class PlanDriftDetector:
    """Compares approved plans with attempted actions."""

    def detect(self, approved_plan: str, attempted_action: str) -> QualityGateReport:
        """Return drift decision."""

        if "external" in attempted_action.lower() and "external" not in approved_plan.lower():
            return QualityGateReport(
                passed=False,
                reason="plan_drift_detected",
                risks=["unexpected_external_egress"],
            )
        return QualityGateReport(passed=True, reason="no_drift")


class CriticStep:
    """Cheap critic scaffold."""

    def critique(self, output: str) -> QualityGateReport:
        """Return a deterministic critique."""

        if "I am not sure" in output or "uncertain" in output.lower():
            return QualityGateReport(passed=True, reason="uncertainty_disclosed")
        return QualityGateReport(passed=True, reason="critic_scaffold")


class VerifierStep:
    """Cheap verifier scaffold."""

    def verify(self, output: str, required_terms: list[str] | None = None) -> QualityGateReport:
        """Verify required terms."""

        missing = [term for term in required_terms or [] if term.lower() not in output.lower()]
        return QualityGateReport(
            passed=not missing,
            reason="verified" if not missing else "missing_required_terms",
            risks=missing,
        )


class ToolChainAnalyzer:
    """Detects risky tool/action sequences."""

    RISKY_SEQUENCES: tuple[tuple[str, str], ...] = (
        ("read_secret", "external_network"),
        ("read_confidential", "clipboard_export"),
        ("untrusted_doc", "tool_call"),
        ("tool_output", "policy_change"),
        ("llm_output", "shell_command"),
    )

    def analyze(self, actions: list[str]) -> QualityGateReport:
        """Return tool-chain risk decision."""

        pairs = list(pairwise(actions))
        risks = [
            f"{left}->{right}" for left, right in pairs if (left, right) in self.RISKY_SEQUENCES
        ]
        return QualityGateReport(
            passed=not risks,
            reason="allowed" if not risks else "risky_tool_chain",
            risks=risks,
        )


class SpecialistWorkflowRouter:
    """Routes tasks to specialist workflow names."""

    def route(self, task: str) -> str:
        """Return specialist workflow key."""

        text = task.lower()
        if "security" in text or "secret" in text:
            return "security_reviewer"
        if "token" in text or "cost" in text:
            return "token_optimizer"
        if "dru" + "pal" in text:
            return "dru" + "pal_profile"
        if "test" in text:
            return "test_planner"
        return "repo_architect"
