"""opencontext-core success-metrics dashboard (PR-R2-G).

Re-exports the pre-existing ``MetricsCollector`` (perf + cost tracking) and
the new KPI dashboard surface added by PR-R2-G.
"""

from opencontext_core.metrics.collector import (
    MetricsCollector,
    OperationMetrics,
)
from opencontext_core.metrics.dashboard import (
    KPI,
    KPI_NAMES,
    MANDATORY_CI_KPIS,
    MetricCard,
    MetricRecord,
    MetricsDashboard,
    MetricsSnapshot,
    MissingMethodologyError,
)

__all__ = [
    "KPI",
    "KPI_NAMES",
    "MANDATORY_CI_KPIS",
    "MetricCard",
    "MetricRecord",
    "MetricsCollector",
    "MetricsDashboard",
    "MetricsSnapshot",
    "MissingMethodologyError",
    "OperationMetrics",
]
