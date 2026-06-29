"""Evaluation layer models."""

from __future__ import annotations

from enum import StrEnum
from statistics import median

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.models.contract import StabilityLevel, VersionedContract


class GateStatus(StrEnum):
    """The honest three-state verdict for any benchmark suite or release gate.

    HONESTY (binding, book §10 / build-rule #1): a suite that cannot run
    end-to-end yet is ``NOT_MEASURED`` — never a fabricated ``MET``. Only a real,
    passing measurement is ``MET``; a real, failing one is ``FAILED``.
    """

    MET = "met"
    NOT_MEASURED = "not-measured"
    FAILED = "failed"


class EvalCase(BaseModel):
    """A structural evaluation case for a workflow."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Eval case identifier.")
    workflow: str = Field(description="Workflow to run or inspect.")
    input: str = Field(description="Eval input.")
    expected_sources: list[str] = Field(default_factory=list)
    forbidden_sources: list[str] = Field(default_factory=list)
    expected_behavior: str | None = Field(default=None)
    forbidden_behavior: str | None = Field(default=None)


class EvalResult(BaseModel):
    """Result of evaluating one case."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(description="Eval case identifier.")
    passed: bool = Field(description="Whether the eval passed.")
    score: float = Field(ge=0.0, le=1.0, description="Normalized score.")
    reasons: list[str] = Field(description="Human-readable reasons.")


class ContextBenchCase(BaseModel):
    """Golden case for deterministic context retrieval and token-efficiency checks."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable benchmark case identifier.")
    query: str = Field(description="Developer task used to prepare a context pack.")
    expected_sources: list[str] = Field(
        default_factory=list,
        description="Source path fragments that should be present in the packed context.",
    )
    forbidden_sources: list[str] = Field(
        default_factory=list,
        description="Source path fragments that must not be present in the packed context.",
    )
    min_source_coverage: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Minimum expected-source coverage required for this case.",
    )
    target_symbol: str | None = Field(
        default=None,
        description=(
            "Primary symbol a realistic OpenContext-free agent would grep for. "
            "When omitted, derived from the case id/query."
        ),
    )
    difficulty: str | None = Field(
        default=None,
        description="Informational tier label (simple|medium|hard); no behaviour.",
    )


class ContextBenchCaseResult(BaseModel):
    """Result for one context benchmark case."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(description="Benchmark case identifier.")
    passed: bool = Field(description="Whether this case passed all gates.")
    source_coverage: float = Field(ge=0.0, le=1.0, description="Expected-source hit ratio.")
    token_reduction: float = Field(
        ge=0.0,
        le=1.0,
        description="Token reduction compared with the full indexed project baseline.",
    )
    context_tokens: int = Field(ge=0, description="Prepared context token estimate.")
    baseline_tokens: int = Field(ge=0, description="Full indexed project token estimate.")
    included_sources: list[str] = Field(description="Sources included by the context pack.")
    missing_sources: list[str] = Field(description="Expected source fragments not found.")
    forbidden_hits: list[str] = Field(description="Forbidden source fragments found.")
    reasons: list[str] = Field(description="Human-readable result details.")


class ContextBenchSuiteResult(BaseModel):
    """Aggregate result for a context benchmark suite."""

    model_config = ConfigDict(extra="forbid")

    passed: bool = Field(description="Whether all cases passed.")
    cases: list[ContextBenchCaseResult] = Field(description="Per-case benchmark results.")
    average_source_coverage: float = Field(
        ge=0.0,
        le=1.0,
        description="Average expected-source coverage.",
    )
    average_token_reduction: float = Field(
        ge=0.0,
        le=1.0,
        description="Average token reduction compared with full project context.",
    )


# ── Efficiency benchmark: symmetric CON vs SIN cost ──────────────────────────


class CostTriple(BaseModel):
    """One side's measured cost for building task context: the symmetric unit.

    The same three fields are reported for CON (context built WITH OpenContext via
    a single ``runtime.prepare_context`` call) and SIN (a realistic OpenContext-free
    control: a ``grep`` + full-``Read`` loop), so the per-case delta is well-defined.
    """

    model_config = ConfigDict(extra="forbid")

    tokens: int = Field(ge=0, description="Estimated tokens of the built context.")
    tool_calls: int = Field(ge=0, description="Number of agent tool calls used to build it.")
    latency_ms: float = Field(ge=0.0, description="Wall-clock to build the context, ms.")


class EfficiencyCaseResult(BaseModel):
    """Per-case efficiency result: what it cost (CON vs SIN) AND whether it was correct.

    ``con_sufficient`` is the mandatory quality-parity verdict — a CON pack that
    misses an expected source or hits a forbidden one is ``con_sufficient=False`` and
    must NOT be counted as a token win.
    """

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(description="Benchmark case identifier.")
    difficulty: str | None = Field(default=None, description="Informational tier label.")
    con: CostTriple = Field(description="Cost of context built WITH OpenContext.")
    sin: CostTriple = Field(description="Cost of the realistic OpenContext-free control.")
    ceiling_tokens: int | None = Field(
        default=None,
        ge=0,
        description="Whole-repo 'read everything' token ceiling (labeled, secondary).",
    )
    con_sufficient: bool = Field(description="Quality-parity verdict for the CON pack.")
    source_coverage: float = Field(
        ge=0.0, le=1.0, description="Expected-source hit ratio for the CON pack."
    )
    forbidden_hits: list[str] = Field(
        default_factory=list, description="Forbidden source fragments the CON pack included."
    )
    reasons: list[str] = Field(default_factory=list, description="Human-readable result details.")

    @property
    def token_delta(self) -> int:
        """SIN tokens minus CON tokens (positive ⇒ CON used fewer)."""
        return self.sin.tokens - self.con.tokens

    @property
    def tool_call_delta(self) -> int:
        """SIN tool calls minus CON tool calls (positive ⇒ CON used fewer)."""
        return self.sin.tool_calls - self.con.tool_calls


class EfficiencyReport(BaseModel):
    """Symmetric, machine-readable efficiency report — measured numbers, no claim.

    Deliberately carries NO "X% reduction"/badge/marketing field: the benchmark
    reports raw per-case and aggregate deltas; whether/what to publish is a separate,
    later decision.
    """

    model_config = ConfigDict(extra="forbid")

    cases: list[EfficiencyCaseResult] = Field(
        default_factory=list, description="Per-case efficiency results."
    )

    @property
    def insufficient_cases(self) -> int:
        """Cases where the CON pack failed quality parity (not a win)."""
        return sum(1 for c in self.cases if not c.con_sufficient)

    @property
    def all_sufficient(self) -> bool:
        """True when every CON pack met quality parity."""
        return all(c.con_sufficient for c in self.cases)

    @property
    def median_token_delta(self) -> int:
        """Median (SIN minus CON) token delta across cases."""
        if not self.cases:
            return 0
        return int(median([c.token_delta for c in self.cases]))

    @property
    def median_tool_call_delta(self) -> int:
        """Median (SIN minus CON) tool-call delta across cases."""
        if not self.cases:
            return 0
        return int(median([c.tool_call_delta for c in self.cases]))

    def con_latency_p(self, pct: float) -> float:
        """CON latency percentile (ms) across cases."""
        return _latency_p([c.con.latency_ms for c in self.cases], pct)

    def sin_latency_p(self, pct: float) -> float:
        """SIN latency percentile (ms) across cases."""
        return _latency_p([c.sin.latency_ms for c in self.cases], pct)


def _latency_p(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(pct / 100 * len(ordered)))
    return ordered[idx]


# ── Unified benchmark-runner report (REL-08/REL-09) ──────────────────────────


class BenchmarkSuiteReport(VersionedContract):
    """One named cognitive suite's outcome, stamped with a versioned methodology.

    Carries the book §19 ``benchmark_suite`` + ``version`` so cross-release
    comparisons are only made within the same suite version (REL-09). ``status`` is
    the honest :class:`GateStatus`: a suite without a runnable end-to-end harness
    yet reports ``NOT_MEASURED`` with a ``notes`` reason, never a fake ``MET``.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.benchmark_suite_report.v1"
    suite: str = Field(description="Named cognitive suite, e.g. 'context-token-efficiency'.")
    version: str = Field(description="Semver of the benchmark methodology, e.g. '1.0.0'.")
    status: GateStatus = Field(description="Honest MET / NOT_MEASURED / FAILED verdict.")
    measured: bool = Field(
        default=False,
        description="True only when the suite ran end-to-end (status MET or FAILED).",
    )
    success: bool = Field(default=False, description="True only when status is MET.")
    duration_ms: int = Field(default=0, ge=0)
    tokens: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    changed_files: int = Field(default=0, ge=0)
    changed_lines: int = Field(default=0, ge=0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    receipts: int = Field(default=0, ge=0)
    notes: str = Field(default="", description="Human-readable detail; required when NOT_MEASURED.")


class EvaluationRecord(VersionedContract):
    """Immutable AI-evaluation artifact for a persona / skill / harness run (book §88).

    Frozen audit record carrying the book metric set so ``eval compare`` can diff
    two releases per-metric and flag regressions (REL-14). Persisted via the
    existing receipt/artifact infra — this is evidence, never control.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "opencontext.evaluation_record.v1"
    stability: StabilityLevel = StabilityLevel.BETA
    target_kind: str = Field(description="What was evaluated: persona | skill | harness.")
    target_id: str = Field(description="Registry id of the evaluated definition.")
    task: str = ""
    repository: str = ""
    workflow: str = ""
    runtime_version: str = ""
    provider: str = ""
    profile: str = ""
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    token_count: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    retries: int = Field(default=0, ge=0)
    escalation_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    patch_size: int = Field(default=0, ge=0)
    local_validation_pass_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    benchmark_version: str = Field(default="1.0.0", description="Eval methodology semver.")
    receipts: list[str] = Field(default_factory=list)
