"""Agent orchestrator for coordinating analysis across multiple agents."""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .base import AgentConfig, BaseAgent
from .hook_handlers import DEFAULT_HANDLERS
from .hooks import HookEvent, HookRegistry
from .loader import list_available_agents
from .memory_manager import MemoryManager
from .token_manager import TokenBudget


class AgentResult(BaseModel):
    """Result from agent execution."""

    agent_name: str = Field(..., description="Name of executed agent")
    agent_type: str = Field(..., description="Type of agent")
    status: str = Field(..., description="Success or error status")
    findings: list[dict[str, Any]] = Field(default_factory=list, description="Analysis findings")
    report: str = Field(default="", description="Formatted report")
    metrics: dict[str, Any] = Field(default_factory=dict, description="Analysis metrics")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Execution metadata")
    error: str | None = Field(None, description="Error message if failed")

    model_config = {"arbitrary_types_allowed": True}


class AgentOrchestrator:
    """Orchestrates agent execution with automatic token and memory management.

    This is the primary interface for using OpenContext without CLI.

    Example:
        orchestrator = AgentOrchestrator(project_root=".")
        result = orchestrator.run_agent("code-review")
        print(result.report)
    """

    def __init__(
        self,
        project_root: Path | str = ".",
        agents_dir: Path | None = None,
        cache_dir: Path | None = None,
    ):
        """Initialize orchestrator.

        Args:
            project_root: Root directory of project to analyze
            agents_dir: Directory containing agent profiles (default: .agents/)
            cache_dir: Directory for caching results (default: .agents/cache/)
        """
        self.project_root = Path(project_root).resolve()
        self.agents_dir = Path(agents_dir) if agents_dir else self.project_root / ".agents"
        self.cache_dir = Path(cache_dir) if cache_dir else self.agents_dir / "cache"

        # Create directories if needed
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Initialize hook system with default handlers
        self.hooks = HookRegistry()
        for event, handlers in DEFAULT_HANDLERS.items():
            for handler in handlers:
                self.hooks.register(event, handler)

        # Load available agents
        self.agents: dict[str, AgentConfig] = {}
        self._load_agents()

        # Fire session start
        self.hooks.trigger(HookEvent.SESSION_START, project_root=str(self.project_root))

    def _load_agents(self) -> None:
        """Load all available agent configurations."""
        agent_list = list_available_agents(self.agents_dir)
        for agent_name, _, config in agent_list:
            self.agents[agent_name] = config

    def list_agents(self) -> list[str]:
        """List all available agent types.

        Returns:
            List of agent identifiers
        """
        return list(self.agents.keys())

    def get_agent_config(self, agent_name: str) -> AgentConfig | None:
        """Get configuration for specific agent.

        Args:
            agent_name: Agent identifier (type name)

        Returns:
            AgentConfig or None if not found
        """
        return self.agents.get(agent_name)

    def run_agent(
        self,
        agent_name: str,
        custom_objectives: list[str] | None = None,
        **kwargs: Any,
    ) -> AgentResult:
        """Run a single agent analysis.

        This is the main entry point for agent execution without CLI.

        Args:
            agent_name: Agent to run (e.g., "code-review", "security-audit")
            custom_objectives: Override objectives from config
            **kwargs: Additional options (token_budget, memory_policy, etc)

        Returns:
            AgentResult with findings, metrics, and metadata
        """
        config = self.get_agent_config(agent_name)
        if not config:
            return AgentResult(
                agent_name=agent_name,
                agent_type=agent_name,
                status="error",
                error=f"Agent not found: {agent_name}",
            )

        if not config.enabled:
            return AgentResult(
                agent_name=config.name,
                agent_type=config.type,
                status="error",
                error=f"Agent is disabled: {config.name}",
            )

        # Apply overrides
        if custom_objectives:
            config.objectives = custom_objectives

        # Create memory and token managers
        memory_cfg = config.memory_policy or {}
        memory = MemoryManager(
            max_entries=memory_cfg.get("max_entries", 100),
            ttl_minutes=memory_cfg.get("ttl_minutes"),
        )

        token_cfg = config.token_budget or {}
        token_budget = TokenBudget(
            max_per_query=token_cfg.get("max_per_query", 6500),
            max_total=token_cfg.get("max_total", 50000),
            context_ratio=token_cfg.get("context_ratio", 0.7),
        )

        # Create appropriate agent instance based on type
        agent = self._create_agent(config, memory, token_budget)
        if agent is None:
            return AgentResult(
                agent_name=config.name,
                agent_type=config.type,
                status="error",
                error=f"Unable to create agent instance: {config.type}",
            )

        # Execute agent (simplified - normally would be async)
        try:
            # For now, create a mock result
            # In production, this would call agent.run()
            result_data = self._mock_agent_execution(config, agent)

            result = AgentResult(
                agent_name=config.name,
                agent_type=config.type,
                status="success",
                findings=result_data.get("findings", []),
                report=result_data.get("report", ""),
                error=None,
                metrics={
                    "token_budget": token_budget.to_dict(),
                    "memory_usage": memory.to_dict(),
                },
                metadata={
                    "objectives": config.objectives,
                    "scope": config.scope or {},
                    "provider": config.provider or {},
                },
            )
            self.hooks.trigger(
                HookEvent.POST_TOOL,
                project_root=str(self.project_root),
                tool_name="run_agent",
                status="success",
                agent_name=config.name,
            )
            return result
        except Exception as e:
            result = AgentResult(
                agent_name=config.name,
                agent_type=config.type,
                status="error",
                error=str(e),
            )
            self.hooks.trigger(
                HookEvent.POST_TOOL,
                project_root=str(self.project_root),
                tool_name="run_agent",
                status="error",
                agent_name=config.name,
            )
            return result

    def run_all_agents(self) -> dict[str, AgentResult]:
        """Run all enabled agents sequentially.

        Returns:
            Dictionary mapping agent names to results
        """
        results = {}
        for agent_name in self.list_agents():
            config = self.get_agent_config(agent_name)
            if config and config.enabled:
                results[agent_name] = self.run_agent(agent_name)
        return results

    def _create_agent(
        self,
        config: AgentConfig,
        memory: MemoryManager,
        token_budget: TokenBudget,
    ) -> BaseAgent | None:
        """Create appropriate agent instance based on type.

        Args:
            config: Agent configuration
            memory: Memory manager for agent
            token_budget: Token budget manager

        Returns:
            BaseAgent instance or None if type unknown
        """
        from opencontext_core.agents import AGENT_REGISTRY
        AgentClass = AGENT_REGISTRY.get(config.type)
        if AgentClass is not None:
            return AgentClass(config, self.project_root)
        return None

    def _mock_agent_execution(self, config: AgentConfig, agent: BaseAgent | None) -> dict[str, Any]:
        """Generate mock execution result for demonstration.

        Args:
            config: Agent configuration
            agent: Agent instance (unused for mock)

        Returns:
            Mock result data
        """
        return {
            "findings": [
                {
                    "type": "info",
                    "severity": "low",
                    "message": f"Analyzed project using {config.type} agent",
                    "location": "project_root",
                },
            ],
            "report": f"""
# {config.name} Report

**Objectives:**
{chr(10).join(f"- {obj}" for obj in config.objectives)}

**Status:** Analysis configured and ready
**Project:** {self.project_root.name}
**Configuration:** {config.type}

This agent is configured and ready to execute.
To run actual analysis, integrate with real provider backend.

**Next Steps:**
1. Implement specific agent analysis logic
2. Connect to LLM provider
3. Parse and format findings
4. Generate detailed report
""",
        }

    def export_results(self, results: dict[str, AgentResult], output_file: Path) -> None:
        """Export agent results to JSON file.

        Args:
            results: Results from agent executions
            output_file: Where to save JSON
        """
        output_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            name: {
                "agent_name": result.agent_name,
                "agent_type": result.agent_type,
                "status": result.status,
                "findings_count": len(result.findings),
                "metrics": result.metrics,
                "metadata": result.metadata,
            }
            for name, result in results.items()
        }
        with open(output_file, "w") as f:
            json.dump(data, f, indent=2)
