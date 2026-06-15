"""OpenContext self-improvement and learning system.

Captures usage patterns, optimizes token spend, and enforces
data governance policies for enterprise-grade deployments.
"""

from __future__ import annotations

from opencontext_core.learning.feed import record_outcome
from opencontext_core.learning.feedback_collector import FeedbackCollector, OperationMetrics
from opencontext_core.learning.governance_harness import ExecutionPolicy, GovernanceHarness
from opencontext_core.learning.learning_orchestrator import LearningOrchestrator
from opencontext_core.learning.pattern_learner import PatternLearner, TaskPattern
from opencontext_core.learning.proposals import ApplyOutcome, ConfigProposal, ProposalEngine
from opencontext_core.learning.token_optimizer import TokenOptimizer

__all__ = [
    "ApplyOutcome",
    "ConfigProposal",
    "ExecutionPolicy",
    "FeedbackCollector",
    "GovernanceHarness",
    "LearningOrchestrator",
    "OperationMetrics",
    "PatternLearner",
    "ProposalEngine",
    "TaskPattern",
    "TokenOptimizer",
    "record_outcome",
]
