"""Agent system for OpenContext Runtime.

This module provides an agent-based interface to OpenContext without requiring CLI.
Agents are configured via YAML profiles in .agents/profiles/ and handle:
- Automatic token management
- Memory persistence
- Index caching
- Analysis orchestration

Example usage (no CLI required):

    from opencontext_core.agents import AgentOrchestrator

    orchestrator = AgentOrchestrator(project_root=".")

    result = orchestrator.run_agent("code-review")
    print(result.report)

    result = orchestrator.run_agent("security-audit")
    print(result.metrics)
"""

from .base import BaseAgent
from .code_review_agent import CodeReviewAgent
from .context_planner_agent import ContextPlannerAgent
from .loader import list_available_agents, load_agent_config
from .mutation_analyst_agent import MutationAnalystAgent
from .orchestrator import AgentOrchestrator, AgentResult
from .security_audit_agent import SecurityAuditAgent
from .tdd_enforcer_agent import TDDEnforcerAgent

# DEPRECATED(2.0): dead registry of the deprecated agent SDK
# (no reader outside this package/tests). Remove in 2.0.
AGENT_REGISTRY: dict[str, type] = {
    "context-planner": ContextPlannerAgent,
    "tdd-enforcer": TDDEnforcerAgent,
    "mutation-analyst": MutationAnalystAgent,
    "security-audit": SecurityAuditAgent,
    "code-review": CodeReviewAgent,
}

__all__ = [
    "AGENT_REGISTRY",
    "AgentOrchestrator",
    "AgentResult",
    "BaseAgent",
    "CodeReviewAgent",
    "ContextPlannerAgent",
    "MutationAnalystAgent",
    "SecurityAuditAgent",
    "TDDEnforcerAgent",
    "list_available_agents",
    "load_agent_config",
]
