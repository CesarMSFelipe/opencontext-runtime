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
    
    # Run code review analysis
    result = orchestrator.run_agent("code-review")
    print(result.report)
    
    # Run security audit
    result = orchestrator.run_agent("security-audit")
    print(result.metrics)
"""

from .loader import load_agent_config, list_available_agents
from .orchestrator import AgentOrchestrator, AgentResult
from .base import BaseAgent

__all__ = [
    "AgentOrchestrator",
    "AgentResult",
    "BaseAgent",
    "load_agent_config",
    "list_available_agents",
]
