"""Runtime Intelligence event + receipt constants (book §16/§17).

The intelligence layer emits named ``intelligence.*`` events and matching
receipts. Per doc 59 (Event hierarchy) every event belongs to exactly one family;
intelligence events belong to the ``runtime_intelligence`` family (OC-OBS event
model), which Studio (PR-014) renders as one lane.
"""

from __future__ import annotations

# Event family (doc 59 §Event hierarchy / OC-OBS event model).
INTELLIGENCE_EVENT_FAMILY = "runtime_intelligence"

# Required events (book §16).
COST_ESTIMATED = "intelligence.cost.estimated"
COST_REPORTED = "intelligence.cost.reported"
CONFIDENCE_CALCULATED = "intelligence.confidence.calculated"
SIMULATION_CREATED = "intelligence.simulation.created"
PROFILER_REPORTED = "intelligence.profiler.reported"
HEALTH_REPORTED = "intelligence.health.reported"
EVOLUTION_CANDIDATE_CREATED = "intelligence.evolution_candidate.created"
EVOLUTION_CANDIDATE_PROMOTED = "intelligence.evolution_candidate.promoted"
EVOLUTION_CANDIDATE_REJECTED = "intelligence.evolution_candidate.rejected"

INTELLIGENCE_EVENTS: frozenset[str] = frozenset(
    {
        COST_ESTIMATED,
        COST_REPORTED,
        CONFIDENCE_CALCULATED,
        SIMULATION_CREATED,
        PROFILER_REPORTED,
        HEALTH_REPORTED,
        EVOLUTION_CANDIDATE_CREATED,
        EVOLUTION_CANDIDATE_PROMOTED,
        EVOLUTION_CANDIDATE_REJECTED,
    }
)

# Required receipt kinds (book §17).
RECEIPT_WORKFLOW_COMPARISON = "intelligence.receipt.workflow_comparison"
RECEIPT_COST_ESTIMATE = "intelligence.receipt.cost_estimate"
RECEIPT_CONFIDENCE_DECISION = "intelligence.receipt.confidence_decision"
RECEIPT_SIMULATION = "intelligence.receipt.simulation"
RECEIPT_BENCHMARK = "intelligence.receipt.benchmark"
RECEIPT_EVOLUTION_PROPOSAL = "intelligence.receipt.evolution_proposal"

INTELLIGENCE_RECEIPTS: frozenset[str] = frozenset(
    {
        RECEIPT_WORKFLOW_COMPARISON,
        RECEIPT_COST_ESTIMATE,
        RECEIPT_CONFIDENCE_DECISION,
        RECEIPT_SIMULATION,
        RECEIPT_BENCHMARK,
        RECEIPT_EVOLUTION_PROPOSAL,
    }
)


__all__ = [
    "CONFIDENCE_CALCULATED",
    "COST_ESTIMATED",
    "COST_REPORTED",
    "EVOLUTION_CANDIDATE_CREATED",
    "EVOLUTION_CANDIDATE_PROMOTED",
    "EVOLUTION_CANDIDATE_REJECTED",
    "HEALTH_REPORTED",
    "INTELLIGENCE_EVENTS",
    "INTELLIGENCE_EVENT_FAMILY",
    "INTELLIGENCE_RECEIPTS",
    "PROFILER_REPORTED",
    "RECEIPT_BENCHMARK",
    "RECEIPT_CONFIDENCE_DECISION",
    "RECEIPT_COST_ESTIMATE",
    "RECEIPT_EVOLUTION_PROPOSAL",
    "RECEIPT_SIMULATION",
    "RECEIPT_WORKFLOW_COMPARISON",
    "SIMULATION_CREATED",
]
