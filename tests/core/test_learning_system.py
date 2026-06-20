"""Tests for the learning system."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.learning.feedback_collector import (
    FeedbackCollector,
)
from opencontext_core.learning.governance_harness import (
    DataClassification,
    ExecutionAction,
    GovernanceHarness,
)
from opencontext_core.learning.learning_orchestrator import LearningOrchestrator
from opencontext_core.learning.pattern_learner import PatternLearner, TaskPattern
from opencontext_core.learning.token_optimizer import TokenOptimizer


class TestFeedbackCollector:
    def test_start_operation_returns_id(self, tmp_path: Path) -> None:
        collector = FeedbackCollector(storage_path=tmp_path)
        op_id = collector.start_operation("ask", "test query")
        assert isinstance(op_id, str)
        assert len(op_id) == 8

    def test_finish_operation_persists_metric(self, tmp_path: Path) -> None:
        collector = FeedbackCollector(storage_path=tmp_path)
        op_id = collector.start_operation("ask", "test query")
        collector.finish_operation(op_id, tokens_used=100, context_items_selected=5, success=True)
        metrics = collector.load_metrics()
        assert len(metrics) == 1
        assert metrics[0].tokens_used == 100
        assert metrics[0].success is True

    def test_load_metrics_filters_by_type(self, tmp_path: Path) -> None:
        collector = FeedbackCollector(storage_path=tmp_path)
        id1 = collector.start_operation("ask", "q1")
        collector.finish_operation(id1)
        id2 = collector.start_operation("index", "q2")
        collector.finish_operation(id2)

        ask_metrics = collector.load_metrics(operation_type="ask")
        assert len(ask_metrics) == 1
        assert ask_metrics[0].operation_type == "ask"

    def test_statistics_empty(self, tmp_path: Path) -> None:
        collector = FeedbackCollector(storage_path=tmp_path)
        stats = collector.get_statistics()
        assert stats["total_operations"] == 0

    def test_statistics_with_data(self, tmp_path: Path) -> None:
        collector = FeedbackCollector(storage_path=tmp_path)
        id1 = collector.start_operation("ask", "q1")
        collector.finish_operation(id1, tokens_used=100, success=True)
        id2 = collector.start_operation("ask", "q2")
        collector.finish_operation(id2, tokens_used=200, success=False)

        stats = collector.get_statistics()
        assert stats["total_operations"] == 2
        assert stats["total_tokens_used"] == 300
        assert stats["successful_operations"] == 1
        assert stats["failed_operations"] == 1


class TestPatternLearner:
    def test_learn_from_empty_history(self, tmp_path: Path) -> None:
        feedback = FeedbackCollector(storage_path=tmp_path)
        learner = PatternLearner(feedback, storage_path=tmp_path)
        patterns = learner.learn_from_history()
        assert patterns == {}

    def test_learn_creates_pattern(self, tmp_path: Path) -> None:
        feedback = FeedbackCollector(storage_path=tmp_path)
        learner = PatternLearner(feedback, storage_path=tmp_path)

        op_id = feedback.start_operation("ask", "fix auth bug", task_type="bugfix")
        feedback.finish_operation(
            op_id,
            tokens_used=500,
            context_items_selected=3,
            success=True,
            metadata={"relevant_files": ["auth.py"]},
        )

        patterns = learner.learn_from_history()
        assert "bugfix" in patterns
        assert patterns["bugfix"].success_rate == 1.0
        assert patterns["bugfix"].occurrence_count == 1

    def test_suggest_context_boost(self, tmp_path: Path) -> None:
        feedback = FeedbackCollector(storage_path=tmp_path)
        learner = PatternLearner(feedback, storage_path=tmp_path)

        # Seed a pattern manually
        learner._patterns["bugfix"] = TaskPattern(
            task_type="bugfix",
            relevant_symbols=["authenticate", "hash_password"],
            success_rate=0.9,
        )

        boosts = learner.suggest_context_boost("bugfix", ["authenticate", "other_func"])
        assert len(boosts) == 1
        assert boosts[0][0] == "authenticate"


class TestTokenOptimizer:
    def test_optimize_empty_history(self, tmp_path: Path) -> None:
        feedback = FeedbackCollector(storage_path=tmp_path)
        optimizer = TokenOptimizer(feedback, storage_path=tmp_path)
        budgets = optimizer.optimize_budgets()
        assert budgets == {}

    def test_optimize_creates_budget(self, tmp_path: Path) -> None:
        feedback = FeedbackCollector(storage_path=tmp_path)
        optimizer = TokenOptimizer(feedback, storage_path=tmp_path)

        for _ in range(5):
            op_id = feedback.start_operation("ask", "test", tokens_budgeted=2000)
            feedback.finish_operation(op_id, tokens_used=1000)

        budgets = optimizer.optimize_budgets()
        assert "ask" in budgets
        assert budgets["ask"].recommended_budget > 0

    def test_get_budget_fallback(self, tmp_path: Path) -> None:
        feedback = FeedbackCollector(storage_path=tmp_path)
        optimizer = TokenOptimizer(feedback, storage_path=tmp_path, default_budget=5000)
        assert optimizer.get_budget("unknown") == 5000

    def test_acon_widens_budget_when_failures_omit_context(self, tmp_path: Path) -> None:
        # ACON-lite: same token usage, but one op type FAILED while omitting context
        # (over-compressed). Its budget must be widened vs a clean op type, not shrunk.
        feedback = FeedbackCollector(storage_path=tmp_path)
        optimizer = TokenOptimizer(feedback, storage_path=tmp_path)

        for _ in range(6):  # clean history — all succeed, nothing omitted
            op_id = feedback.start_operation("clean", "q", tokens_budgeted=2000)
            feedback.finish_operation(op_id, tokens_used=1000, success=True)
        for _ in range(6):  # failed while context was omitted -> over-compressed
            op_id = feedback.start_operation("starved", "q", tokens_budgeted=2000)
            feedback.finish_operation(
                op_id, tokens_used=1000, context_items_omitted=4, success=False
            )

        budgets = optimizer.optimize_budgets()
        # Same avg usage (1000) but the starved type gets a larger budget.
        assert budgets["starved"].recommended_budget > budgets["clean"].recommended_budget

    def test_report_savings(self, tmp_path: Path) -> None:
        feedback = FeedbackCollector(storage_path=tmp_path)
        optimizer = TokenOptimizer(feedback, storage_path=tmp_path)

        for _ in range(5):
            op_id = feedback.start_operation("ask", "test", tokens_budgeted=2000)
            feedback.finish_operation(op_id, tokens_used=500)

        optimizer.optimize_budgets()
        report = optimizer.report_savings()
        assert "total_potential_savings_tokens" in report


class TestGovernanceHarness:
    def test_check_policy_compliant(self, tmp_path: Path) -> None:
        harness = GovernanceHarness(storage_path=tmp_path)
        result = harness.check_policy(
            ExecutionAction.QUERY,
            tokens_estimate=1000,
            file_count=10,
        )
        assert result["allowed"] is True
        assert result["reason"] == "Policy compliant"

    def test_check_policy_violation(self, tmp_path: Path) -> None:
        harness = GovernanceHarness(storage_path=tmp_path)
        result = harness.check_policy(
            ExecutionAction.QUERY,
            tokens_estimate=999999,
            file_count=10,
        )
        assert result["allowed"] is False
        assert "exceeds maximum" in result["reason"]

    def test_audit_and_retrieve(self, tmp_path: Path) -> None:
        harness = GovernanceHarness(storage_path=tmp_path)
        record = harness.audit(
            action="query",
            actor="test",
            query="test query",
            tokens_used=100,
            data_classification=DataClassification.INTERNAL,
            result="success",
        )
        assert record.record_id
        assert record.checksum

        trail = harness.get_audit_trail()
        assert len(trail) == 1
        assert trail[0].action == "query"

    def test_verify_integrity(self, tmp_path: Path) -> None:
        harness = GovernanceHarness(storage_path=tmp_path)
        harness.audit(
            action="query",
            actor="test",
            query="test",
            tokens_used=100,
            data_classification=DataClassification.INTERNAL,
            result="ok",
        )
        result = harness.verify_integrity()
        assert result["status"] == "valid"
        assert result["valid_records"] == 1


class TestLearningOrchestrator:
    def test_initialization(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        orch = LearningOrchestrator(
            storage_path=tmp_path,
            kg_db_path=db_path,
            default_token_budget=8000,
        )
        assert orch.feedback is not None
        assert orch.governance is not None
        assert orch.patterns is not None
        assert orch.optimizer is not None

    def test_operation_tracking(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        orch = LearningOrchestrator(storage_path=tmp_path, kg_db_path=db_path)
        op_id = orch.start_operation("ask", "test query")
        assert isinstance(op_id, str)
        orch.finish_operation(op_id, tokens_used=100, success=True)

        stats = orch.get_statistics()
        assert stats["feedback"]["total_operations"] == 1

    def test_policy_check(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        orch = LearningOrchestrator(storage_path=tmp_path, kg_db_path=db_path)
        result = orch.check_policy("query", tokens_estimate=1000)
        assert result["allowed"] is True

    def test_learn_cycle(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        orch = LearningOrchestrator(storage_path=tmp_path, kg_db_path=db_path)

        for _ in range(5):
            op_id = orch.start_operation("ask", "test")
            orch.finish_operation(op_id, tokens_used=500, success=True)

        result = orch.learn()
        assert result["patterns_learned"] >= 0
        assert result["budgets_optimized"] >= 0

    def test_get_optimized_budget(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        orch = LearningOrchestrator(
            storage_path=tmp_path,
            kg_db_path=db_path,
            default_token_budget=10000,
        )
        # Without data, should return fallback
        assert orch.get_optimized_budget("ask") == 10000
