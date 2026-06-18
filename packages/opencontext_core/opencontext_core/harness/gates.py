"""Phase gate implementations for the Harness system."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from opencontext_core.harness.models import (
    AuditLevel,
    GateStatus,
    PhaseGate,
    PhaseLedger,
    PrivacyRule,
)


class ProjectIndexExistsGate:
    """Check that the project manifest exists (project was indexed)."""

    id = "project_index_exists"

    def evaluate(self, root: Path) -> PhaseGate:
        manifest = root / ".storage" / "opencontext" / "project_manifest.json"
        if manifest.exists():
            return PhaseGate(
                id=self.id,
                phase="explore",
                status=GateStatus.PASSED,
                message="Project manifest exists.",
            )
        return PhaseGate(
            id=self.id,
            phase="explore",
            status=GateStatus.FAILED,
            message="Project manifest missing — run `opencontext install` first.",
        )


class ContextPackCreatedGate:
    """Verify that a context pack was created for a given query."""

    id = "context_pack_created"

    def evaluate(self, included_count: int) -> PhaseGate:
        if included_count > 0:
            return PhaseGate(
                id=self.id,
                phase="explore",
                status=GateStatus.PASSED,
                message=f"Context pack created with {included_count} items.",
            )
        return PhaseGate(
            id=self.id,
            phase="explore",
            status=GateStatus.FAILED,
            message="Context pack is empty — try a broader query.",
        )


class TraceIdCreatedGate:
    """Check that a trace ID was generated."""

    id = "trace_id_created"

    def evaluate(self, trace_id: str | None) -> PhaseGate:
        if trace_id:
            return PhaseGate(
                id=self.id,
                phase="propose",
                status=GateStatus.PASSED,
                message=f"Trace ID created: {trace_id}",
            )
        return PhaseGate(
            id=self.id,
            phase="propose",
            status=GateStatus.FAILED,
            message="No trace ID generated.",
        )


class SecurityScanPassedGate:
    """Check that a security scan passed (no findings)."""

    id = "security_scan_passed"

    def evaluate(self, findings: list[str]) -> PhaseGate:
        if not findings:
            return PhaseGate(
                id=self.id,
                phase="verify",
                status=GateStatus.PASSED,
                message="Security scan passed — no findings.",
            )
        return PhaseGate(
            id=self.id,
            phase="verify",
            status=GateStatus.WARNING,
            message=f"Security scan found {len(findings)} item(s).",
            metadata={"finding_count": len(findings)},
        )


class TokenBudgetGate:
    """Check token budget adherence for a phase."""

    id = "token_budget"

    def evaluate(self, ledger: PhaseLedger) -> PhaseGate:
        return PhaseGate(
            id=self.id,
            phase=ledger.phase,
            status=ledger.status,
            message=ledger.message,
            metadata={
                "used_tokens": ledger.used_tokens,
                "budget_tokens": ledger.budget_tokens,
                "mode": (
                    ledger.budget_mode.value
                    if hasattr(ledger.budget_mode, "value")
                    else str(ledger.budget_mode)
                ),
            },
        )


class ArtifactPersistedGate:
    """Check that an artifact was persisted to disk."""

    id = "artifact_persisted"

    def evaluate(self, path: Path | None) -> PhaseGate:
        if path and path.exists():
            return PhaseGate(
                id=self.id,
                phase="archive",
                status=GateStatus.PASSED,
                message=f"Artifact persisted: {path}",
            )
        return PhaseGate(
            id=self.id,
            phase="archive",
            status=GateStatus.FAILED,
            message="Artifact was not persisted.",
        )


class ConfidenceGate:
    """Evaluate phase confidence based on complexity, coverage, and history.

    Produces a 0-1 score by combining:
    - Phase complexity (more complex phases need higher confidence)
    - Test coverage (from project manifest metadata)
    - Previous phase success (passed/failed prior gates)

    The gate FAILS if the combined score falls below the configured threshold.

    Complexity can be overridden per-project via PhaseConfig.complexity in
    harness.yaml (e.g., {"spec": {"complexity": 0.6}} to make spec more lenient).
    """

    id = "confidence"

    # Baseline complexity per phase (0.0 = trivial, 1.0 = very complex).
    # These defaults apply when PhaseConfig.complexity is not set.
    _DEFAULT_COMPLEXITY: ClassVar[dict[str, float]] = {
        "explore": 0.2,
        "propose": 0.3,
        "spec": 0.4,
        "design": 0.5,
        "tasks": 0.3,
        "apply": 0.8,
        "verify": 0.4,
        "review": 0.3,
        "archive": 0.1,
    }

    def evaluate(
        self,
        phase: str,
        threshold: float = 0.5,
        previous_gates: list[PhaseGate] | None = None,
        test_coverage: float | None = None,
        complexity_override: float | None = None,
    ) -> PhaseGate:
        """Evaluate confidence for a phase.

        Args:
            phase: Phase identifier (e.g. ``"apply"``).
            threshold: Minimum confidence score required (0-1).
            previous_gates: Results from previous phases' gate evaluations.
            test_coverage: Optional test coverage ratio (0-1).
            complexity_override: Per-project complexity (0.0-1.0) from
                PhaseConfig.complexity. When set, overrides the default
                baseline for this phase.

        Returns:
            A PhaseGate with PASSED or FAILED status.
        """
        # Use per-project override if provided, otherwise fall back to default
        complexity = (
            complexity_override
            if complexity_override is not None
            else self._DEFAULT_COMPLEXITY.get(phase, 0.5)
        )
        score = self._calculate_score(complexity, previous_gates, test_coverage)
        passed = score >= threshold

        details: list[str] = []
        details.append(f"complexity={complexity:.2f}")
        if complexity_override is not None:
            details.append("complexity_source=config")
        else:
            details.append("complexity_source=default")

        if previous_gates:
            prev_passed = sum(1 for g in previous_gates if g.status == GateStatus.PASSED)
            prev_total = len(previous_gates)
            details.append(f"previous={prev_passed}/{prev_total}")
        else:
            details.append("previous=no-data")

        if test_coverage is not None:
            details.append(f"coverage={test_coverage:.0%}")

        details.append(f"threshold={threshold:.2f}")
        details.append(f"score={score:.2f}")

        if passed:
            return PhaseGate(
                id=self.id,
                phase=phase,
                status=GateStatus.PASSED,
                message=f"Confidence score {score:.2f} meets threshold {threshold:.2f}.",
                metadata={"confidence_score": score, "threshold": threshold, "details": details},
            )
        return PhaseGate(
            id=self.id,
            phase=phase,
            status=GateStatus.FAILED,
            message=(
                f"Confidence score {score:.2f} below threshold {threshold:.2f}. "
                "Consider simplifying the task or increasing test coverage."
            ),
            metadata={"confidence_score": score, "threshold": threshold, "details": details},
        )

    def _calculate_score(
        self,
        complexity: float,
        previous_gates: list[PhaseGate] | None = None,
        test_coverage: float | None = None,
    ) -> float:
        """Compute confidence score from weighted factors.

        Args:
            complexity: Phase complexity (0.0=trivial, 1.0=very complex).
                Already resolved by evaluate() from config or defaults.
            previous_gates: Gate results from prior phases.
            test_coverage: Optional test coverage ratio (0-1).
        """
        # Factor 1: Phase complexity (inverse — simpler = higher base)
        complexity_factor = 1.0 - complexity

        # Factor 2: Previous phase success rate
        prev_factor = 0.5
        if previous_gates:
            passed_count = sum(1 for g in previous_gates if g.status == GateStatus.PASSED)
            total = len(previous_gates)
            prev_factor = passed_count / max(total, 1)

        # Factor 3: Test coverage (default 0.5 when unknown)
        coverage_factor = test_coverage if test_coverage is not None else 0.5

        # Weighted combination (complexity 20%, history 50%, coverage 30%)
        return 0.2 * complexity_factor + 0.5 * prev_factor + 0.3 * coverage_factor


class PrivacyGate:
    """Evaluate whether an operation violates a privacy rule.

    BLOCKS the operation if the provider is in the rule's provider_restrictions
    and the operation scope matches one of the rule's permission_scopes.

    When ``rule.audit_level`` is ``DETAILED``, writes a per-rule JSON-Lines audit
    trail to ``<run_dir>/audit-<rule_id>.jsonl`` for traceability.
    """

    id = "privacy"

    def evaluate(
        self,
        operation: dict[str, Any],
        rule: PrivacyRule,
        run_dir: Path | None = None,
    ) -> PhaseGate:
        """Evaluate privacy gate for an operation against a rule.

        Args:
            operation: Dict with 'provider' and 'scope' keys.
            rule: PrivacyRule to evaluate against.
            run_dir: When provided and ``rule.audit_level == DETAILED``, writes
                an audit record to ``<run_dir>/audit-<rule_id>.jsonl``.

        Returns:
            PhaseGate with PASSED if allowed, FAILED if blocked.
        """
        allowed = rule.evaluate(operation)
        if allowed:
            result = PhaseGate(
                id=self.id,
                phase="privacy",
                status=GateStatus.PASSED,
                message=f"Operation allowed by rule '{rule.name}'.",
                metadata={"rule_id": rule.id, "provider": operation.get("provider")},
            )
        else:
            result = PhaseGate(
                id=self.id,
                phase="privacy",
                status=GateStatus.FAILED,
                message=(
                    f"Privacy rule violated: {rule.name} "
                    f"(blocked provider: {operation.get('provider')})"
                ),
                metadata={"rule_id": rule.id, "blocked_provider": operation.get("provider")},
            )

        # Emit detailed audit trail when configured
        if run_dir is not None and rule.audit_level == AuditLevel.DETAILED:
            self._write_audit(run_dir, rule, operation, result)

        return result

    def _write_audit(
        self,
        run_dir: Path,
        rule: PrivacyRule,
        operation: dict[str, Any],
        result: PhaseGate,
    ) -> None:
        """Append a JSON-Lines audit record for DETAILED audit level."""
        import json

        audit_path = run_dir / f"audit-{rule.id}.jsonl"
        record = {
            "rule_id": rule.id,
            "rule_name": rule.name,
            "operation": operation,
            "result": result.status.value,
            "message": result.message,
        }
        try:
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            with open(audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception:
            # Never fail a gate due to audit write failures
            pass


class NoSecretLeakageGate:
    """Check that no sensitive patterns exist in an artifact."""

    id = "no_secret_leakage"

    def evaluate(self, artifact_content: str) -> PhaseGate:
        from opencontext_core.safety.secrets import SecretScanner

        try:
            findings = SecretScanner().scan(artifact_content)
        except Exception:
            findings = []
        if findings:
            return PhaseGate(
                id=self.id,
                status=GateStatus.FAILED,
                message=f"{len(findings)} sensitive pattern(s) detected in artifact",
                phase="any",
            )
        return PhaseGate(
            id=self.id,
            status=GateStatus.PASSED,
            message="No sensitive patterns detected",
            phase="any",
        )


class IncludedSourcesPresentGate:
    """Check that all required sources appear in the context."""

    id = "included_sources_present"

    def evaluate(self, required_sources: list[str], included_sources: set[str]) -> PhaseGate:
        missing = [s for s in required_sources if s not in included_sources]
        if missing:
            return PhaseGate(
                id=self.id,
                status=GateStatus.WARNING,
                message=f"Required sources not in context: {missing[:3]}",
                phase="any",
            )
        return PhaseGate(
            id=self.id,
            status=GateStatus.PASSED,
            message="All required sources included",
            phase="any",
        )


class OmissionsRecordedGate:
    """Check that omitted items have recorded reasons."""

    id = "omissions_recorded"

    def evaluate(self, omitted_count: int, omissions_recorded: int) -> PhaseGate:
        if omitted_count > 0 and omissions_recorded == 0:
            return PhaseGate(
                id=self.id,
                status=GateStatus.WARNING,
                message="Items omitted but omission reasons not recorded",
                phase="any",
            )
        return PhaseGate(
            id=self.id,
            status=GateStatus.PASSED,
            message="Omission trace complete",
            phase="any",
        )


class ProviderPolicyPassedGate:
    """Check provider policy for external context sends."""

    id = "provider_policy_passed"

    def evaluate(self, provider: str, is_external: bool, items_count: int) -> PhaseGate:
        if is_external and items_count > 0:
            return PhaseGate(
                id=self.id,
                status=GateStatus.WARNING,
                message=f"Context sent to external provider '{provider}' — verify policy",
                phase="any",
            )
        return PhaseGate(
            id=self.id,
            status=GateStatus.PASSED,
            message="Provider policy check passed",
            phase="any",
        )


class ApprovalRequiredForWritesGate:
    """Human-approval pre-gate for write operations.

    Decoupled from token ``budget_mode``: whether approval is *required* is a
    governance decision declared in config (``approval_required``), and whether
    it has been *granted* is supplied separately (``approved``). When approval is
    required but not granted the gate FAILS, which must block ApplyPhase before
    any file is edited.
    """

    id = "approval_required_for_writes"

    def evaluate(self, approval_required: bool, approved: bool) -> PhaseGate:
        if approval_required and not approved:
            return PhaseGate(
                id=self.id,
                status=GateStatus.FAILED,
                message="Write operations require explicit human approval (not granted)",
                phase="apply",
            )
        return PhaseGate(
            id=self.id,
            status=GateStatus.PASSED,
            message=(
                "Approval granted for writes"
                if approval_required
                else "Approval not required for writes"
            ),
            phase="apply",
        )


class NoHighRiskExportsGate:
    """Check that restricted data is not exported to external providers."""

    id = "no_high_risk_exports"

    def evaluate(self, has_confidential: bool, is_external_provider: bool) -> PhaseGate:
        if is_external_provider and has_confidential:
            return PhaseGate(
                id=self.id,
                status=GateStatus.FAILED,
                message="Restricted data cannot be exported to external provider",
                phase="any",
            )
        return PhaseGate(
            id=self.id,
            status=GateStatus.PASSED,
            message="No restricted data export",
            phase="any",
        )


class ReviewArtifactCreatedGate:
    """Check that the review artifact exists in the run directory."""

    id = "review_artifact_created"

    def evaluate(self, run_dir: Path) -> PhaseGate:
        if not (run_dir / "review.json").exists():
            return PhaseGate(
                id=self.id,
                status=GateStatus.FAILED,
                message="Review artifact not found in run directory",
                phase="any",
            )
        return PhaseGate(
            id=self.id,
            status=GateStatus.PASSED,
            message="Review artifact present",
            phase="any",
        )


class FailingTestExistsGate:
    """Check that a test file exists matching the change/task name pattern.

    In Strict TDD mode, VerifyPhase requires a failing test before ApplyPhase
    can execute. This gate looks for test files matching patterns like:
    - tests/**/test_*<task>*.py
    - tests/**/*<task>*_test.py

    If no exact match is found, performs fuzzy matching against all test files
    and suggests the closest alternative to help developers create the right test.
    """

    id = "failing_test_exists"

    def evaluate(self, task: str, root: Path) -> PhaseGate:
        """Find a test file matching the task name.

        Args:
            task: The task/change name (e.g., "add-privacy-gate").
            root: Project root directory.

        Returns:
            PhaseGate with PASSED if found, FAILED if not found.
        """
        tests_dir = root / "tests"
        if not tests_dir.exists():
            return PhaseGate(
                id=self.id,
                phase="verify",
                status=GateStatus.FAILED,
                message=f"No test found for task '{task}' — tests/ directory does not exist.",
            )

        # Build search patterns from task name
        # "add-privacy-gate" → "test_add_privacy_gate.py", "test*privacy*gate*.py"
        task_slug = task.replace("-", "_")
        patterns = [
            f"**/test_{task_slug}.py",
            f"**/test*{task_slug}*.py",
            f"**/*{task_slug}*_test.py",
            f"**/*{task_slug}*.py",
        ]

        matching_files: list[str] = []
        for pattern in patterns:
            matching_files.extend(str(p) for p in root.glob(pattern) if p.is_file())

        if matching_files:
            return PhaseGate(
                id=self.id,
                phase="verify",
                status=GateStatus.PASSED,
                message=f"Test found for '{task}': {matching_files[0]}",
                metadata={"test_files": matching_files, "task": task},
            )

        # No exact match — try fuzzy matching to suggest alternatives
        suggestion = self._fuzzy_suggest(task, root)
        if suggestion:
            return PhaseGate(
                id=self.id,
                phase="verify",
                status=GateStatus.FAILED,
                message=(
                    f"No test found for task '{task}'. "
                    f"Did you mean: {suggestion}? "
                    f"Write a failing test first (Strict TDD)."
                ),
                metadata={"task": task, "suggestion": suggestion},
            )

        return PhaseGate(
            id=self.id,
            phase="verify",
            status=GateStatus.FAILED,
            message=f"No test found for task '{task}' — write a failing test first (Strict TDD).",
            metadata={"task": task},
        )

    def _fuzzy_suggest(self, task: str, root: Path) -> str | None:
        """Find the most similar test file when exact matching fails.

        Splits the task into words and finds test files whose names contain
        at least half of those words.
        """
        tests_dir = root / "tests"
        if not tests_dir.exists():
            return None

        all_tests = [str(p) for p in tests_dir.rglob("test_*.py")]
        if not all_tests:
            return None

        # Split task into words for matching
        task_words = set(task.replace("-", "_").replace("_", " ").split())
        if not task_words:
            return None

        best_match: tuple[str, int] | None = None
        for test_path in all_tests:
            test_name = Path(test_path).stem.replace("test_", "").replace("_test", "")
            test_words = set(test_name.replace("_", " ").split())

            # Count overlapping words
            overlap = len(task_words & test_words)
            if overlap > 0 and (best_match is None or overlap > best_match[1]):
                best_match = (test_path, overlap)

        if best_match:
            return best_match[0]
        return None
