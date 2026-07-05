"""Shared vocabulary for the architecture & code-quality enforcement package.

Every other ``quality.*`` module imports its types from here so the type names
cannot drift. This module is pure stdlib dataclasses, deterministic, and makes
zero model calls. It reuses the existing ``ci_checks`` severity/status enums
(no duplicate severity enum) and the harness ``GateStatus`` so the quality gate,
the CLI exit path, and the CI-check report all speak one schema.

Design invariants:

* ``HealthScore.score`` is an INTEGER in ``[0, 10000]`` (basis points) so
  equality and diff are exact and deterministic — never a float.
* ``finding_key`` is the SINGLE source of the ratchet/dedupe key; both
  ``baseline.py`` and ``evaluator.py`` call it (never reimplement it).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from opencontext_core.harness.models import GateStatus
from opencontext_core.quality.ci_checks import CheckResult, CheckSeverity, CheckStatus

# Reuse ci_checks.CheckSeverity as the canonical severity. Alias for readability:
# info | warning | error | critical
Severity = CheckSeverity


@dataclass(frozen=True)
class Finding:
    """A single architecture/language/test quality finding.

    ``file`` is always a project-relative POSIX path (never an absolute path and
    never a backslash path) so the ratchet key is portable across platforms.
    ``symbol`` is set when the finding is symbol-scoped (god-file / complexity).
    """

    rule: str  # e.g. 'max_cycles', 'no_god_files', 'layers', 'max_cc', 'ruff', 'tool_missing'
    severity: CheckSeverity
    message: str
    file: str | None = None  # project-relative POSIX path
    line: int | None = None
    symbol: str | None = None  # qualified symbol name when symbol-scoped
    suggestion: str | None = None
    category: str = "architecture"  # 'architecture' | 'language' | 'tests'
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuleVerdict:
    """The pass/fail outcome of a single rule, with its supporting findings."""

    rule: str
    status: CheckStatus  # passed | failed | skipped | error
    severity: CheckSeverity
    findings: tuple[Finding, ...] = ()
    message: str = ""


@dataclass(frozen=True)
class QualityMetrics:
    """Raw, explainable signals that feed HealthScore + the baseline diff.

    Every field is a plain ``int`` so the whole structure round-trips through
    JSON losslessly and the health score stays integer-exact.
    """

    cycles: int = 0  # count of SCCs with >1 node (or a self-loop)
    god_files: int = 0  # count of files over the god threshold
    max_cc: int = 0  # highest cyclomatic complexity seen
    max_in_degree: int = 0  # worst fan-in (coupling)
    max_out_degree: int = 0  # worst fan-out
    boundary_violations: int = 0
    duplication: int = 0  # count of near-duplicate function pairs/clusters in scope
    max_depth: int = 0  # deepest DIRECTORY nesting among changed files
    max_nesting: int = 0  # deepest CODE block-nesting among in-scope functions
    node_count: int = 0  # graph size (for normalization context)
    edge_count: int = 0
    # Distribution/balance signal ("equality"): Gini of per-file LOC in basis
    # points, 0 = perfectly even, 10000 = maximally concentrated. REPORT-ONLY —
    # surfaced for explainability but NOT wired into the health penalty formula.
    loc_gini_bp: int = 0

    def as_dict(self) -> dict[str, int]:
        """Serialize to a plain ``{name: int}`` dict (stable key order)."""
        return {
            "cycles": self.cycles,
            "god_files": self.god_files,
            "max_cc": self.max_cc,
            "max_in_degree": self.max_in_degree,
            "max_out_degree": self.max_out_degree,
            "boundary_violations": self.boundary_violations,
            "duplication": self.duplication,
            "max_depth": self.max_depth,
            "max_nesting": self.max_nesting,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "loc_gini_bp": self.loc_gini_bp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> QualityMetrics:
        """Rebuild from a dict; unknown keys are ignored, missing keys default to 0.

        Values are coerced to ``int`` so a JSON float (e.g. ``3.0``) round-trips
        cleanly back to an integer signal.
        """
        return cls(
            cycles=int(d.get("cycles", 0)),
            god_files=int(d.get("god_files", 0)),
            max_cc=int(d.get("max_cc", 0)),
            max_in_degree=int(d.get("max_in_degree", 0)),
            max_out_degree=int(d.get("max_out_degree", 0)),
            boundary_violations=int(d.get("boundary_violations", 0)),
            duplication=int(d.get("duplication", 0)),
            max_depth=int(d.get("max_depth", 0)),
            max_nesting=int(d.get("max_nesting", 0)),
            node_count=int(d.get("node_count", 0)),
            edge_count=int(d.get("edge_count", 0)),
            loc_gini_bp=int(d.get("loc_gini_bp", 0)),
        )


@dataclass(frozen=True)
class HealthScore:
    """An integer health score plus its explainable per-signal penalty breakdown.

    ``score`` is in ``[0, 10000]`` basis points (10000 == perfect). ``components``
    maps each signal name to the penalty it contributed, so the one-line summary
    and the trace can show exactly WHY the score moved.
    """

    score: int  # 0..10000 integer (see health_score formula)
    metrics: QualityMetrics
    components: dict[str, int]  # per-signal penalty breakdown for explainability

    def delta(self, other: HealthScore) -> int:
        """``self.score - other.score`` — positive means improved vs ``other``."""
        return self.score - other.score


@dataclass(frozen=True)
class QualityReport:
    """The single verdict object returned by the evaluator.

    Consumed by the harness gate, the CLI exit path, the MCP tool, and the
    CI-check shim — one engine, one report shape.
    """

    status: GateStatus  # PASSED | WARNING | FAILED | SKIPPED (maps to gate + CLI exit)
    findings: tuple[Finding, ...]
    verdicts: tuple[RuleVerdict, ...]
    health: HealthScore
    baseline_health: HealthScore | None = None  # set when diffed against a snapshot
    new_findings: tuple[Finding, ...] = ()  # ratchet: findings not in baseline
    skipped: tuple[str, ...] = ()  # rules/tools that did not run (degrade honestly)
    summary: str = ""  # one-line delta, e.g. 'architecture 9120 -> 9180 (up)'

    @property
    def exit_code(self) -> int:
        """0 if the status is non-blocking (PASSED/SKIPPED), else 1."""
        return 0 if self.status.is_ok else 1

    def to_report_dict(self) -> dict[str, Any]:
        """Render a ``ci_checks.generate_report``-compatible report dict.

        Shape::

            {
              'summary': {total_checks, passed, failed, warnings, errors, success},
              'results': [{check, status, severity, message, file, line, suggestion}, ...],
              'health': {score, delta, components, metrics},
              'delta': int,
            }

        The summary counters are derived from the rule verdicts (one row per
        rule) so the numbers match the ``ci-check run`` schema; ``results`` rows
        come from the individual findings.
        """
        total_checks = len(self.verdicts)
        passed = sum(1 for v in self.verdicts if v.status == CheckStatus.PASSED)
        failed = sum(
            1 for v in self.verdicts if v.status in (CheckStatus.FAILED, CheckStatus.ERROR)
        )

        warnings = 0
        errors = 0
        results: list[dict[str, Any]] = []
        for f in self.findings:
            if f.severity in (CheckSeverity.ERROR, CheckSeverity.CRITICAL):
                errors += 1
            elif f.severity == CheckSeverity.WARNING:
                warnings += 1
            results.append(
                {
                    "check": f.rule,
                    "status": CheckStatus.FAILED.value,
                    "severity": f.severity.value,
                    "message": f.message,
                    "file": f.file,
                    "line": f.line,
                    "suggestion": f.suggestion,
                }
            )

        delta = self.health.delta(self.baseline_health) if self.baseline_health is not None else 0
        applicable = passed + failed
        status = "not_applicable" if applicable == 0 else self.status.value
        # Coherent Quality Result Fields (spec ahe-010-quality-semantics):
        # ``success`` claims a real pass only when at least one rule RAN (so the
        # verdict is grounded in measurement) AND zero rules failed. A verdict
        # derived from zero verdicts (``applicable == 0``) cannot honestly claim
        # success — nothing was measured, so ``success`` is False. This is what
        # blocks the contradictory "not_applicable + success=True" surface
        # where nothing ran but the gate reads as green.
        success = applicable > 0 and failed == 0

        return {
            "status": status,
            "summary": {
                "total_checks": total_checks,
                "passed": passed,
                "failed": failed,
                "warnings": warnings,
                "errors": errors,
                "success": success,
                "status": status,
            },
            "results": results,
            "health": {
                "score": self.health.score,
                "delta": delta,
                "components": dict(self.health.components),
                "metrics": self.health.metrics.as_dict(),
            },
            "delta": delta,
        }


# --- shared helpers (canonical; every module reuses these, no re-impl) ---


def finding_key(rule: str, file: str | None, symbol_or_line: str | int | None) -> str:
    """``sha1(rule + '|' + normalized_file + '|' + bucket)`` — the ratchet key.

    Used by the baseline diff and finding dedupe. The file component is
    normalized to POSIX (backslash -> slash) so the key is identical across
    platforms; the bucket is the symbol name (preferred) or the line number.
    """
    normalized_file = (file or "").replace(chr(92), "/")
    bucket = symbol_or_line if symbol_or_line is not None else ""
    raw = f"{rule}|{normalized_file}|{bucket}"
    return hashlib.sha1(raw.encode()).hexdigest()


def to_check_result(f: Finding) -> CheckResult:
    """Convert a ``Finding`` into a ``ci_checks.CheckResult`` (rule -> check_name).

    Shared row type so the ``ci-check`` report and the gate emit one schema.
    A Finding always represents a violation, so the status is FAILED.
    """
    return CheckResult(
        check_name=f.rule,
        status=CheckStatus.FAILED,
        severity=f.severity,
        message=f.message,
        file=f.file,
        line=f.line,
        suggestion=f.suggestion,
    )


def to_gate_status(verdicts: tuple[RuleVerdict, ...]) -> GateStatus:
    """Reduce rule verdicts to a single gate status.

    Any error/critical finding (or an errored verdict) -> FAILED; otherwise any
    warning -> WARNING; otherwise PASSED. A verdict's own status takes part too:
    a ``CheckStatus.ERROR`` verdict is treated as blocking.
    """
    has_error = False
    has_warning = False
    for v in verdicts:
        if v.status == CheckStatus.ERROR:
            has_error = True
        if v.severity in (CheckSeverity.ERROR, CheckSeverity.CRITICAL):
            if v.status not in (CheckStatus.PASSED, CheckStatus.SKIPPED):
                has_error = True
        if v.severity == CheckSeverity.WARNING:
            if v.status not in (CheckStatus.PASSED, CheckStatus.SKIPPED):
                has_warning = True
        for f in v.findings:
            if f.severity in (CheckSeverity.ERROR, CheckSeverity.CRITICAL):
                has_error = True
            elif f.severity == CheckSeverity.WARNING:
                has_warning = True

    if has_error:
        return GateStatus.FAILED
    if has_warning:
        return GateStatus.WARNING
    return GateStatus.PASSED
