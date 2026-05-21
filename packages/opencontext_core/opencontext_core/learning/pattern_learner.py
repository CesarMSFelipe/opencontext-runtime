"""Pattern learner for optimizing context selection based on task types.

Learns which files and symbols are most relevant for different types
of tasks by analyzing historical operation outcomes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from opencontext_core.learning.feedback_collector import FeedbackCollector


@dataclass
class TaskPattern:
    """Learned pattern for a specific task type."""

    task_type: str
    relevant_symbols: list[str] = field(default_factory=list)
    relevant_files: list[str] = field(default_factory=list)
    avg_tokens_used: int = 0
    avg_context_items: int = 0
    success_rate: float = 0.0
    occurrence_count: int = 0


class PatternLearner:
    """Learns optimal context patterns from historical operations."""

    def __init__(
        self,
        feedback_collector: FeedbackCollector,
        db: Any | None = None,
        storage_path: Path | str = ".storage/opencontext/learning",
    ) -> None:
        self.feedback = feedback_collector
        self._db = db
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.patterns_file = self.storage_path / "task_patterns.json"
        self._patterns: dict[str, TaskPattern] = {}
        self._load_patterns()

    def _load_patterns(self) -> None:
        """Load previously learned patterns."""

        if self._db is not None:
            try:
                rows = self._db.get_task_patterns()
                for row in rows:
                    self._patterns[row["task_type"]] = TaskPattern(
                        task_type=row["task_type"],
                        relevant_symbols=json.loads(row.get("relevant_symbols", "[]")),
                        relevant_files=json.loads(row.get("relevant_files", "[]")),
                        avg_tokens_used=row.get("avg_tokens_used", 0) or 0,
                        avg_context_items=row.get("avg_context_items", 0) or 0,
                        success_rate=row.get("success_rate", 0.0) or 0.0,
                        occurrence_count=row.get("occurrence_count", 0) or 0,
                    )
                return
            except Exception:
                pass

        if self.patterns_file.exists():
            try:
                with open(self.patterns_file, encoding="utf-8") as f:
                    data = json.load(f)
                for task_type, p in data.items():
                    self._patterns[task_type] = TaskPattern(
                        task_type=task_type,
                        relevant_symbols=p.get("relevant_symbols", []),
                        relevant_files=p.get("relevant_files", []),
                        avg_tokens_used=p.get("avg_tokens_used", 0),
                        avg_context_items=p.get("avg_context_items", 0),
                        success_rate=p.get("success_rate", 0.0),
                        occurrence_count=p.get("occurrence_count", 0),
                    )
            except (json.JSONDecodeError, KeyError):
                pass

    def _save_patterns(self) -> None:
        """Persist learned patterns."""

        data = {}
        for task_type, p in self._patterns.items():
            data[task_type] = {
                "relevant_symbols": p.relevant_symbols,
                "relevant_files": p.relevant_files,
                "avg_tokens_used": p.avg_tokens_used,
                "avg_context_items": p.avg_context_items,
                "success_rate": p.success_rate,
                "occurrence_count": p.occurrence_count,
            }
            if self._db is not None:
                try:
                    self._db.upsert_task_pattern(
                        {
                            "task_type": task_type,
                            "relevant_symbols": p.relevant_symbols,
                            "relevant_files": p.relevant_files,
                            "avg_tokens_used": p.avg_tokens_used,
                            "avg_context_items": p.avg_context_items,
                            "success_rate": p.success_rate,
                            "occurrence_count": p.occurrence_count,
                            "updated_at": datetime.now().isoformat(),
                        }
                    )
                except Exception:
                    pass

        with open(self.patterns_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def learn_from_history(self, days: int = 30) -> dict[str, TaskPattern]:
        """Analyze recent operations and update patterns."""

        metrics = self.feedback.load_metrics(limit=5000)
        if not metrics:
            return self._patterns

        by_task: dict[str, list[Any]] = {}
        for m in metrics:
            tt = m.task_type or "unknown"
            if tt not in by_task:
                by_task[tt] = []
            by_task[tt].append(m)

        for task_type, task_metrics in by_task.items():
            successful = [m for m in task_metrics if m.success is True]
            total = len(task_metrics)

            if task_type not in self._patterns:
                self._patterns[task_type] = TaskPattern(task_type=task_type)

            pattern = self._patterns[task_type]
            pattern.occurrence_count += total

            if successful:
                pattern.success_rate = (
                    len(successful) / total if total > 0 else 0.0
                )
                pattern.avg_tokens_used = int(
                    sum(m.tokens_used for m in successful) / len(successful)
                )
                pattern.avg_context_items = int(
                    sum(m.context_items_selected for m in successful)
                    / len(successful)
                )

                files: set[str] = set()
                for m in successful:
                    if "relevant_files" in m.metadata:
                        files.update(m.metadata["relevant_files"])
                if files:
                    pattern.relevant_files = sorted(files)[:50]

        self._save_patterns()
        return self._patterns

    def get_pattern(self, task_type: str) -> TaskPattern | None:
        """Get the learned pattern for a task type."""

        return self._patterns.get(task_type)

    def suggest_context_boost(
        self,
        task_type: str,
        available_symbols: list[str],
    ) -> list[tuple[str, float]]:
        """Suggest symbol relevance boosts for a task type."""

        pattern = self._patterns.get(task_type)
        if not pattern:
            return []

        boosts: list[tuple[str, float]] = []
        relevant_set = set(pattern.relevant_symbols)
        for sym in available_symbols:
            if sym in relevant_set:
                boost = pattern.success_rate * 0.5 + 0.1
                boosts.append((sym, boost))
        return boosts

    def get_all_patterns(self) -> dict[str, TaskPattern]:
        """Return all learned patterns."""

        return dict(self._patterns)
