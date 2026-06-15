"""Token optimizer for dynamic budget management based on historical usage.

Adjusts token budgets per operation type based on actual effectiveness,
reducing waste while maintaining quality.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from opencontext_core.learning.feedback_collector import FeedbackCollector


@dataclass
class TokenBudgetProfile:
    """Optimized token budget for an operation type."""

    operation_type: str
    recommended_budget: int
    min_budget: int
    max_budget: int
    avg_actual_usage: int
    efficiency_score: float
    confidence: float


class TokenOptimizer:
    """Optimizes token budgets using historical operation data."""

    def __init__(
        self,
        feedback_collector: FeedbackCollector,
        db: Any | None = None,
        storage_path: Path | str = ".storage/opencontext/learning",
        default_budget: int = 10000,
    ) -> None:
        self.feedback = feedback_collector
        self._db = db
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.budgets_file = self.storage_path / "token_budgets.json"
        self.default_budget = default_budget
        self._budgets: dict[str, TokenBudgetProfile] = {}
        self._load_budgets()

    def _load_budgets(self) -> None:
        """Load persisted budget profiles."""

        if self._db is not None:
            try:
                rows = self._db.get_token_budgets()
                for row in rows:
                    self._budgets[row["operation_type"]] = TokenBudgetProfile(
                        operation_type=row["operation_type"],
                        recommended_budget=row.get("recommended_budget", 0) or 0,
                        min_budget=row.get("min_budget", 0) or 0,
                        max_budget=row.get("max_budget", 0) or 0,
                        avg_actual_usage=row.get("avg_actual_usage", 0) or 0,
                        efficiency_score=row.get("efficiency_score", 0.0) or 0.0,
                        confidence=row.get("confidence", 0.0) or 0.0,
                    )
                return
            except Exception:
                pass

        if self.budgets_file.exists():
            try:
                with open(self.budgets_file, encoding="utf-8") as f:
                    data = json.load(f)
                for op_type, b in data.items():
                    self._budgets[op_type] = TokenBudgetProfile(
                        operation_type=op_type,
                        recommended_budget=b["recommended_budget"],
                        min_budget=b["min_budget"],
                        max_budget=b["max_budget"],
                        avg_actual_usage=b["avg_actual_usage"],
                        efficiency_score=b["efficiency_score"],
                        confidence=b["confidence"],
                    )
            except (json.JSONDecodeError, KeyError):
                pass

    def _save_budgets(self) -> None:
        """Persist budget profiles."""

        data = {}
        for op_type, b in self._budgets.items():
            data[op_type] = {
                "recommended_budget": b.recommended_budget,
                "min_budget": b.min_budget,
                "max_budget": b.max_budget,
                "avg_actual_usage": b.avg_actual_usage,
                "efficiency_score": b.efficiency_score,
                "confidence": b.confidence,
            }
            if self._db is not None:
                try:
                    self._db.upsert_token_budget(
                        {
                            "operation_type": op_type,
                            "recommended_budget": b.recommended_budget,
                            "min_budget": b.min_budget,
                            "max_budget": b.max_budget,
                            "avg_actual_usage": b.avg_actual_usage,
                            "efficiency_score": b.efficiency_score,
                            "confidence": b.confidence,
                            "updated_at": datetime.now().isoformat(),
                        }
                    )
                except Exception:
                    pass

        with open(self.budgets_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def optimize_budgets(self) -> dict[str, TokenBudgetProfile]:
        """Analyze history and optimize budgets for all operation types."""

        metrics = self.feedback.load_metrics(limit=5000)
        if not metrics:
            return self._budgets

        by_type: dict[str, list[Any]] = {}
        for m in metrics:
            ot = m.operation_type
            if ot not in by_type:
                by_type[ot] = []
            by_type[ot].append(m)

        for op_type, op_metrics in by_type.items():
            if len(op_metrics) < 3:
                continue

            tokens_used = [m.tokens_used for m in op_metrics if m.tokens_used > 0]
            tokens_budgeted = [m.tokens_budgeted for m in op_metrics if m.tokens_budgeted > 0]

            if not tokens_used:
                continue

            avg_usage = sum(tokens_used) / len(tokens_used)
            if tokens_budgeted:
                avg_budget = sum(tokens_budgeted) / len(tokens_budgeted)
            else:
                avg_budget = self.default_budget

            if avg_budget > 0:
                efficiency = min(avg_usage / avg_budget, 1.0)
            else:
                efficiency = 1.0

            recommended = int(avg_usage * 1.2)
            min_budget = int(avg_usage * 0.8)
            max_budget = int(avg_usage * 2.0)
            confidence = min(len(op_metrics) / 50, 1.0)

            self._budgets[op_type] = TokenBudgetProfile(
                operation_type=op_type,
                recommended_budget=recommended,
                min_budget=min_budget,
                max_budget=max_budget,
                avg_actual_usage=int(avg_usage),
                efficiency_score=efficiency,
                confidence=confidence,
            )

        self._save_budgets()
        return self._budgets

    def get_budget(self, operation_type: str, fallback: int | None = None) -> int:
        """Get optimized budget for an operation type."""

        profile = self._budgets.get(operation_type)
        if profile and profile.confidence > 0.3:
            return profile.recommended_budget
        return fallback or self.default_budget

    def get_budget_profile(self, operation_type: str) -> TokenBudgetProfile | None:
        """Get full budget profile for an operation type."""

        return self._budgets.get(operation_type)

    def report_savings(self, applied_budgets: dict[str, int] | None = None) -> dict[str, Any]:
        """Report token savings, honestly separating projected from realized.

        ``projected_savings_tokens`` is the hypothetical waste reduction the
        optimizer estimates from observed efficiency — it is a projection, not a
        realized gain. ``realized_savings_tokens`` is only non-zero for operation
        types whose optimized budget has actually been *applied* (passed in via
        ``applied_budgets``); with nothing applied it is exactly 0 rather than a
        fabricated number.
        """

        applied = applied_budgets or {}
        projected_total = 0
        realized_total = 0
        details: dict[str, Any] = {}

        for op_type, profile in self._budgets.items():
            if profile.avg_actual_usage > 0 and profile.efficiency_score < 0.9:
                waste = (1.0 - profile.efficiency_score) * profile.avg_actual_usage
                projected = int(waste * profile.confidence)
                projected_total += projected

                # Realized savings: only when this op type's budget is applied.
                realized = projected if op_type in applied else 0
                realized_total += realized

                details[op_type] = {
                    "avg_usage": profile.avg_actual_usage,
                    "efficiency": round(profile.efficiency_score, 2),
                    "projected_savings": projected,
                    "realized_savings": realized,
                    "applied": op_type in applied,
                    # Backward-compatible alias.
                    "potential_savings": projected,
                }

        return {
            "realized_savings_tokens": realized_total,
            "projected_savings_tokens": projected_total,
            # Backward-compatible key (== projected; labeled potential).
            "total_potential_savings_tokens": projected_total,
            "by_operation_type": details,
            "recommendation": ("Run optimize_budgets() regularly to reduce token waste."),
        }
