"""Runtime optimization package (PR-000.3).

A recommend-only optimizer that reads cache + token telemetry and emits
``RuntimeOptimizationRecommendation``s for downstream Runtime Intelligence
(PR-011) to consume through a port — this package imports nothing upward.
"""

from opencontext_core.optimization.optimizer import RuntimeOptimizer
from opencontext_core.optimization.recommendations import (
    RecommendationTarget,
    RuntimeOptimizationRecommendation,
)

__all__ = [
    "RecommendationTarget",
    "RuntimeOptimizationRecommendation",
    "RuntimeOptimizer",
]
