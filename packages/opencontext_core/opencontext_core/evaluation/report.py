"""REQ-eval-fw-001/002: EvalReport + EvalCaseResult + EvalRegression + factory.

The :class:`EvalReport` is the immutable artifact every :class:`EvalSuite`
emits. It carries:

- the suite identity + its ``methodology_version`` (the version that bumped
  when the SCORING RUBRIC changed, not on bug fixes — per spec §C.3
  REQ-eval-fw-001),
- the per-case :class:`EvalCaseResult` list,
- the high-level ``verdict`` (``pass`` / ``fail`` / ``regression``),
- a list of :class:`EvalRegression` entries (a passing case that drifted
  past the suite's ``regression_threshold`` counts as a regression — the
  spec rule: "regression in any gate block release"),
- the total wall-clock time in microseconds (the spec contract uses
  microseconds, not ms, so cross-suite comparison is fine-grained).

:func:`generate_report` is the single canonical factory; everything that
produces an :class:`EvalReport` (including :func:`opencontext_core.evaluation
.runner.run_suite`) routes through it.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvalCaseResult:
    """The per-case result inside an :class:`EvalReport`."""

    case_id: str
    passed: bool
    score: float
    duration_ms: int = 0
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvalRegression:
    """A passing case whose metric drifted past the suite's regression threshold.

    Attributes
    ----------
    case_id:
        The case that drifted.
    before, after:
        The metric value before and after the change.
    delta:
        ``after - before``; negative when the metric got worse.
    axis:
        Which metric drifted. Common values: ``"score"``, ``"outcome_drift"``
        (per spec §C.3 scenario "regression suite catches an outcome shift").
    """

    case_id: str
    before: float
    after: float
    delta: float
    axis: str


@dataclass(frozen=True)
class EvalReport:
    """The canonical output of an :class:`EvalSuite` run.

    ``verdict`` follows the spec rule from §C.3 REQ-eval-fw-003:

    - ``"regression"`` when any regression was detected (BLOCKS release
      regardless of pass/fail of the per-case results),
    - ``"fail"`` when any case failed,
    - ``"pass"`` otherwise.
    """

    suite: str
    methodology_version: str
    results: list[EvalCaseResult] = field(default_factory=list)
    verdict: str = "pass"
    regressions: list[EvalRegression] = field(default_factory=list)
    microseconds_total: int = 0

    @property
    def passed(self) -> bool:
        """True when ``verdict == "pass"``."""
        return self.verdict == "pass"

    @property
    def failed(self) -> bool:
        """True when ``verdict == "fail"``."""
        return self.verdict == "fail"


def generate_report(
    *,
    suite: str,
    methodology_version: str,
    results: list[EvalCaseResult] | None = None,
    regressions: list[EvalRegression] | None = None,
    microseconds_total: int = 0,
) -> EvalReport:
    """Build an :class:`EvalReport` with the correct verdict.

    Precedence (per spec §C.3):

    1. Any regression → ``"regression"`` (blocks release).
    2. Any failing case → ``"fail"``.
    3. Otherwise → ``"pass"``.

    The function is the ONLY place that decides a verdict, so consumers
    can trust the report is consistent with the inputs.
    """
    results = list(results or [])
    regressions = list(regressions or [])

    if regressions:
        verdict = "regression"
    elif any(not r.passed for r in results):
        verdict = "fail"
    else:
        verdict = "pass"

    return EvalReport(
        suite=suite,
        methodology_version=methodology_version,
        results=results,
        verdict=verdict,
        regressions=regressions,
        microseconds_total=int(microseconds_total),
    )


__all__ = [
    "EvalCaseResult",
    "EvalRegression",
    "EvalReport",
    "generate_report",
]
