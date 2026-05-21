"""Performance metrics and cost tracking.

Tracks token usage, timing, and costs across all operations.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar


@dataclass
class OperationMetrics:
    """Metrics for a single operation."""

    operation: str
    start_time: float
    end_time: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        if self.end_time == 0.0:
            return (time.time() - self.start_time) * 1000
        return (self.end_time - self.start_time) * 1000

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "duration_ms": round(self.duration_ms, 2),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "metadata": self.metadata,
        }


class MetricsCollector:
    """Collects and reports performance metrics."""

    # Token costs per 1M tokens (approximate)
    COST_PER_1M_TOKENS: ClassVar[dict[str, dict[str, float]]] = {
        "openai": {"input": 2.50, "output": 10.00},  # GPT-4o
        "anthropic": {"input": 3.00, "output": 15.00},  # Claude Sonnet
        "openrouter": {"input": 1.00, "output": 5.00},  # Average
        "local": {"input": 0.0, "output": 0.0},  # Free
        "mock": {"input": 0.0, "output": 0.0},  # Free
    }

    def __init__(self, metrics_dir: str | Path = ".opencontext/metrics") -> None:
        self.metrics_dir = Path(metrics_dir)
        self.metrics_dir.mkdir(parents=True, exist_ok=True)
        self._current: dict[str, OperationMetrics] = {}
        self._history: list[OperationMetrics] = []

    def start(self, operation: str, **metadata: Any) -> str:
        """Start tracking an operation.

        Returns:
            Operation ID for stopping.
        """

        op_id = f"{operation}_{time.time()}"
        self._current[op_id] = OperationMetrics(
            operation=operation,
            start_time=time.time(),
            metadata=metadata,
        )
        return op_id

    def stop(
        self,
        op_id: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        provider: str = "mock",
    ) -> OperationMetrics:
        """Stop tracking an operation."""

        metrics = self._current.pop(op_id, None)
        if metrics is None:
            raise KeyError(f"Operation not found: {op_id}")

        metrics.end_time = time.time()
        metrics.input_tokens = input_tokens
        metrics.output_tokens = output_tokens

        # Calculate cost
        costs = self.COST_PER_1M_TOKENS.get(provider, self.COST_PER_1M_TOKENS["mock"])
        input_cost = (input_tokens / 1_000_000) * costs["input"]
        output_cost = (output_tokens / 1_000_000) * costs["output"]
        metrics.cost_usd = input_cost + output_cost

        self._history.append(metrics)
        self._persist(metrics)

        return metrics

    def get_summary(self) -> dict[str, Any]:
        """Get summary of all operations."""

        if not self._history:
            return {
                "total_operations": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "avg_duration_ms": 0.0,
            }

        total_duration = sum(m.duration_ms for m in self._history)
        total_tokens = sum(m.total_tokens for m in self._history)
        total_cost = sum(m.cost_usd for m in self._history)

        # Group by operation
        by_operation: dict[str, list[OperationMetrics]] = {}
        for m in self._history:
            by_operation.setdefault(m.operation, []).append(m)

        return {
            "total_operations": len(self._history),
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 6),
            "avg_duration_ms": round(total_duration / len(self._history), 2),
            "by_operation": {
                op: {
                    "count": len(metrics),
                    "total_tokens": sum(m.total_tokens for m in metrics),
                    "total_cost_usd": round(sum(m.cost_usd for m in metrics), 6),
                    "avg_duration_ms": round(sum(m.duration_ms for m in metrics) / len(metrics), 2),
                }
                for op, metrics in by_operation.items()
            },
        }

    def get_recent(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent operations."""

        recent = sorted(self._history, key=lambda m: m.start_time, reverse=True)
        return [m.to_dict() for m in recent[:limit]]

    def _persist(self, metrics: OperationMetrics) -> None:
        """Persist metrics to disk."""

        date = time.strftime("%Y-%m-%d")
        path = self.metrics_dir / f"{date}.jsonl"

        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(metrics.to_dict()) + "\n")

    def load_history(self, days: int = 7) -> list[dict[str, Any]]:
        """Load historical metrics."""

        results = []
        for i in range(days):
            date = time.strftime("%Y-%m-%d", time.localtime(time.time() - i * 86400))
            path = self.metrics_dir / f"{date}.jsonl"
            if path.exists():
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                results.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue
        return results

    def clear(self) -> None:
        """Clear in-memory history."""

        self._history.clear()
        self._current.clear()
