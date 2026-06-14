"""Tests for concrete agent implementations."""
import asyncio
import pytest
from pathlib import Path


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestContextPlannerAgent:
    def test_produces_contract(self, tmp_path):
        from opencontext_core.agents.context_planner_agent import ContextPlannerAgent
        from opencontext_core.agents.base import AgentConfig
        cfg = AgentConfig(name="planner", type="context-planner", objectives=["fix auth crash"])
        agent = ContextPlannerAgent(cfg, tmp_path)
        result = run(agent.execute())
        assert "contract" in result
        assert "risk_tier" in result


class TestTDDEnforcerAgent:
    def test_runs_without_crash(self, tmp_path):
        from opencontext_core.agents.tdd_enforcer_agent import TDDEnforcerAgent
        from opencontext_core.agents.base import AgentConfig
        cfg = AgentConfig(name="tdd", type="tdd-enforcer", objectives=[])
        agent = TDDEnforcerAgent(cfg, tmp_path)
        result = run(agent.execute())
        assert "cycle_status" in result
        assert result["cycle_status"] in ("green", "red")


class TestSecurityAuditAgent:
    def test_clean_on_empty_dir(self, tmp_path):
        from opencontext_core.agents.security_audit_agent import SecurityAuditAgent
        from opencontext_core.agents.base import AgentConfig
        cfg = AgentConfig(name="sec", type="security-audit", objectives=[])
        agent = SecurityAuditAgent(cfg, tmp_path)
        result = run(agent.execute())
        assert result["clean"] is True

    def test_finds_secret_pattern(self, tmp_path):
        from opencontext_core.agents.security_audit_agent import SecurityAuditAgent
        from opencontext_core.agents.base import AgentConfig
        (tmp_path / "leak.py").write_text('API_KEY = "AKIAIOSFODNN7EXAMPLE123456789"')
        cfg = AgentConfig(name="sec", type="security-audit", objectives=[], scope={"paths": ["."]})
        agent = SecurityAuditAgent(cfg, tmp_path)
        result = run(agent.execute())
        assert result["finding_count"] > 0


class TestMutationAnalystAgent:
    def test_returns_unavailable_gracefully(self, tmp_path):
        from opencontext_core.agents.mutation_analyst_agent import MutationAnalystAgent
        from opencontext_core.agents.base import AgentConfig
        cfg = AgentConfig(name="mut", type="mutation-analyst", objectives=[])
        agent = MutationAnalystAgent(cfg, tmp_path)
        result = run(agent.execute())
        # If no framework installed, available=False, no crash
        assert "available" in result
        assert "status" in result


class TestAgentRegistry:
    def test_all_registered_types_instantiable(self, tmp_path):
        from opencontext_core.agents import AGENT_REGISTRY
        from opencontext_core.agents.base import AgentConfig
        for agent_type, AgentClass in AGENT_REGISTRY.items():
            cfg = AgentConfig(name=agent_type, type=agent_type, objectives=["test task"])
            agent = AgentClass(cfg, tmp_path)
            assert agent is not None
