"""Runtime Intelligence report models (PR-011, OC-RUNTIME-INTELLIGENCE-001).

The book §6/§8/§10/§11/§12/§13/§14 typed report family. These are additive,
backward-compatible contracts; the engines in
:mod:`opencontext_core.runtime_intelligence` compose the existing measurement
substrate (traces, metrics, telemetry, efficiency benchmark, graph health,
evolution flow) into them. Runtime Intelligence recommends; the Runtime governs
(book §23.1) — every model here is read-only evidence, never control.

Collision notes (compat/collisions.py CL-009):

* ``CostReport`` here is the book estimate-vs-actual report. It is DISTINCT from
  the aggregate-ledger ``operating_model/performance.py:CostReport`` and the two
  are disambiguated by package (``namespace`` rule). The ledger one totals a cost
  ledger; this one reconciles a pre-run :class:`CostEstimate` against measured
  actuals and attributes cost by component.
* ``SimulationReport`` here is the book §10 cognitive-dry-run report. It is
  DISTINCT from ``runtime/decisions.py:SimulationReport`` (the PR-000.1 Scheduler
  plan-forecast seam) and disambiguated by package. The Runtime Simulator wires
  the scheduler seam to a real estimator (see ``runtime_intelligence/simulator``)
  without changing that seam's contract.
* ``EvolutionCandidate`` here is the book §14 schema; the legacy
  ``learning/evolution.py:EvolutionProposal`` becomes its persisted/serialized
  form via the adapter in ``runtime_intelligence/evolution.py`` (``alias`` rule).
  No second evolution store is introduced.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# --- Canonical dimension/suite/component vocabularies (test + render surface) --

#: The eight Confidence Engine dimensions (book §8). ``overall`` is both a
#: dimension key and the aggregate scalar carried on :class:`ConfidenceReport`.
CONFIDENCE_DIMENSIONS: tuple[str, ...] = (
    "intent",
    "context",
    "plan",
    "mutation",
    "inspection",
    "memory",
    "security",
    "overall",
)

#: The ten Runtime Health dimensions (book §13).
HEALTH_DIMENSIONS: tuple[str, ...] = (
    "kg_freshness",
    "memory_quality",
    "skill_catalog",
    "harness_pass_rate",
    "selector_accuracy",
    "cost_calibration",
    "confidence_calibration",
    "benchmark_trend",
    "policy_violations",
    "context_drift",
)

#: Profiler cost-by-component buckets (book §11).
PROFILER_COMPONENTS: tuple[str, ...] = (
    "context_retrieval",
    "diagnosis",
    "planning",
    "mutation",
    "inspection",
    "consolidation",
)

#: The thirteen benchmark suites (PR-011 §RI-CONV taxonomy; book §12 / OC-OBS).
BENCHMARK_SUITES: tuple[str, ...] = (
    "first-run",
    "bugfix",
    "feature",
    "refactor",
    "review",
    "sdd",
    "oc-flow",
    "kg-retrieval",
    "memory-retrieval",
    "context-compression",
    "harness",
    "persona",
    "security",
)

#: The bounded set of confidence-driven actions (book §9). Runtime Intelligence
#: recommends exactly one; the Runtime enforces the final decision.
ConfidenceAction = Literal[
    "continue",
    "retrieve_deeper",
    "ask",
    "switch_workflow",
    "deep_mode",
    "require_approval",
    "escalate",
]


# --- Cost Engine (book §6) ----------------------------------------------------


class CostEstimate(BaseModel):
    """Pre-run cost estimate for a (workflow, lane) pair (book §6)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.cost_estimate.v1"
    workflow: str = Field(description="Candidate workflow (e.g. 'oc-flow', 'sdd').")
    lane: str = Field(description="Candidate lane (e.g. 'quick', 'fast', 'full').")
    estimated_input_tokens: int = Field(ge=0)
    estimated_output_tokens: int = Field(ge=0)
    estimated_tool_calls: int = Field(ge=0)
    estimated_duration_s: int = Field(ge=0)
    estimated_cost_usd: float | None = Field(default=None)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    assumptions: list[str] = Field(default_factory=list)


class CostReport(BaseModel):
    """Post-run estimate-vs-actual reconciliation (book §6).

    Distinct from the aggregate ledger ``operating_model/performance.py:CostReport``
    (collision CL-009, ``namespace``). Carries the pre-run :class:`CostEstimate`,
    measured actuals, the estimate error, a per-component cost attribution, and a
    measured-only token-savings attribution (no fabricated reduction claim).
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.cost_report.v1"
    session_id: str
    run_id: str
    estimate: CostEstimate
    actual_input_tokens: int = Field(ge=0)
    actual_output_tokens: int = Field(ge=0)
    actual_tool_calls: int = Field(ge=0)
    actual_duration_s: int = Field(ge=0)
    estimate_error_pct: float = Field(
        description="Signed estimate error: (actual - estimated) / estimated * 100.",
    )
    cost_by_component: dict[str, Any] = Field(default_factory=dict)
    token_savings: dict[str, int] = Field(default_factory=dict)


class WorkflowComparison(BaseModel):
    """A what-if comparison across candidate workflows (book §7).

    Carries the per-workflow :class:`CostEstimate`s and the chosen workflow plus a
    rationale. HONESTY (design DEC-8): there is deliberately NO ``reduction``/
    ``savings_pct``/``cheaper_by`` field — the comparison reports measured/estimated
    numbers only, parity-gated, with no fabricated reduction badge.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.workflow_comparison.v1"
    task: str
    estimates: dict[str, CostEstimate] = Field(default_factory=dict)
    chosen: str
    reason: str = ""
    advisory: bool = Field(
        default=True,
        description="Recommendation only — the Runtime governs the final selection.",
    )


# --- Confidence Engine (book §8) ----------------------------------------------


class ConfidenceReport(BaseModel):
    """System-level confidence across the eight runtime dimensions (book §8)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.confidence_report.v1"
    session_id: str
    run_id: str
    workflow: str
    dimensions: dict[str, float] = Field(default_factory=dict)
    overall: float = Field(ge=0.0, le=1.0)
    threshold: float = Field(ge=0.0, le=1.0)
    recommended_action: ConfidenceAction
    evidence_refs: list[str] = Field(default_factory=list)


# --- Runtime Simulator (book §10) ---------------------------------------------


class SimulationReport(BaseModel):
    """Deterministic, provider-free cognitive dry run (book §10).

    Distinct from ``runtime/decisions.py:SimulationReport`` (the Scheduler plan
    seam); disambiguated by package.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.simulation_report.v1"
    task: str
    recommended_workflow: str
    recommended_lane: str
    expected_files: list[str] = Field(default_factory=list)
    expected_symbols: list[str] = Field(default_factory=list)
    expected_tests: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    cost_estimates: list[CostEstimate] = Field(default_factory=list)
    confidence_estimate: float = Field(default=0.5, ge=0.0, le=1.0)
    recommendation: str = ""
    provider_calls: int = Field(
        default=0,
        ge=0,
        description="MUST be 0 — the simulator is local-only (book §10 invariant).",
    )


# --- Runtime Profiler (book §11) ----------------------------------------------


class ProfilerReport(BaseModel):
    """Cost-by-component attribution + bottlenecks from a real trace (book §11)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.profiler_report.v1"
    session_id: str = ""
    run_id: str = ""
    cost_by_component: dict[str, Any] = Field(default_factory=dict)
    bottlenecks: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


# --- Benchmark System (book §12) ----------------------------------------------


class BenchmarkTask(BaseModel):
    """One repeatable benchmark task (book §12)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.benchmark_task.v1"
    id: str
    name: str
    suite: str = ""
    repo_fixture: str = ""
    task: str = ""
    expected_workflow: str | None = None
    setup_commands: list[str] = Field(default_factory=list)
    eval_commands: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    max_tokens: int | None = None
    max_changed_lines: int | None = None


class BenchmarkResult(BaseModel):
    """Result of running one :class:`BenchmarkTask` (book §12).

    HONESTY: a suite that cannot run honestly sets ``measured=False`` with a
    "not measured" ``notes`` — it is never reported as a fake ``success``.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.benchmark_result.v1"
    task_id: str
    suite: str = ""
    measured: bool = Field(
        default=True,
        description="False ⇒ suite declared but not honestly runnable ('not measured').",
    )
    success: bool = False
    tokens: int = Field(default=0, ge=0)
    duration_s: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    changed_files: int = Field(default=0, ge=0)
    changed_lines: int = Field(default=0, ge=0)
    tests_passed: bool = False
    security_passed: bool = True
    notes: str = ""


# --- Runtime Health (book §13) ------------------------------------------------


class RuntimeHealthReport(BaseModel):
    """Self-health across the ten runtime dimensions (book §13)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.runtime_health_report.v1"
    overall_score: float = Field(ge=0.0, le=1.0)
    dimensions: dict[str, float] = Field(
        default_factory=dict,
        description="Only the dimensions backed by a real evidence source (B9/AVH-016).",
    )
    unmeasured_dimensions: list[str] = Field(
        default_factory=list,
        description="Dimensions with no wired evidence source — reported UNMEASURED, never a "
        "fabricated neutral score (B9/AVH-016).",
    )
    critical_findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


# --- Evolution Engine (book §14) ----------------------------------------------


class EvolutionCandidate(BaseModel):
    """An evidence-backed runtime-improvement candidate (book §14).

    The book schema for an evolution improvement. Maps to/from the legacy
    ``learning/evolution.py:EvolutionProposal`` via the adapter in
    ``runtime_intelligence/evolution.py`` (collision CL-009, ``alias``);
    evolution stays propose-only and benchmark-gated.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.evolution_candidate.v1"
    candidate_id: str
    target_type: str = Field(description="What the change targets (skill/persona/harness/…).")
    target_id: str = ""
    change_summary: str = ""
    rationale: str = ""
    expected_benefit: str = ""
    risks: list[str] = Field(default_factory=list)
    generated_from_runs: list[str] = Field(default_factory=list)
    required_benchmarks: list[str] = Field(default_factory=list)
    requires_approval: bool = True


__all__ = [
    "BENCHMARK_SUITES",
    "CONFIDENCE_DIMENSIONS",
    "HEALTH_DIMENSIONS",
    "PROFILER_COMPONENTS",
    "BenchmarkResult",
    "BenchmarkTask",
    "ConfidenceAction",
    "ConfidenceReport",
    "CostEstimate",
    "CostReport",
    "EvolutionCandidate",
    "ProfilerReport",
    "RuntimeHealthReport",
    "SimulationReport",
    "WorkflowComparison",
]
