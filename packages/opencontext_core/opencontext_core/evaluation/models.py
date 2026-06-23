"""Evaluation layer models."""

from __future__ import annotations

from statistics import median

from pydantic import BaseModel, ConfigDict, Field


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
