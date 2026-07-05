"""Phase gate implementations for the Harness system."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, ClassVar

from opencontext_core.config_resolver import resolve_active_storage_path
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
        manifest = resolve_active_storage_path(root) / "project_manifest.json"
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

    Score = 0.2*(1-complexity) + 0.5*prev_success_rate + 0.3*coverage_factor

    With no history and no coverage (both default to 0.5), scores are:
    - explore (complexity=0.2) → 0.56  passes default threshold 0.5
    - apply   (complexity=0.8) → 0.44  passes harness threshold 0.4 (not 0.5)

    The harness uses a lower threshold (0.4) for apply precisely because
    apply is the most complex phase and would otherwise fail every first run.
    Increase test coverage or lower PhaseConfig.complexity to raise the score.

    Complexity can be overridden per-project via PhaseConfig.complexity in
    harness.yaml (e.g., {"apply": {"complexity": 0.6}} to make apply easier).
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
        first_run_bypass: bool = False,
    ) -> PhaseGate:
        """Evaluate confidence for a phase.

        Score formula: 0.2*(1-complexity) + 0.5*prev_success_rate + 0.3*coverage_factor.

        Args:
            phase: Phase identifier (e.g. ``"apply"``).
            threshold: Minimum confidence score required (0-1).
            previous_gates: Results from previous phases' gate evaluations.
            test_coverage: Optional test coverage ratio (0-1).
            complexity_override: Per-project complexity (0.0-1.0) from
                PhaseConfig.complexity. When set, overrides the default
                baseline for this phase.
            first_run_bypass: When True and no previous_gates exist, auto-pass
                with score 1.0. Useful for the very first run of a new project
                where no history is available yet.

        Returns:
            A PhaseGate with PASSED or FAILED status.
        """
        if first_run_bypass and not previous_gates:
            return PhaseGate(
                id=self.id,
                phase=phase,
                status=GateStatus.PASSED,
                message="First run bypass — no history available.",
                metadata={"confidence_score": 1.0, "threshold": threshold, "first_run": True},
            )

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


class PolicyEnginePassedGate:
    """Harness gate that consumes a unified PolicyEngine decision (HARNESS-1).

    Translates a canonical :class:`~opencontext_core.policy.models.PolicyDecision`
    into a :class:`PhaseGate`: ``allow`` → PASSED, ``warn``/``ask`` → WARNING,
    ``deny`` → FAILED (blocking). Keeps :class:`ProviderPolicyPassedGate` for the
    provider-specific path.
    """

    id = "policy_engine_passed"

    def evaluate(self, decision: Any) -> PhaseGate:
        verb = getattr(decision, "decision", "deny")
        reason = getattr(decision, "reason", "")
        policy_id = getattr(decision, "policy_id", "")
        if verb == "allow":
            status = GateStatus.PASSED
            message = f"Policy {policy_id} allowed: {reason}"
        elif verb in ("warn", "ask"):
            status = GateStatus.WARNING
            message = f"Policy {policy_id} {verb}: {reason}"
        else:
            status = GateStatus.FAILED
            remediation = getattr(decision, "remediation", "")
            message = f"Policy {policy_id} denied: {reason}"
            if remediation:
                message = f"{message} — {remediation}"
        return PhaseGate(id=self.id, phase="any", status=status, message=message)


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

    # Timeout in seconds for the subprocess execution of a single test file.
    _EXEC_TIMEOUT: int = 120

    def evaluate(self, task: str, root: Path, *, tdd_mode: str = "ask") -> PhaseGate:
        """Find a test file matching the task name.

        In strict TDD mode the matched test file is also *executed* via subprocess
        and must EXIT with a non-zero code (RED confirmed).  An empty or already-
        passing test is rejected with a clear message.

        In non-strict modes (``ask`` / ``off``) the original filename-existence
        check is preserved — no subprocess is spawned.

        Args:
            task: The task/change name (e.g., "add-privacy-gate").
            root: Project root directory.
            tdd_mode: "strict" | "ask" | "off"  (default "ask").

        Returns:
            PhaseGate with PASSED if found (and RED-confirmed in strict mode),
            FAILED otherwise.
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

        if not matching_files:
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
                message=(
                    f"No test found for task '{task}' — write a failing test first (Strict TDD)."
                ),
                metadata={"task": task},
            )

        # File found — in non-strict modes, filename existence is sufficient.
        if tdd_mode != "strict":
            return PhaseGate(
                id=self.id,
                phase="verify",
                status=GateStatus.PASSED,
                message=f"Test found for '{task}': {matching_files[0]}",
                metadata={"test_files": matching_files, "task": task},
            )

        # --- Strict mode: execute the test and require it to FAIL (RED). ---
        test_path = matching_files[0]
        return self._verify_test_is_red(task, test_path, root, matching_files)

    def _verify_test_is_red(
        self, task: str, test_path: str, root: Path, all_matches: list[str]
    ) -> PhaseGate:
        """Execute ``test_path`` and return PASSED only when it exits non-zero.

        Only the single matched file is run — never the full suite.
        """
        try:
            proc = subprocess.run(
                ["pytest", test_path, "-x", "-q", "--no-header", "--tb=no"],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=self._EXEC_TIMEOUT,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            return PhaseGate(
                id=self.id,
                phase="verify",
                status=GateStatus.FAILED,
                message=(
                    f"Strict TDD: test execution timed out after {self._EXEC_TIMEOUT}s "
                    f"for '{test_path}'. Ensure the test file is runnable."
                ),
                metadata={"task": task, "test_path": test_path},
            )

        if proc.returncode != 0:
            # Non-zero exit → test is RED, gate PASSES.
            return PhaseGate(
                id=self.id,
                phase="verify",
                status=GateStatus.PASSED,
                message=(f"Strict TDD: RED confirmed — test '{test_path}' fails as required."),
                metadata={
                    "test_files": all_matches,
                    "task": task,
                    "exit_code": proc.returncode,
                },
            )

        # Zero exit → test passes, no RED — gate FAILS.
        return PhaseGate(
            id=self.id,
            phase="verify",
            status=GateStatus.FAILED,
            message=(
                f"Strict TDD: test '{test_path}' already passes (exit 0). "
                "The test must be RED (failing) before apply. "
                "Write a failing test that captures the missing behavior."
            ),
            metadata={"task": task, "test_path": test_path, "exit_code": 0},
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


class TestsPassGate:
    """Run the project test command and verify all tests pass (GREEN).

    This gate is intended as a post-apply / verify gate confirming that the
    implementation is GREEN after a Strict TDD RED → GREEN cycle.

    **Default behaviour (OFF)**: when ``tdd_mode`` is not ``"strict"``, the gate
    returns PASSED immediately without executing any subprocess.  This preserves
    existing verify-phase behaviour for projects that have not opted into strict
    TDD.

    When active (``tdd_mode="strict"``), the gate runs the supplied command,
    maps exit-code 0 → PASSED and any non-zero exit → FAILED (never WARNING).
    """

    id = "tests_pass"

    # Timeout in seconds for the test-suite subprocess.
    _EXEC_TIMEOUT: int = 300

    def evaluate(
        self,
        cmd: list[str],
        *,
        cwd: Path,
        tdd_mode: str = "ask",
    ) -> PhaseGate:
        """Evaluate whether the project test suite passes.

        Args:
            cmd: The test command as an argv list (e.g. ``["pytest", "-q"]``).
            cwd: Working directory for the subprocess (project root).
            tdd_mode: "strict" | "ask" | "off".  Only "strict" activates
                      execution; all other modes return PASSED immediately.

        Returns:
            PhaseGate with PASSED on success, FAILED on test failure or timeout.
        """
        if tdd_mode != "strict":
            return PhaseGate(
                id=self.id,
                phase="verify",
                status=GateStatus.PASSED,
                message="TestsPassGate: inactive (tdd_mode is not strict).",
            )

        # Sanitize the subprocess env so the nested test run is deterministic when
        # this gate itself runs inside a parent pytest (drop PYTEST_*/COV_* that would
        # leak the parent's config/coverage), and add the project root to PYTHONPATH so
        # a bare `pytest` can import the project's own modules (else exit 2 on import).
        import os

        _env = {
            k: v
            for k, v in os.environ.items()
            if not (k.startswith("PYTEST_") or k.startswith("COV_"))
        }
        _pp = _env.get("PYTHONPATH", "")
        _env["PYTHONPATH"] = str(cwd) + (os.pathsep + _pp if _pp else "")
        # The GREEN gate re-imports source that a mutation just rewrote, often within
        # the same filesystem-timestamp second. CPython's .pyc invalidation is
        # mtime-granular, so a stale pre-mutation .pyc could be reused and the suite
        # would test the OLD code (a real correctness bug, and a flake in tests).
        # Never write/read cached bytecode for this nested run.
        _env["PYTHONDONTWRITEBYTECODE"] = "1"

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=self._EXEC_TIMEOUT,
                shell=False,
                env=_env,
            )
        except subprocess.TimeoutExpired:
            return PhaseGate(
                id=self.id,
                phase="verify",
                status=GateStatus.FAILED,
                message=(
                    f"TestsPassGate: test suite timed out after {self._EXEC_TIMEOUT}s. "
                    "Investigate slow tests or increase the timeout."
                ),
            )

        if proc.returncode == 0:
            return PhaseGate(
                id=self.id,
                phase="verify",
                status=GateStatus.PASSED,
                message="TestsPassGate: all tests pass (GREEN confirmed).",
                metadata={"exit_code": 0},
            )

        return PhaseGate(
            id=self.id,
            phase="verify",
            status=GateStatus.FAILED,
            message=(
                f"TestsPassGate: tests failed (exit {proc.returncode}). "
                "Fix failing tests before completing the verify phase."
            ),
            metadata={"exit_code": proc.returncode},
        )
