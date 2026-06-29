"""Unified benchmark runner over the named cognitive suites (REL-08/REL-09/REL-CONV).

A thin registry that unifies discovery + versioned reporting across the ten
mandatory 1.0 benchmark gates (doc 57 §A / convergence §6) WITHOUT coupling their
measurement code. Three gates already have honest measurement substrate and are
WIRED here:

* ``context-token-efficiency`` → the parity-gated efficiency benchmark
  (``evaluation/efficiency.py``); MET only when every CON pack is sufficient.
* ``kg-retrieval-precision`` → :func:`~opencontext_core.evaluation.recall_eval.run_recall_eval`
  (median recall/precision over labeled tasks).
* ``memory-usefulness`` → :func:`~opencontext_core.memory.benchmark.run_benchmark`
  (R@5 / MRR / p50, the gate K-5 thresholds).

Five more gates are WIRED here to real, provider-free golden fixtures under
``tests/golden/`` via :class:`~opencontext_core.evaluation.golden.GoldenSuite`
(B4/B5/AVH-006): ``first-run``, ``oc-flow-localized-bugfix``, ``policy-security``,
``resume-rollback`` and ``provider-fallback`` produce a genuine ``MET`` / ``FAILED``
(NOT_MEASURED only when a fixture is absent — e.g. an installed wheel without the test
tree). The two remaining gates (``sdd-formal-feature``, ``plugin-compatibility``) stay
DECLARED and honestly report :class:`GateStatus.NOT_MEASURED` with a reason until their
end-to-end runners land — never a fabricated pass (build-rule #1).

A provider-gated suite invoked WITHOUT its measurement inputs also returns
``NOT_MEASURED`` with a clear note; supplying a real provider produces a genuine
``MET`` / ``FAILED`` (exercised by the tests).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Protocol, runtime_checkable

from opencontext_core.evaluation.models import (
    BenchmarkSuiteReport,
    EfficiencyReport,
    GateStatus,
)

#: The ten mandatory 1.0 benchmark gates (doc 57 §A / OC-FINAL-CONVERGENCE-001 §6).
#: The release gate blocks 1.0 unless every one of these is MET (REL-CONV).
MANDATORY_GATES: tuple[str, ...] = (
    "first-run",
    "oc-flow-localized-bugfix",
    "sdd-formal-feature",
    "context-token-efficiency",
    "kg-retrieval-precision",
    "memory-usefulness",
    "policy-security",
    "plugin-compatibility",
    "provider-fallback",
    "resume-rollback",
)

#: Default versioned methodology stamp (book §19). Bump on any methodology change
#: so cross-release comparisons stay within the same suite version.
DEFAULT_METHODOLOGY_VERSION = "1.0.0"


def not_measured(suite: str, version: str, reason: str) -> BenchmarkSuiteReport:
    """An honest NOT_MEASURED report — never a fake pass (build-rule #1)."""
    return BenchmarkSuiteReport(
        suite=suite,
        version=version,
        status=GateStatus.NOT_MEASURED,
        measured=False,
        success=False,
        notes=f"not measured: {reason}",
    )


@runtime_checkable
class BenchmarkSuite(Protocol):
    """A named, versioned benchmark suite producing a :class:`BenchmarkSuiteReport`."""

    name: str
    version: str

    def run(self, root: Path, *, smoke: bool = False) -> BenchmarkSuiteReport: ...


@dataclass
class DeclaredSuite:
    """A declared-but-not-yet-measurable gate: always honest NOT_MEASURED."""

    name: str
    version: str = DEFAULT_METHODOLOGY_VERSION
    reason: str = "end-to-end suite runner not implemented yet"

    def run(self, root: Path, *, smoke: bool = False) -> BenchmarkSuiteReport:
        return not_measured(self.name, self.version, self.reason)


@dataclass
class EfficiencySuite:
    """``context-token-efficiency`` — wraps the parity-gated efficiency benchmark.

    ``provider`` runs the real benchmark over ``root`` and returns an
    :class:`EfficiencyReport`; when absent the suite is honestly NOT_MEASURED.
    """

    name: str = "context-token-efficiency"
    version: str = DEFAULT_METHODOLOGY_VERSION
    provider: Callable[[Path, bool], EfficiencyReport] | None = None

    def run(self, root: Path, *, smoke: bool = False) -> BenchmarkSuiteReport:
        if self.provider is None:
            return not_measured(
                self.name, self.version, "no contextbench suite / indexed runtime supplied"
            )
        report = self.provider(root, smoke)
        if not report.cases:
            return not_measured(self.name, self.version, "efficiency suite produced no cases")
        status = GateStatus.MET if report.all_sufficient else GateStatus.FAILED
        return BenchmarkSuiteReport(
            suite=self.name,
            version=self.version,
            status=status,
            measured=True,
            success=report.all_sufficient,
            duration_ms=int(report.con_latency_p(50)),
            tokens=int(median([c.con.tokens for c in report.cases])),
            tool_calls=int(median([c.con.tool_calls for c in report.cases])),
            confidence=sum(c.source_coverage for c in report.cases) / len(report.cases),
            notes=(f"{len(report.cases)} cases, {report.insufficient_cases} parity-insufficient"),
        )


@dataclass
class RecallSuite:
    """``kg-retrieval-precision`` — median recall/precision over labeled tasks."""

    name: str = "kg-retrieval-precision"
    version: str = DEFAULT_METHODOLOGY_VERSION
    min_recall: float = 0.5
    min_precision: float = 0.3
    # provider(root, smoke) -> RecallReport (duck-typed: .median_recall/.median_precision/.results)
    provider: Callable[[Path, bool], object] | None = None

    def run(self, root: Path, *, smoke: bool = False) -> BenchmarkSuiteReport:
        if self.provider is None:
            return not_measured(
                self.name, self.version, "no labeled retrieval tasks / indexed runtime supplied"
            )
        report = self.provider(root, smoke)
        results = list(getattr(report, "results", []))
        if not results:
            return not_measured(self.name, self.version, "retrieval suite produced no tasks")
        median_recall = float(getattr(report, "median_recall", 0.0))
        median_precision = float(getattr(report, "median_precision", 0.0))
        ok = median_recall >= self.min_recall and median_precision >= self.min_precision
        return BenchmarkSuiteReport(
            suite=self.name,
            version=self.version,
            status=GateStatus.MET if ok else GateStatus.FAILED,
            measured=True,
            success=ok,
            confidence=median_recall,
            notes=(
                f"median recall {median_recall:.0%} (min {self.min_recall:.0%}), "
                f"median precision {median_precision:.0%} (min {self.min_precision:.0%})"
            ),
        )


@dataclass
class MemorySuite:
    """``memory-usefulness`` — R@5 / MRR / p50 (gate K-5 thresholds)."""

    name: str = "memory-usefulness"
    version: str = DEFAULT_METHODOLOGY_VERSION
    min_recall_at_5: float = 0.85
    min_mrr: float = 0.70
    # provider(root, smoke) -> MemoryBenchmarkResult (duck-typed)
    provider: Callable[[Path, bool], object] | None = None

    def run(self, root: Path, *, smoke: bool = False) -> BenchmarkSuiteReport:
        if self.provider is None:
            return not_measured(
                self.name, self.version, "no seeded memory backend / fixture supplied"
            )
        result = self.provider(root, smoke)
        recall_at_5 = float(getattr(result, "recall_at_5", 0.0))
        mrr = float(getattr(result, "mrr", 0.0))
        ok = recall_at_5 >= self.min_recall_at_5 and mrr >= self.min_mrr
        return BenchmarkSuiteReport(
            suite=self.name,
            version=self.version,
            status=GateStatus.MET if ok else GateStatus.FAILED,
            measured=True,
            success=ok,
            duration_ms=int(getattr(result, "p50_ms", 0.0)),
            confidence=recall_at_5,
            notes=(
                f"R@5 {recall_at_5:.0%} (min {self.min_recall_at_5:.0%}), "
                f"MRR {mrr:.2f} (min {self.min_mrr:.2f})"
            ),
        )


class BenchmarkRunner:
    """Registry + driver over the named cognitive suites (REL-08).

    Suites are keyed by name; ``run_all`` returns one versioned report per suite.
    The registry never fabricates a result — an unmeasurable suite reports
    NOT_MEASURED.
    """

    def __init__(self) -> None:
        self._suites: dict[str, BenchmarkSuite] = {}

    def register(self, suite: BenchmarkSuite, *, replace: bool = False) -> None:
        if suite.name in self._suites and not replace:
            raise ValueError(f"benchmark suite {suite.name!r} already registered")
        self._suites[suite.name] = suite

    def list_suites(self) -> list[str]:
        return list(self._suites.keys())

    def has(self, name: str) -> bool:
        return name in self._suites

    def suite(self, name: str) -> BenchmarkSuite:
        """Return the registered suite object for ``name`` (KeyError if absent)."""
        return self._suites[name]

    def run(
        self, name: str, root: str | Path = ".", *, smoke: bool = False
    ) -> BenchmarkSuiteReport:
        if name not in self._suites:
            raise ValueError(f"unknown benchmark suite: {name!r}")
        return self._suites[name].run(Path(root), smoke=smoke)

    def run_all(self, root: str | Path = ".", *, smoke: bool = False) -> list[BenchmarkSuiteReport]:
        return [self.run(name, root, smoke=smoke) for name in self._suites]


@dataclass
class RunnerConfig:
    """Optional measurement providers for the three wired gates."""

    efficiency_provider: Callable[[Path, bool], EfficiencyReport] | None = None
    recall_provider: Callable[[Path, bool], object] | None = None
    memory_provider: Callable[[Path, bool], object] | None = None
    extra: list[BenchmarkSuite] = field(default_factory=list)


def build_default_runner(config: RunnerConfig | None = None) -> BenchmarkRunner:
    """Register all ten mandatory gates: three wired, seven declared NOT_MEASURED.

    Pass a :class:`RunnerConfig` with providers to make the wired gates produce a
    genuine MET/FAILED; with no providers every gate is honestly NOT_MEASURED today
    (the correct output for the unified CLI/CI path before fixtures are wired).
    """
    # Lazy import keeps the runner<->golden module pair acyclic (golden imports
    # not_measured/DEFAULT_METHODOLOGY_VERSION from here at its module top).
    from opencontext_core.evaluation.golden import GOLDEN_ROOT, GOLDEN_SUITE_NAMES, GoldenSuite

    cfg = config or RunnerConfig()
    runner = BenchmarkRunner()
    wired: dict[str, BenchmarkSuite] = {
        "context-token-efficiency": EfficiencySuite(provider=cfg.efficiency_provider),
        "kg-retrieval-precision": RecallSuite(provider=cfg.recall_provider),
        "memory-usefulness": MemorySuite(provider=cfg.memory_provider),
    }
    # B4/B5/AVH-006: the five 1.0-minimum golden gates MEASURE against real fixtures
    # under tests/golden/ (MET/FAILED; NOT_MEASURED only when a fixture is absent).
    # These replace the DeclaredSuite NOT_MEASURED stubs the loop below would create.
    for name in GOLDEN_SUITE_NAMES:
        wired[name] = GoldenSuite(name, GOLDEN_ROOT)
    for name in MANDATORY_GATES:
        runner.register(wired.get(name, DeclaredSuite(name)))
    for suite in cfg.extra:
        runner.register(suite, replace=True)
    return runner


__all__ = [
    "DEFAULT_METHODOLOGY_VERSION",
    "MANDATORY_GATES",
    "BenchmarkRunner",
    "BenchmarkSuite",
    "DeclaredSuite",
    "EfficiencySuite",
    "MemorySuite",
    "RecallSuite",
    "build_default_runner",
    "not_measured",
]
