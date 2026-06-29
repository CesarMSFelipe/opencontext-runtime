"""Meta-planning package: intent -> governed program of PRs.

Additive and workflow-neutral. Nothing on the runtime hot path imports this
package; it is reached only via the ``MetaPlanner`` facade (and tests). The
facade chains six deterministic, offline stages so the requirement-coverage
guarantee never depends on a provider call.
"""

from __future__ import annotations

from opencontext_core.planning.decomposition import ImplementationSlice, decompose
from opencontext_core.planning.estimates import estimate, recommend_workflow
from opencontext_core.planning.intent import IntentRecord, map_to_docs, parse_intent
from opencontext_core.planning.pr_plan import (
    PrCycleError,
    PrEntry,
    PrPlan,
    assign_prs,
)
from opencontext_core.planning.program import (
    ARTIFACT_KIND_CONVERGENCE_MAP,
    ARTIFACT_KIND_PROGRAM_PLAN,
    ConvergenceMap,
    CoverageEntry,
    Disposition,
    MetaPlanner,
    PlanningError,
    ProgramPlan,
)
from opencontext_core.planning.risk import RiskAssessment, RiskClassifier, assess

__all__ = [
    "ARTIFACT_KIND_CONVERGENCE_MAP",
    "ARTIFACT_KIND_PROGRAM_PLAN",
    "ConvergenceMap",
    "CoverageEntry",
    "Disposition",
    "ImplementationSlice",
    "IntentRecord",
    "MetaPlanner",
    "PlanningError",
    "PrCycleError",
    "PrEntry",
    "PrPlan",
    "ProgramPlan",
    "RiskAssessment",
    "RiskClassifier",
    "assess",
    "assign_prs",
    "decompose",
    "estimate",
    "map_to_docs",
    "parse_intent",
    "recommend_workflow",
]
