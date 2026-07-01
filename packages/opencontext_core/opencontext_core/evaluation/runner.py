"""Unified benchmark runner over the named cognitive suites (REL-08/REL-09/REL-CONV)
+ the PR-R2-C ``EvalSuite`` / :class:`EvalRunner` harness for the evaluation
framework (REQ-eval-fw-001/002/003).

A thin registry that unifies discovery + versioned reporting across the ten
mandatory 1.0 benchmark gates (doc 57 §A / convergence §6) WITHOUT coupling their
measurement code.

``memory-usefulness`` is WIRED to a deterministic provider-free seeded backend
(:func:`~opencontext_core.memory.benchmark.seeded_memory_provider`) so it MEASURES
(R@5 / MRR / p50 against the gate K-5 thresholds) without a live model (VDM-008).

Seven gates are WIRED to real, provider-free golden fixtures under ``tests/golden/``
via :class:`~opencontext_core.evaluation.golden.GoldenSuite` (B4/B5/AVH-006/VDM-008):
``first-run``, ``oc-flow-localized-bugfix``, ``policy-security``, ``resume-rollback``,
``provider-fallback``, ``sdd-formal-feature`` and ``plugin-compatibility`` produce a
genuine ``MET`` / ``FAILED`` (NOT_MEASURED only when a fixture is absent — e.g. an
installed wheel without the test tree).

The two remaining gates require a live provider and are DEFERRED under Option A
(``DEFERRED_PROVIDER_CI.md``): ``context-token-efficiency`` (parity-gated efficiency
benchmark) and ``kg-retrieval-precision`` (median recall/precision over labeled tasks)
ship runner hooks (``efficiency_provider`` / ``recall_provider``) but report
:class:`GateStatus.NOT_MEASURED` until a provider callable is injected — never a
fabricated pass (build-rule #1).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Any, Protocol, runtime_checkable

from opencontext_core.evaluation.models import (
    BenchmarkSuiteReport,
    EfficiencyReport,
    GateStatus,
)
from opencontext_core.evaluation.report import (
    EvalCaseResult,
    EvalReport,
    generate_report,
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
    from opencontext_core.memory.benchmark import seeded_memory_provider

    cfg = config or RunnerConfig()
    # VDM-008: memory-usefulness MEASURES provider-free by default via a deterministic
    # seeded backend; an explicit ``memory_provider`` in the config still overrides it.
    # The two provider-CI gates (efficiency / recall) stay NOT_MEASURED until a hook is
    # injected (Option A — see DEFERRED_PROVIDER_CI.md).
    memory_provider = cfg.memory_provider or seeded_memory_provider()
    runner = BenchmarkRunner()
    wired: dict[str, BenchmarkSuite] = {
        "context-token-efficiency": EfficiencySuite(provider=cfg.efficiency_provider),
        "kg-retrieval-precision": RecallSuite(provider=cfg.recall_provider),
        "memory-usefulness": MemorySuite(provider=memory_provider),
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
    "EvalRunner",
    "EvalSuite",
    "MemorySuite",
    "RecallSuite",
    "build_default_runner",
    "not_measured",
    "run_suite",
]


# ── PR-R2-C evaluation framework (REQ-eval-fw-001/002/003) ──────────────────
# A lightweight, registry-based harness on top of the existing
# ``BenchmarkRunner``. The two coexist on purpose: the legacy
# ``BenchmarkRunner`` is the unified entry point for the 10 mandatory 1.0
# gates (REL-08/REL-09/REL-CONV); :class:`EvalRunner` is the user-facing
# surface for the six canonical suites described in spec §C.3.


@dataclass
class EvalSuite:
    """A named, versioned eval suite — the eval framework's unit of work.

    Mirrors the spec's :class:`EvalSuite` Protocol
    (specs/evaluation-framework/spec.md §Contracts): ``name``,
    ``methodology_version`` (the ``YYYY.MM.DD`` schema-style stamp that bumps
    ONLY on a rubric change), ``cases``, ``gate_blocking`` (default ``True``
    so a failing suite blocks release — REQ-eval-fw-003), and
    ``regression_threshold`` (a passing case whose score drops by more than
    this amount is recorded as a regression).

    Each entry in ``cases`` is a mapping that MUST expose ``"id"`` and a
    ``"run"`` callable returning a payload of the form
    ``{"passed": bool, "score": float, "reasons": list[str]}``; ``"setup"``,
    ``"teardown"``, ``"assertions"`` and ``"timeout_s"`` are accepted per
    the spec contract but are NOT enforced by this lazy reference runner —
    they are surfaced as attributes for downstream consumers (CI gates,
    Studio dashboard).
    """

    name: str
    methodology_version: str
    cases: list[dict[Any, Any]] = field(default_factory=list[Any])
    gate_blocking: bool = True
    regression_threshold: float = 0.05


@dataclass
class _CaseOutcome:
    """Internal: a case's raw run payload + timing."""

    case_id: str
    payload: dict[Any, Any]
    duration_ms: int


class EvalRunner:
    """Registry + driver for :class:`EvalSuite` instances.

    Per REQ-eval-fw-001: ``eval.registry.list()`` returns every registered
    suite; per REQ-eval-fw-003: a failing or regressing suite carries a
    verdict the release-gate lint can act on.
    """

    def __init__(self) -> None:
        self._suites: dict[str, EvalSuite] = {}

    # ── Registry API ────────────────────────────────────────────────────

    def register(self, suite: EvalSuite, *, replace: bool = False) -> None:
        """Add ``suite`` to the registry.

        Raises :class:`ValueError` on duplicate name unless ``replace=True``.
        """
        if suite.name in self._suites and not replace:
            raise ValueError(f"eval suite {suite.name!r} already registered")
        self._suites[suite.name] = suite

    def list_suites(self) -> list[str]:
        """Return the registered suite names in insertion order."""
        return list(self._suites.keys())

    def has(self, name: str) -> bool:
        return name in self._suites

    def get_suite(self, name: str) -> EvalSuite:
        """Return the registered :class:`EvalSuite` for ``name``."""
        if name not in self._suites:
            raise KeyError(f"unknown eval suite: {name!r}")
        return self._suites[name]

    # ── Execution ───────────────────────────────────────────────────────

    def run(self, name: str) -> EvalReport:
        """Run every case in the named suite and return an :class:`EvalReport`."""
        suite = self.get_suite(name)
        return _execute_suite(suite)

    def run_all(self) -> list[EvalReport]:
        """Run every registered suite; preserves registration order."""
        return [self.run(name) for name in self._suites]


def _execute_case(case: dict[Any, Any]) -> _CaseOutcome:
    """Run a single case dict; never raises — failures become a failed result.

    The case MUST have an ``"id"`` and a ``"run"`` callable. Anything else
    (missing id, run is not callable, the run raised) becomes a failed
    case with a descriptive reason; the harness never crashes on a bad
    case because a single bad case must not block the suite.
    """
    case_id = str(case.get("id", "<unknown>"))
    run = case.get("run")
    if not callable(run):
        return _CaseOutcome(
            case_id=case_id,
            payload={"passed": False, "score": 0.0, "reasons": ["case has no callable 'run'"]},
            duration_ms=0,
        )
    t0 = time.monotonic()
    try:
        payload = run() or {}
    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        return _CaseOutcome(
            case_id=case_id,
            payload={"passed": False, "score": 0.0, "reasons": [f"case raised: {exc!r}"]},
            duration_ms=duration_ms,
        )
    duration_ms = int((time.monotonic() - t0) * 1000)
    if not isinstance(payload, dict):
        payload = {"passed": bool(payload), "score": 1.0 if payload else 0.0, "reasons": []}
    return _CaseOutcome(case_id=case_id, payload=payload, duration_ms=duration_ms)


def _execute_suite(suite: EvalSuite) -> EvalReport:
    """Drive a full suite → :class:`EvalReport` via :func:`generate_report`."""
    outcomes = [_execute_case(case) for case in suite.cases]
    results = [
        EvalCaseResult(
            case_id=o.case_id,
            passed=bool(o.payload.get("passed", False)),
            score=float(o.payload.get("score", 1.0 if o.payload.get("passed") else 0.0)),
            duration_ms=o.duration_ms,
            reasons=list(o.payload.get("reasons", [])),
        )
        for o in outcomes
    ]
    microseconds_total = sum(o.duration_ms for o in outcomes) * 1000
    return generate_report(
        suite=suite.name,
        methodology_version=suite.methodology_version,
        results=results,
        microseconds_total=microseconds_total,
    )


def run_suite(suite: EvalSuite) -> EvalReport:
    """Free-function convenience wrapper: run a suite without a registry.

    Equivalent to ``EvalRunner().run(suite.name)`` after registering, but
    avoids touching the registry for one-shot invocations (e.g. tests, ad-hoc
    ``opencontext eval run bug_fix``).
    """
    return _execute_suite(suite)
