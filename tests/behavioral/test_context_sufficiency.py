"""
Behavioral Contract Tests for OpenContext Runtime v2.
These define WHAT the system must do, not HOW.
All tests must pass before the change is considered complete.
"""

from datetime import UTC
from pathlib import Path


class TestTaskClassificationContract:
    """BCT-1: Classification must be deterministic and correct."""

    def test_bugfix_task_classified_correctly(self):
        """Bugfix keywords always produce bugfix classification."""
        from opencontext_core.context.planning.classifier import TaskClassifier

        result = TaskClassifier().classify("fix crash in authentication middleware")
        assert result.task_type == "bugfix"

    def test_security_task_requires_mutation(self):
        """Security tasks always require mutation testing."""
        from opencontext_core.context.planning.classifier import TaskClassifier

        result = TaskClassifier().classify("fix security vulnerability in login")
        assert result.requires_mutation is True

    def test_critical_escalation(self):
        """Critical keywords always escalate risk."""
        from opencontext_core.context.planning.classifier import TaskClassifier

        result = TaskClassifier().classify("critical production outage")
        assert result.risk_level == "critical"


class TestContextContractContract:
    """BCT-2: Contract must document knowns, unknowns, and verification requirements."""

    def test_contract_has_verification_gates(self):
        """Every contract must include at least one verification gate."""
        from opencontext_core.context.planning.classifier import TaskClassifier
        from opencontext_core.context.planning.contract import ContextContractBuilder
        from opencontext_core.context.planning.risk import RiskClassifier

        contract = ContextContractBuilder(
            classifier=TaskClassifier(),
            risk_classifier=RiskClassifier(),
        ).build("fix bug in user service")
        assert len(contract.must_verify) > 0

    def test_critical_contract_is_complete(self):
        """Critical tasks must produce complete contracts."""
        from opencontext_core.context.planning.classifier import TaskClassifier
        from opencontext_core.context.planning.contract import ContextContractBuilder
        from opencontext_core.context.planning.risk import RiskClassifier

        contract = ContextContractBuilder(
            classifier=TaskClassifier(),
            risk_classifier=RiskClassifier(),
        ).build("critical production crash in payment processor")
        assert contract.risk_tier == "critical"
        assert len(contract.must_verify) >= 3


class TestMemoryContract:
    """BCT-3: Memory must enrich future context after failures."""

    def test_failure_boost_increases_after_recording(self):
        """After recording a failure for a symbol, that symbol gets a boost."""
        import tempfile
        import uuid
        from datetime import datetime

        from opencontext_core.memory.graph import LocalMemoryStore
        from opencontext_core.models.agent_memory import DecayPolicy, MemoryLayer, MemoryRecord

        with tempfile.TemporaryDirectory() as d:
            store = LocalMemoryStore(Path(d) / "mem.db")
            record = MemoryRecord(
                id=str(uuid.uuid4()),
                layer=MemoryLayer.FAILURE,
                key="auth:AuthMiddleware",
                content="fix auth AuthMiddleware",
                linked_nodes=["AuthMiddleware"],
                tags=["AuthMiddleware"],
                decay_policy=DecayPolicy(enabled=False),
                created_at=datetime.now(tz=UTC),
                updated_at=datetime.now(tz=UTC),
            )
            store.write(record)
            boost = store.failure_boost(["AuthMiddleware"])
            assert boost.get("AuthMiddleware", 0.0) > 0.0

    def test_null_store_never_crashes(self):
        """NullAgentMemoryStore must never raise exceptions."""
        import uuid
        from datetime import datetime

        from opencontext_core.memory.agent import NullAgentMemoryStore
        from opencontext_core.models.agent_memory import DecayPolicy, MemoryLayer, MemoryRecord

        store = NullAgentMemoryStore()
        record = MemoryRecord(
            id=str(uuid.uuid4()),
            layer=MemoryLayer.FAILURE,
            key="test",
            content="test",
            tags=[],
            linked_nodes=[],
            decay_policy=DecayPolicy(enabled=False),
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        store.write(record)
        assert store.search("anything") == []
        assert store.failure_boost(["any_symbol"]) == {}


class TestScoringContract:
    """BCT-4: Hybrid scoring must prioritize required and memory-boosted candidates."""

    def test_required_candidate_scores_higher(self):
        """A required candidate must score higher than an identical non-required one."""
        from opencontext_core.retrieval.scoring import compute_hybrid_score

        base_params = dict(
            candidate_id="c1",
            candidate_source="file.py",
            candidate_source_type="file",
            candidate_source_trust=0.8,
            candidate_modified_at=None,
            candidate_tokens=500,
            lexical_score=0.5,
            memory_boost_map={},
            graph_distance_map={},
            is_test=False,
        )
        score_required = compute_hybrid_score(**base_params, is_required=True)
        score_not_required = compute_hybrid_score(**base_params, is_required=False)
        assert score_required > score_not_required

    def test_memory_boosted_candidate_scores_higher(self):
        """A memory-boosted candidate must score higher than the same candidate unboosted."""
        from opencontext_core.retrieval.scoring import compute_hybrid_score

        base_params = dict(
            candidate_id="c1",
            candidate_source="file.py",
            candidate_source_type="file",
            candidate_source_trust=0.8,
            candidate_modified_at=None,
            candidate_tokens=500,
            lexical_score=0.5,
            graph_distance_map={},
            is_required=False,
            is_test=False,
        )
        score_boosted = compute_hybrid_score(**base_params, memory_boost_map={"c1": 0.8})
        score_unboosted = compute_hybrid_score(**base_params, memory_boost_map={})
        assert score_boosted > score_unboosted


class TestTokenBudgetContract:
    """BCT-5: Token budget must scale with risk tier."""

    def test_cheap_tier_lower_budget_than_critical(self):
        """cheap tier has lower token budget than critical tier."""
        from opencontext_core.context.planning.contract import TIER_BUDGET

        assert TIER_BUDGET["cheap"] < TIER_BUDGET["critical"]

    def test_critical_tier_budget(self):
        """critical tier has budget >= 20000 tokens."""
        from opencontext_core.context.planning.contract import TIER_BUDGET

        assert TIER_BUDGET["critical"] >= 20_000


class TestGatesContract:
    """BCT-6: New gates must evaluate correctly."""

    def test_approval_gate_fails_without_approval(self):
        """ApprovalRequiredForWritesGate must FAIL when approval is required but not granted.

        Decoupled from budget_mode: gating is driven by approval_required.
        """
        from opencontext_core.harness.gates import ApprovalRequiredForWritesGate
        from opencontext_core.harness.models import GateStatus

        gate = ApprovalRequiredForWritesGate()
        result = gate.evaluate(approval_required=True, approved=False)
        assert result.status == GateStatus.FAILED

    def test_no_high_risk_exports_blocks_confidential(self):
        """NoHighRiskExportsGate must FAIL for confidential data to external provider."""
        from opencontext_core.harness.gates import NoHighRiskExportsGate
        from opencontext_core.harness.models import GateStatus

        gate = NoHighRiskExportsGate()
        result = gate.evaluate(has_confidential=True, is_external_provider=True)
        assert result.status == GateStatus.FAILED
