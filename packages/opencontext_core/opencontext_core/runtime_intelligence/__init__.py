"""Runtime Intelligence (L10) — observe, measure, estimate, explain, improve.

The book §5 composition layer (OC-RUNTIME-INTELLIGENCE-001). Thin, read-only
facades over the existing measurement substrate (traces, metrics, telemetry, the
parity-gated efficiency benchmark, graph health, the propose-only evolution flow)
that produce the typed book report family. Runtime Intelligence recommends; the
Runtime governs (invariant §23.1). Optional and first-class; default off behind
the ``runtime_intelligence_enabled`` config flag.

Layering (doc 58): this package consumes events/receipts/traces from lower layers
via their public types/ports; lower layers never import this package.
"""

from __future__ import annotations

from opencontext_core.models.intelligence import (
    BENCHMARK_SUITES,
    CONFIDENCE_DIMENSIONS,
    HEALTH_DIMENSIONS,
    PROFILER_COMPONENTS,
    BenchmarkResult,
    BenchmarkTask,
    ConfidenceReport,
    CostEstimate,
    CostReport,
    EvolutionCandidate,
    ProfilerReport,
    RuntimeHealthReport,
    SimulationReport,
    WorkflowComparison,
)
from opencontext_core.runtime_intelligence.benchmarks import (
    BenchmarkSystem,
    efficiency_report_to_results,
)
from opencontext_core.runtime_intelligence.confidence import (
    ConfidenceEngine,
    ConfidenceSignals,
    ConfidenceThresholds,
)
from opencontext_core.runtime_intelligence.cost import CostEngine
from opencontext_core.runtime_intelligence.evolution import (
    CandidatePromotionGate,
    candidate_from_proposal,
    proposal_from_candidate,
)
from opencontext_core.runtime_intelligence.health import (
    RuntimeHealth,
    confidence_calibration_error,
    cost_calibration_error,
    decision_quality_metrics,
)
from opencontext_core.runtime_intelligence.optimizer import (
    LearningRuntimeOptimizer,
    RuntimeOptimizationRecommendation,
    RuntimeOptimizer,
)
from opencontext_core.runtime_intelligence.profiler import RuntimeProfiler
from opencontext_core.runtime_intelligence.simulator import (
    RuntimeSimulator,
    SchedulerPlanEstimator,
)

# Internal contract version (doc 59 §Internal contract versioning).
RUNTIME_INTELLIGENCE_CONTRACT_VERSION = 1

__all__ = [
    "BENCHMARK_SUITES",
    "CONFIDENCE_DIMENSIONS",
    "HEALTH_DIMENSIONS",
    "PROFILER_COMPONENTS",
    "RUNTIME_INTELLIGENCE_CONTRACT_VERSION",
    "BenchmarkResult",
    "BenchmarkSystem",
    "BenchmarkTask",
    "CandidatePromotionGate",
    "ConfidenceEngine",
    "ConfidenceReport",
    "ConfidenceSignals",
    "ConfidenceThresholds",
    "CostEngine",
    "CostEstimate",
    "CostReport",
    "EvolutionCandidate",
    "LearningRuntimeOptimizer",
    "ProfilerReport",
    "RuntimeHealth",
    "RuntimeHealthReport",
    "RuntimeOptimizationRecommendation",
    "RuntimeOptimizer",
    "RuntimeProfiler",
    "RuntimeSimulator",
    "SchedulerPlanEstimator",
    "SimulationReport",
    "WorkflowComparison",
    "candidate_from_proposal",
    "confidence_calibration_error",
    "cost_calibration_error",
    "decision_quality_metrics",
    "efficiency_report_to_results",
    "proposal_from_candidate",
]
