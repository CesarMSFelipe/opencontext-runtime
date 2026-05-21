"""Learning orchestrator that coordinates all self-improvement components.

Integrates feedback collection, pattern learning, token optimization,
and governance enforcement into a unified system.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from opencontext_core.learning.feedback_collector import FeedbackCollector
from opencontext_core.learning.governance_harness import (
    DataClassification,
    ExecutionAction,
    GovernanceHarness,
)
from opencontext_core.learning.pattern_learner import PatternLearner
from opencontext_core.learning.token_optimizer import TokenOptimizer


class LearningOrchestrator:
    """Central coordinator for the self-improvement system."""

    def __init__(
        self,
        storage_path: Path | str = ".storage/opencontext/learning",
        kg_db_path: Path | str = ".storage/opencontext/codegraph.db",
        default_token_budget: int = 10000,
    ) -> None:
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # Lazy-load GraphDatabase if available
        db = self._try_load_db(kg_db_path)

        self.feedback = FeedbackCollector(self.storage_path, db=db)
        self.governance = GovernanceHarness(db=db, storage_path=self.storage_path)
        self.patterns = PatternLearner(self.feedback, db=db, storage_path=self.storage_path)
        self.optimizer = TokenOptimizer(
            self.feedback,
            db=db,
            storage_path=self.storage_path,
            default_budget=default_token_budget,
        )

    def _try_load_db(self, db_path: Path | str) -> Any | None:
        """Attempt to load GraphDatabase for unified storage."""

        try:
            from opencontext_core.indexing.graph_db import GraphDatabase

            db = GraphDatabase(db_path=db_path)
            db.init_schema()
            return db
        except Exception:
            return None

    # ---- Feedback Collection ----

    def start_operation(
        self,
        operation_type: str,
        query: str,
        task_type: str | None = None,
        tokens_budgeted: int = 0,
    ) -> str:
        """Begin tracking an operation. Returns operation ID."""

        return self.feedback.start_operation(operation_type, query, task_type, tokens_budgeted)

    def finish_operation(
        self,
        operation_id: str,
        **kwargs: Any,
    ) -> None:
        """Complete tracking an operation."""

        self.feedback.finish_operation(operation_id, **kwargs)

    # ---- Governance ----

    def check_policy(
        self,
        action: str,
        tokens_estimate: int = 0,
        file_count: int = 0,
        data_classification: str = "internal",
    ) -> dict[str, Any]:
        """Check if operation complies with governance policy."""

        dc = DataClassification(data_classification)
        return self.governance.check_policy(
            ExecutionAction(action),
            tokens_estimate=tokens_estimate,
            file_count=file_count,
            data_classification=dc,
        )

    def audit(
        self,
        action: str,
        actor: str,
        query: str,
        tokens_used: int,
        data_classification: str,
        result: str,
    ) -> None:
        """Record an audit entry."""

        dc = DataClassification(data_classification)
        self.governance.audit(action, actor, query, tokens_used, dc, result)

    # ---- Learning ----

    def learn(self) -> dict[str, Any]:
        """Run learning cycle: patterns + budgets."""

        patterns = self.patterns.learn_from_history()
        budgets = self.optimizer.optimize_budgets()

        return {
            "patterns_learned": len(patterns),
            "budgets_optimized": len(budgets),
            "savings_report": self.optimizer.report_savings(),
        }

    def get_optimized_budget(self, operation_type: str, fallback: int | None = None) -> int:
        """Get optimized token budget for an operation."""

        return self.optimizer.get_budget(operation_type, fallback)

    def get_pattern(self, task_type: str) -> Any | None:
        """Get learned pattern for a task type."""

        return self.patterns.get_pattern(task_type)

    def suggest_context_boost(
        self,
        task_type: str,
        available_symbols: list[str],
    ) -> list[tuple[str, float]]:
        """Get relevance boosts for symbols based on learned patterns."""

        return self.patterns.suggest_context_boost(task_type, available_symbols)

    # ---- Reporting ----

    def get_statistics(self) -> dict[str, Any]:
        """Get comprehensive system statistics."""

        return {
            "feedback": self.feedback.get_statistics(),
            "patterns": {
                task_type: {
                    "relevant_symbols": p.relevant_symbols[:10],
                    "success_rate": p.success_rate,
                    "occurrences": p.occurrence_count,
                }
                for task_type, p in self.patterns.get_all_patterns().items()
            },
            "budgets": {
                op_type: {
                    "recommended": b.recommended_budget,
                    "efficiency": round(b.efficiency_score, 2),
                    "confidence": round(b.confidence, 2),
                }
                for op_type, b in self.optimizer._budgets.items()
            },
            "governance": self.governance.verify_integrity(),
        }
