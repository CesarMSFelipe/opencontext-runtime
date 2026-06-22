"""The single quality-evaluation engine: one entry point, one verdict.

``QualityEvaluator`` is the sole engine used by the harness gate, the CLI, the
MCP tool, and the CI-check shim. It composes the four producers
(:mod:`~opencontext_core.quality.architecture`,
:mod:`~opencontext_core.quality.languages`,
:mod:`~opencontext_core.quality.baseline`) plus the built-in health score into
one :class:`~opencontext_core.quality.models.QualityReport`.

Two cost tiers:

* :meth:`snapshot` runs ONLY the architecture metric passes (cycles / god-files
  / coupling / depth) over the whole graph — no language subprocesses, no model
  — so it is fast and token-free. It is the explore/verify baseline path.
* :meth:`evaluate` is the full check: architecture findings + the language tool
  subprocesses + the ratchet diff + the status mapping. Still zero model calls.

Design invariants (enforced by the tests):

* The entire check path is **deterministic** — the same inputs always produce
  byte-identical reports. Achieved with integer signals, sorted iteration, and
  no wall-clock/randomness in the verdict.
* The check path makes **zero model calls**. ``snapshot`` additionally spawns no
  subprocesses (the language tools only run inside ``evaluate``).
* This module is the ONLY place mode / severity / ratchet logic lives. The
  producers just emit :class:`~opencontext_core.quality.models.Finding` objects;
  they never decide pass/fail.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.harness.models import GateStatus
from opencontext_core.indexing.scanner import ScannedFile
from opencontext_core.quality.architecture import ArchitectureAnalyzer
from opencontext_core.quality.baseline import Baseline, BaselineStore
from opencontext_core.quality.ci_checks import CheckSeverity, CheckStatus
from opencontext_core.quality.languages import LanguageQualityRunner
from opencontext_core.quality.models import (
    Finding,
    HealthScore,
    QualityMetrics,
    QualityReport,
    RuleVerdict,
)
from opencontext_core.quality.rules import (
    DEFAULT_RULES,
    QualityConfigError,
    QualityMode,
    QualityRules,
    load_rules,
)

# --------------------------------------------------------------------------- #
# Built-in health-score weights (documented constants; unit-tested).
#
# The score is an INTEGER in basis points [0, 10000] (NOT a float) so equality
# and diff are exact. It starts at a perfect 10000 and subtracts a bounded
# penalty per signal. Every term is capped so no single signal can dominate or
# push the score out of range — the score degrades gracefully.
# --------------------------------------------------------------------------- #

PERFECT_SCORE = 10000

W_CYCLES = 400  # per cycle — the most damaging structural signal
W_GOD = 120  # per god-file
W_COUPLING = 8  # per unit of in-degree above the soft knee
W_CC = 10  # per complexity point over the configured max_cc
W_BOUNDARY = 150  # per declared-boundary break
W_DEPTH = 30  # per directory level over DEPTH_FREE
W_DUP = 60  # per near-duplicate (clone) pair
W_NESTING = 25  # per code block-nesting level over NESTING_FREE

# Soft knees / free allowances: signal below these costs nothing.
COUPLING_KNEE = 12  # fan-in at or below the knee is free
DEPTH_FREE = 8  # directory nesting depth at or below this is free
NESTING_FREE = 4  # code block-nesting at or below this is free (soft knee)

# Per-signal caps so each term is bounded (and the score cannot overflow/underflow).
_CAP_CYCLES = 10
_CAP_GOD = 20
# Coupling penalty is over (in_degree - COUPLING_KNEE) -- a heavily coupled node
# shouldn't dominate the score on its own. Capped so the worst in-degree
# contributes at most W_COUPLING * _CAP_COUPLING basis points.
_CAP_COUPLING = 40
_CAP_CC = 50
_CAP_BOUNDARY = 20
_CAP_DEPTH = 10
_CAP_DUP = 20  # at most 20 clone pairs contribute to the penalty
_CAP_NESTING = 8  # at most 8 nesting levels over the free knee contribute


def _cap(value: int, ceiling: int) -> int:
    """``min(value, ceiling)`` clamped at 0 — every penalty term is bounded."""
    if value < 0:
        return 0
    return min(value, ceiling)


def _coupling_penalty(in_degree: int) -> int:
    """Excess coupling above :data:`COUPLING_KNEE` (fan-in below the knee is free)."""
    return max(0, in_degree - COUPLING_KNEE)


class QualityEvaluator:
    """Composes architecture + languages + baseline + health into one verdict."""

    def __init__(
        self,
        root: Path,
        *,
        rules: QualityRules | None = None,
        scanned_files: list[ScannedFile] | None = None,
    ) -> None:
        """
        Bind to a project root.

        ``rules`` may be passed explicitly (e.g. by a test or the CLI) or is
        loaded from ``<root>/.opencontext/quality.toml`` via :func:`load_rules`
        (falling back to :data:`DEFAULT_RULES` when no file is present).
        ``scanned_files`` supplies the source the architecture passes need
        (import cycles / LOC / complexity); when omitted the evaluator scans the
        tree lazily the first time it is needed, and caches the result.

        On a malformed ``quality.toml`` the evaluator falls back to
        :data:`DEFAULT_RULES` AND records the cause on ``self._load_error`` so
        :meth:`evaluate` can surface it via :attr:`QualityReport.skipped` —
        never silently present a "clean" verdict for a broken config.
        """
        self.root = Path(root)
        self._load_error: str | None = None
        if rules is not None:
            self.rules = rules
        else:
            try:
                self.rules = load_rules(self.root)
            except QualityConfigError as exc:
                # Documented contract: a malformed config falls back to defaults;
                # the surfaces (gate / MCP / CI) surface the reason via
                # ``report.skipped`` so a broken config never reports a false
                # clean.
                self.rules = DEFAULT_RULES
                self._load_error = f"quality.toml: {exc}"
            except OSError as exc:  # unreadable config file — degrade honestly too
                self.rules = DEFAULT_RULES
                self._load_error = f"quality.toml: cannot read ({exc})"
        self._scanned_files = scanned_files
        self._scanned_loaded = scanned_files is not None

    # -- construction helpers --------------------------------------------- #
    @property
    def load_error(self) -> str | None:
        """The quality.toml load error captured at construction (read-only).

        Exposed so a caller (CLI, MCP, CI) can surface the same message without
        re-running :meth:`evaluate`. ``None`` means the config loaded cleanly.
        """
        return self._load_error

    @property
    def db_path(self) -> Path:
        """Path to this project's persisted knowledge graph DB."""
        return self.root / ".storage" / "opencontext" / "context_graph.db"

    def _scanned(self) -> list[ScannedFile]:
        """Return the scanned source, scanning lazily + caching on first use."""
        if not self._scanned_loaded:
            self._scanned_files = self._scan_root()
            self._scanned_loaded = True
        return self._scanned_files or []

    def _scan_root(self) -> list[ScannedFile]:
        """Scan the project tree (best-effort; never raises out of the engine)."""
        try:
            from opencontext_core.config import DEFAULT_IGNORE_PATTERNS
            from opencontext_core.indexing.scanner import ProjectScanner

            return ProjectScanner(list(DEFAULT_IGNORE_PATTERNS)).scan(self.root)
        except Exception:
            return []

    def _analyzer(self) -> ArchitectureAnalyzer:
        """Build an :class:`ArchitectureAnalyzer` bound to this project."""
        return ArchitectureAnalyzer(self.db_path, scanned_files=self._scanned())

    # -- the canonical health-score function ------------------------------- #

    @staticmethod
    def compute_health(metrics: QualityMetrics, rules: QualityRules) -> HealthScore:
        """The SINGLE health-score definition (see module weights).

        Pure integer arithmetic over the :class:`QualityMetrics` signals
        (cycles / god-files / coupling / complexity / boundary / directory-depth
        plus the Phase-3 duplication + code-nesting signals): no subprocess, no
        model. ``components`` carries the per-signal penalty — including the new
        ``duplication`` and ``nesting`` sub-scores — so the one-line summary and
        the trace can explain exactly why the rolled-up score moved. Every term
        is capped and the result is clamped to ``[0, PERFECT_SCORE]`` so no single
        signal can dominate.
        """
        max_cc_threshold = rules.architecture.max_cc

        components: dict[str, int] = {
            "cycles": W_CYCLES * _cap(metrics.cycles, _CAP_CYCLES),
            "god_files": W_GOD * _cap(metrics.god_files, _CAP_GOD),
            # Coupling is bounded like every other term — without the cap a single
            # super-coupled node can otherwise push the total penalty past
            # PERFECT_SCORE and silently turn every other signal into noise.
            "coupling": W_COUPLING * _cap(_coupling_penalty(metrics.max_in_degree), _CAP_COUPLING),
            "complexity": W_CC * _cap(max(0, metrics.max_cc - max_cc_threshold), _CAP_CC),
            "boundary": W_BOUNDARY * _cap(metrics.boundary_violations, _CAP_BOUNDARY),
            "depth": W_DEPTH * _cap(max(0, metrics.max_depth - DEPTH_FREE), _CAP_DEPTH),
            # Phase-3 depth signals folded into the same rolled-up score. Both are
            # bounded so neither a clone storm nor a deeply-nested function can
            # dominate the total or push it out of [0, PERFECT_SCORE]:
            #  * duplication is a flat per-pair penalty (like god_files),
            #  * nesting is a soft-knee penalty over NESTING_FREE (like depth).
            "duplication": W_DUP * _cap(metrics.duplication, _CAP_DUP),
            "nesting": W_NESTING * _cap(max(0, metrics.max_nesting - NESTING_FREE), _CAP_NESTING),
        }
        penalty = sum(components.values())
        score = PERFECT_SCORE - penalty
        if score < 0:
            score = 0
        elif score > PERFECT_SCORE:
            score = PERFECT_SCORE
        return HealthScore(score=score, metrics=metrics, components=components)

    # -- the fast (token-free) snapshot path ------------------------------- #

    def snapshot(self, *, changed_files: list[str] | None = None) -> HealthScore:
        """Architecture-only health snapshot (no language subprocesses).

        Used at explore (to capture the baseline) and at verify (to re-check).
        Runs the architecture metric passes over the graph and feeds the metrics
        into :meth:`compute_health`. Fast and token-free: it never spawns the
        language tools and never calls a model.
        """
        report = self._analyzer().analyze(self.rules.architecture, changed_files=changed_files)
        return self.compute_health(report.metrics, self.rules)

    # -- the full evaluation ----------------------------------------------- #

    def evaluate(
        self,
        changed_files: list[str],
        *,
        baseline: HealthScore | None = None,
        architecture_only: bool = False,
    ) -> QualityReport:
        """Run the full check and return the single :class:`QualityReport`.

        Steps:

        1. ``ArchitectureAnalyzer.analyze`` over ``changed_files``.
        2. ``LanguageQualityRunner.run`` (the language tool subprocesses) unless
           ``architecture_only`` is set.
        3. ``compute_health`` over the architecture metrics.
        4. In ``ratchet`` mode, diff findings against the persisted baseline so
           only NEW violations count; pre-existing findings never block.
        5. Build per-rule :class:`RuleVerdict` objects (severity/threshold).
        6. Map ``(mode, verdicts, health, baseline)`` to a :class:`GateStatus`.
        7. Compose the one-line health-delta summary.

        Deterministic: identical inputs always produce an identical report.
        """
        # OFF: do nothing — report SKIPPED with the current metrics for context.
        if not self.rules.is_active:
            arch = self._analyzer().analyze(self.rules.architecture, changed_files=changed_files)
            health = self.compute_health(arch.metrics, self.rules)
            # A malformed ``quality.toml`` is independent of the ``off`` mode and
            # must still be surfaced — and ``self._load_error`` already carries
            # the ``quality.toml:`` prefix, so we use it raw (no concatenation,
            # which would also fail ``ruff``'s RUF005).
            return QualityReport(
                status=GateStatus.SKIPPED,
                findings=(),
                verdicts=(),
                health=health,
                baseline_health=baseline,
                new_findings=(),
                skipped=(self._load_error,) if self._load_error else ("quality:mode-off",),
                summary=self._summary(health, baseline),
            )

        arch = self._analyzer().analyze(self.rules.architecture, changed_files=changed_files)

        lang_findings: tuple[Finding, ...] = ()
        lang_skipped: tuple[str, ...] = ()
        if not architecture_only:
            lang_findings, lang_skipped = LanguageQualityRunner(self.root).run(
                changed_files,
                self.rules.languages,
            )

        all_findings: tuple[Finding, ...] = tuple(arch.findings) + lang_findings
        # Malformed quality.toml is recorded FIRST so the read order matches the
        # failure order (config -> architecture -> languages).
        skipped_list = list(dict.fromkeys((*arch.skipped, *lang_skipped)))
        if self._load_error:
            skipped_list.insert(0, self._load_error)
        skipped = tuple(skipped_list)

        health = self.compute_health(arch.metrics, self.rules)

        # Ratchet: only findings NOT present in the baseline are "new"; the
        # blocking decision keys off the new set, not the whole set.
        new_findings = all_findings
        baseline_record: Baseline | None = None
        if self.rules.mode is QualityMode.RATCHET:
            baseline_record = self._load_baseline()
            if baseline_record is not None:
                new_findings = baseline_record.diff(all_findings)

        blocking_findings = new_findings if self.rules.mode is QualityMode.RATCHET else all_findings

        verdicts = self._build_verdicts(blocking_findings, skipped)
        status = self._status(verdicts, health, baseline)

        return QualityReport(
            status=status,
            findings=all_findings,
            verdicts=verdicts,
            health=health,
            baseline_health=baseline,
            new_findings=new_findings,
            skipped=skipped,
            summary=self._summary(health, baseline),
        )

    def evaluate_health_regression(
        self,
        baseline: HealthScore,
        current: HealthScore,
        rules: QualityRules,
    ) -> RuleVerdict:
        """The zero-config in-loop rule: did the health score drop?

        A drop (``current.score < baseline.score``) is the ONLY built-in numeric
        regression condition. Under ``strict`` it is an ERROR verdict (FAILED);
        otherwise a WARNING. No drop -> PASSED. The message is the compact delta
        ``architecture {b} -> {c}`` so the trace shows exactly what moved.
        """
        delta = current.delta(baseline)
        message = f"architecture {baseline.score} -> {current.score}"
        if delta >= 0:
            return RuleVerdict(
                rule="health_regression",
                status=CheckStatus.PASSED,
                severity=CheckSeverity.INFO,
                findings=(),
                message=message,
            )
        strict = rules.mode is QualityMode.STRICT
        severity = CheckSeverity.ERROR if strict else CheckSeverity.WARNING
        finding = Finding(
            rule="health_regression",
            severity=severity,
            message=message,
            suggestion="A change reduced the architecture health score; review the new findings.",
            category="architecture",
            metadata={
                "baseline": baseline.score,
                "current": current.score,
                "delta": delta,
            },
        )
        return RuleVerdict(
            rule="health_regression",
            status=CheckStatus.FAILED,
            severity=severity,
            findings=(finding,),
            message=message,
        )

    def save_baseline(self, changed_files: list[str] | None = None) -> Baseline:
        """Run a whole-repo evaluation and persist findings+metrics+score.

        Backs ``opencontext quality gate --save``. The baseline is captured over
        the WHOLE repo (architecture findings only — a baseline of subprocess
        results would be non-deterministic across machines), so subsequent
        ratchet diffs are stable.
        """
        arch = self._analyzer().analyze(self.rules.architecture, changed_files=None)
        health = self.compute_health(arch.metrics, self.rules)
        store = BaselineStore(self.root / self.rules.baseline_path)
        return store.save(arch.findings, arch.metrics, health)

    # -- internals --------------------------------------------------------- #

    def _load_baseline(self) -> Baseline | None:
        """Load the persisted baseline (``None`` if absent/unusable)."""
        store = BaselineStore(self.root / self.rules.baseline_path)
        return store.load()

    @staticmethod
    def _build_verdicts(
        findings: tuple[Finding, ...],
        skipped: tuple[str, ...],
    ) -> tuple[RuleVerdict, ...]:
        """Group findings into one :class:`RuleVerdict` per rule (deterministic).

        Each rule's verdict status is FAILED when it has any finding (a Finding
        is always a violation) and its severity is the worst across its
        findings. Skipped tools/rules become SKIPPED verdicts so the report
        accounts for them (degrade honestly). Rules are emitted in sorted order
        so the report is byte-stable.
        """
        by_rule: dict[str, list[Finding]] = {}
        for f in findings:
            by_rule.setdefault(f.rule, []).append(f)

        verdicts: list[RuleVerdict] = []
        for rule in sorted(by_rule):
            rule_findings = tuple(by_rule[rule])
            severity = QualityEvaluator._worst_severity(rule_findings)
            verdicts.append(
                RuleVerdict(
                    rule=rule,
                    status=CheckStatus.FAILED,
                    severity=severity,
                    findings=rule_findings,
                    message=f"{len(rule_findings)} {rule} finding(s)",
                )
            )

        for reason in skipped:
            rule_name = reason.split(":", 1)[0] or reason
            verdicts.append(
                RuleVerdict(
                    rule=rule_name,
                    status=CheckStatus.SKIPPED,
                    severity=CheckSeverity.INFO,
                    findings=(),
                    message=reason,
                )
            )

        verdicts.sort(key=lambda v: (v.rule, v.status.value))
        return tuple(verdicts)

    @staticmethod
    def _worst_severity(findings: tuple[Finding, ...]) -> CheckSeverity:
        """Highest severity among ``findings`` (critical > error > warning > info)."""
        order = {
            CheckSeverity.INFO: 0,
            CheckSeverity.WARNING: 1,
            CheckSeverity.ERROR: 2,
            CheckSeverity.CRITICAL: 3,
        }
        worst = CheckSeverity.INFO
        for f in findings:
            if order[f.severity] > order[worst]:
                worst = f.severity
        return worst

    def _status(
        self,
        verdicts: tuple[RuleVerdict, ...],
        health: HealthScore,
        baseline: HealthScore | None,
    ) -> GateStatus:
        """Map the mode + verdicts + health delta to a single gate status.

        * ``strict`` — FAILED on any error/critical finding OR a health drop vs
          the baseline; else PASSED (warnings do not block under strict because a
          blocking warning would defeat the ratchet posture; an error does).
        * ``ratchet`` / ``warn`` — WARNING when any blocking finding exists OR the
          health dropped; PASSED otherwise. Never FAILED (the in-loop sensor
          surfaces, it does not block by itself).
        * ``off`` — handled earlier (SKIPPED).
        """
        has_error = any(
            f.severity in (CheckSeverity.ERROR, CheckSeverity.CRITICAL)
            for v in verdicts
            for f in v.findings
        )
        has_finding = any(v.status == CheckStatus.FAILED for v in verdicts)
        regressed = baseline is not None and health.delta(baseline) < 0

        if self.rules.mode is QualityMode.STRICT:
            if has_error or regressed:
                return GateStatus.FAILED
            if has_finding:
                return GateStatus.WARNING
            return GateStatus.PASSED

        # ratchet / warn: surface but never block.
        if has_finding or regressed:
            return GateStatus.WARNING
        return GateStatus.PASSED

    @staticmethod
    def _summary(health: HealthScore, baseline: HealthScore | None) -> str:
        """One-line health-delta summary, e.g. ``architecture 9120 -> 9180 (up)``."""
        if baseline is None:
            return f"architecture {health.score}"
        delta = health.delta(baseline)
        direction = "flat" if delta == 0 else ("up" if delta > 0 else "down")
        return f"architecture {baseline.score} -> {health.score} ({direction})"
