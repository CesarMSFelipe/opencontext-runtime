"""Feedback collector for capturing runtime operation metrics.

Tracks token usage, context quality, task types, and outcomes
to build a learning dataset for optimization.

Uses the shared SQLite database (codegraph.db) when available,
falling back to JSONL for standalone usage.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from opencontext_core.compat import UTC


@dataclass
class OperationMetrics:
    """Metrics captured for a single runtime operation."""

    operation_id: str
    operation_type: str
    query: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    duration_ms: float = 0.0
    tokens_used: int = 0
    tokens_budgeted: int = 0
    context_items_selected: int = 0
    context_items_omitted: int = 0
    files_consulted: int = 0
    symbols_consulted: int = 0
    task_type: str | None = None
    success: bool | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class FeedbackCollector:
    """Collects and persists operation metrics for learning."""

    def __init__(
        self,
        storage_path: Path | str = ".storage/opencontext/learning",
        db: Any | None = None,
    ) -> None:
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.metrics_file = self.storage_path / "operation_metrics.jsonl"
        self._db = db
        self._pending: list[OperationMetrics] = []

    def start_operation(
        self,
        operation_type: str,
        query: str,
        task_type: str | None = None,
        tokens_budgeted: int = 0,
    ) -> str:
        """Start tracking an operation. Returns operation ID."""

        op_id = str(uuid.uuid4())[:8]
        metric = OperationMetrics(
            operation_id=op_id,
            operation_type=operation_type,
            query=query,
            task_type=task_type,
            tokens_budgeted=tokens_budgeted,
            metadata={"start_time": time.time()},
        )
        self._pending.append(metric)
        return op_id

    def finish_operation(
        self,
        operation_id: str,
        tokens_used: int = 0,
        context_items_selected: int = 0,
        context_items_omitted: int = 0,
        files_consulted: int = 0,
        symbols_consulted: int = 0,
        success: bool | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Finish tracking an operation and persist metrics."""

        for metric in self._pending:
            if metric.operation_id == operation_id:
                metric.tokens_used = tokens_used
                metric.context_items_selected = context_items_selected
                metric.context_items_omitted = context_items_omitted
                metric.files_consulted = files_consulted
                metric.symbols_consulted = symbols_consulted
                metric.success = success
                if metadata:
                    metric.metadata.update(metadata)
                if "start_time" in metric.metadata:
                    metric.duration_ms = (time.time() - metric.metadata["start_time"]) * 1000
                self._persist(metric)
                self._pending.remove(metric)
                break

    def _persist(self, metric: OperationMetrics) -> None:
        """Persist metric to DB (preferred) or JSONL fallback."""

        record = {
            "operation_id": metric.operation_id,
            "operation_type": metric.operation_type,
            "query": metric.query,
            "timestamp": metric.timestamp.isoformat(),
            "duration_ms": metric.duration_ms,
            "tokens_used": metric.tokens_used,
            "tokens_budgeted": metric.tokens_budgeted,
            "context_items_selected": metric.context_items_selected,
            "context_items_omitted": metric.context_items_omitted,
            "files_consulted": metric.files_consulted,
            "symbols_consulted": metric.symbols_consulted,
            "task_type": metric.task_type,
            "success": metric.success,
            "metadata": metric.metadata,
        }
        if self._db is not None:
            try:
                self._db.insert_metric(record)
                return
            except Exception:
                pass
        with open(self.metrics_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def load_metrics(
        self,
        operation_type: str | None = None,
        task_type: str | None = None,
        limit: int = 1000,
    ) -> list[OperationMetrics]:
        """Load persisted metrics with optional filtering."""

        if self._db is not None:
            try:
                rows = self._db.query_metrics(operation_type, task_type, limit)
                return self._rows_to_metrics(rows)
            except Exception:
                pass
        return self._load_from_jsonl(operation_type, task_type, limit)

    def _rows_to_metrics(self, rows: list[dict[str, Any]]) -> list[OperationMetrics]:
        """Convert DB rows to OperationMetrics."""

        metrics: list[OperationMetrics] = []
        for record in rows:
            try:
                metrics.append(
                    OperationMetrics(
                        operation_id=record["operation_id"],
                        operation_type=record["operation_type"],
                        query=record["query"],
                        timestamp=datetime.fromisoformat(record["timestamp"]),
                        duration_ms=record.get("duration_ms", 0) or 0,
                        tokens_used=record.get("tokens_used", 0) or 0,
                        tokens_budgeted=record.get("tokens_budgeted", 0) or 0,
                        context_items_selected=record.get("context_items_selected", 0) or 0,
                        context_items_omitted=record.get("context_items_omitted", 0) or 0,
                        files_consulted=record.get("files_consulted", 0) or 0,
                        symbols_consulted=record.get("symbols_consulted", 0) or 0,
                        task_type=record.get("task_type"),
                        success=record.get("success"),
                        metadata=json.loads(record.get("metadata", "{}")),
                    )
                )
            except (KeyError, ValueError):
                continue
        return metrics

    def _load_from_jsonl(
        self,
        operation_type: str | None = None,
        task_type: str | None = None,
        limit: int = 1000,
    ) -> list[OperationMetrics]:
        """Load from JSONL fallback."""

        metrics: list[OperationMetrics] = []
        if not self.metrics_file.exists():
            return metrics

        with open(self.metrics_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if operation_type and record.get("operation_type") != operation_type:
                        continue
                    if task_type and record.get("task_type") != task_type:
                        continue
                    metrics.append(
                        OperationMetrics(
                            operation_id=record["operation_id"],
                            operation_type=record["operation_type"],
                            query=record["query"],
                            timestamp=datetime.fromisoformat(record["timestamp"]),
                            duration_ms=record.get("duration_ms", 0),
                            tokens_used=record.get("tokens_used", 0),
                            tokens_budgeted=record.get("tokens_budgeted", 0),
                            context_items_selected=record.get("context_items_selected", 0),
                            context_items_omitted=record.get("context_items_omitted", 0),
                            files_consulted=record.get("files_consulted", 0),
                            symbols_consulted=record.get("symbols_consulted", 0),
                            task_type=record.get("task_type"),
                            success=record.get("success"),
                            metadata=record.get("metadata", {}),
                        )
                    )
                    if len(metrics) >= limit:
                        break
                except (json.JSONDecodeError, KeyError):
                    continue
        return metrics

    def get_statistics(self) -> dict[str, Any]:
        """Compute aggregate statistics from all metrics."""

        metrics = self.load_metrics(limit=10000)
        if not metrics:
            return {"total_operations": 0}

        total_tokens = sum(m.tokens_used for m in metrics)
        total_duration = sum(m.duration_ms for m in metrics)
        successful = sum(1 for m in metrics if m.success is True)
        failed = sum(1 for m in metrics if m.success is False)

        by_type: dict[str, dict[str, Any]] = {}
        for m in metrics:
            ot = m.operation_type
            if ot not in by_type:
                by_type[ot] = {"count": 0, "total_tokens": 0, "total_duration_ms": 0}
            by_type[ot]["count"] += 1
            by_type[ot]["total_tokens"] += m.tokens_used
            by_type[ot]["total_duration_ms"] += m.duration_ms

        return {
            "total_operations": len(metrics),
            "total_tokens_used": total_tokens,
            "total_duration_ms": total_duration,
            "successful_operations": successful,
            "failed_operations": failed,
            "average_tokens_per_operation": total_tokens / len(metrics),
            "average_duration_ms": total_duration / len(metrics),
            "by_operation_type": by_type,
        }
