"""Health checks for OpenContext components.

Doctor checks for knowledge graph, MCP server, agent configs,
and all new modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opencontext_core.config import OpenContextConfig
from opencontext_core.doctor.checks import HealthCheck


@dataclass
class ComponentCheck:
    """Result of a component health check."""

    name: str
    ok: bool
    status: str
    details: str
    recommendation: str | None = None


class ComponentDoctor:
    """Doctor checks for OpenContext components."""

    def __init__(self, config: OpenContextConfig) -> None:
        self.config = config

    def check_all(self) -> list[ComponentCheck]:
        """Run all component health checks."""

        checks = []
        checks.extend(self.check_knowledge_graph())
        checks.extend(self.check_mcp_server())
        checks.extend(self.check_agent_configs())
        checks.extend(self.check_sdd_orchestrator())
        checks.extend(self.check_skill_registry())
        checks.extend(self.check_memory_system())
        checks.extend(self.check_provider_adapters())
        return checks

    def check_knowledge_graph(self) -> list[ComponentCheck]:
        """Check knowledge graph health."""

        checks = []

        # Check database
        db_path = Path(".storage/opencontext/codegraph.db")
        if db_path.exists():
            from opencontext_core.indexing.graph_db import GraphDatabase

            try:
                db = GraphDatabase(db_path=db_path)
                stats = db.get_stats()
                db.close()

                checks.append(
                    ComponentCheck(
                        name="kg_database",
                        ok=True,
                        status="healthy",
                        details=f"Database exists with {stats.get('nodes', 0)} nodes, {stats.get('edges', 0)} edges",
                    )
                )

                # Check if FTS5 is working
                if stats.get("nodes", 0) > 0:
                    checks.append(
                        ComponentCheck(
                            name="kg_fts5",
                            ok=True,
                            status="healthy",
                            details="FTS5 index populated",
                        )
                    )
                else:
                    checks.append(
                        ComponentCheck(
                            name="kg_fts5",
                            ok=False,
                            status="warning",
                            details="FTS5 index empty - run 'opencontext index'",
                            recommendation="Index your project: opencontext index .",
                        )
                    )
            except Exception as exc:
                checks.append(
                    ComponentCheck(
                        name="kg_database",
                        ok=False,
                        status="error",
                        details=f"Database error: {exc}",
                    )
                )
        else:
            checks.append(
                ComponentCheck(
                    name="kg_database",
                    ok=False,
                    status="missing",
                    details="Knowledge graph database not found",
                    recommendation="Run 'opencontext index .' to build the knowledge graph",
                )
            )

        # Check tree-sitter
        from opencontext_core.indexing.tree_sitter_parser import TreeSitterParser

        parser = TreeSitterParser()
        checks.append(
            ComponentCheck(
                name="kg_parser",
                ok=parser._available,
                status="available" if parser._available else "fallback",
                details=(
                    "Tree-sitter parser available"
                    if parser._available
                    else "Using regex fallback parser"
                ),
                recommendation=(
                    "Install tree-sitter: pip install tree-sitter"
                    if not parser._available
                    else None
                ),
            )
        )

        return checks

    def check_mcp_server(self) -> list[ComponentCheck]:
        """Check MCP server health."""

        checks = []

        # Check if server module loads
        try:
            from opencontext_core.mcp_stdio import MCPServer

            checks.append(
                ComponentCheck(
                    name="mcp_module",
                    ok=True,
                    status="healthy",
                    details="MCP server module loaded",
                )
            )
        except ImportError as exc:
            checks.append(
                ComponentCheck(
                    name="mcp_module",
                    ok=False,
                    status="error",
                    details=f"MCP server import error: {exc}",
                )
            )

        return checks

    def check_agent_configs(self) -> list[ComponentCheck]:
        """Check agent configuration health."""

        checks = []

        # Check if agent installer works
        try:
            from opencontext_core.agent_installer import AgentInstaller

            installer = AgentInstaller()
            detected = installer.detect_installed_agents()

            checks.append(
                ComponentCheck(
                    name="agent_installer",
                    ok=True,
                    status="healthy",
                    details=f"Agent installer ready, {len(detected)} agents detected",
                )
            )

            if detected:
                checks.append(
                    ComponentCheck(
                        name="agents_detected",
                        ok=True,
                        status="healthy",
                        details=f"Detected: {', '.join(a.value for a in detected)}",
                    )
                )
            else:
                checks.append(
                    ComponentCheck(
                        name="agents_detected",
                        ok=False,
                        status="warning",
                        details="No AI agents detected on system",
                        recommendation="Install an agent (Claude Code, OpenCode, etc.)",
                    )
                )
        except Exception as exc:
            checks.append(
                ComponentCheck(
                    name="agent_installer",
                    ok=False,
                    status="error",
                    details=f"Agent installer error: {exc}",
                )
            )

        return checks

    def check_sdd_orchestrator(self) -> list[ComponentCheck]:
        """Check SDD orchestrator health."""

        checks = []

        try:
            from opencontext_core.agents.sdd_orchestrator import SDDOrchestrator

            checks.append(
                ComponentCheck(
                    name="sdd_orchestrator",
                    ok=True,
                    status="healthy",
                    details="SDD orchestrator loaded",
                )
            )
        except ImportError as exc:
            checks.append(
                ComponentCheck(
                    name="sdd_orchestrator",
                    ok=False,
                    status="error",
                    details=f"SDD orchestrator error: {exc}",
                )
            )

        # Check profiles
        try:
            from opencontext_core.sdd_profiles import SDDProfileManager

            manager = SDDProfileManager()
            profiles = manager.list_profiles()

            checks.append(
                ComponentCheck(
                    name="sdd_profiles",
                    ok=len(profiles) > 0,
                    status="healthy",
                    details=f"{len(profiles)} SDD profiles available",
                )
            )
        except Exception as exc:
            checks.append(
                ComponentCheck(
                    name="sdd_profiles",
                    ok=False,
                    status="error",
                    details=f"SDD profiles error: {exc}",
                )
            )

        return checks

    def check_skill_registry(self) -> list[ComponentCheck]:
        """Check skill registry health."""

        checks = []

        try:
            from opencontext_core.skills.registry import SkillRegistry

            registry = SkillRegistry()
            checks.append(
                ComponentCheck(
                    name="skill_registry",
                    ok=True,
                    status="healthy",
                    details="Skill registry loaded",
                )
            )
        except ImportError as exc:
            checks.append(
                ComponentCheck(
                    name="skill_registry",
                    ok=False,
                    status="error",
                    details=f"Skill registry error: {exc}",
                )
            )

        return checks

    def check_memory_system(self) -> list[ComponentCheck]:
        """Check memory system health."""

        checks = []

        try:
            from opencontext_core.memory.topic_keys import TopicKeyGenerator

            checks.append(
                ComponentCheck(
                    name="memory_topic_keys",
                    ok=True,
                    status="healthy",
                    details="Topic key generator loaded",
                )
            )
        except ImportError as exc:
            checks.append(
                ComponentCheck(
                    name="memory_topic_keys",
                    ok=False,
                    status="error",
                    details=f"Memory system error: {exc}",
                )
            )

        return checks

    def check_provider_adapters(self) -> list[ComponentCheck]:
        """Check provider adapter health."""

        checks = []

        try:
            from opencontext_core.providers.adapters import ProviderRegistry

            registry = ProviderRegistry()
            providers = registry.list_providers()
            available = [p for p in providers if p["available"]]

            checks.append(
                ComponentCheck(
                    name="provider_registry",
                    ok=True,
                    status="healthy",
                    details=f"{len(available)}/{len(providers)} providers available",
                )
            )

            for provider in providers:
                checks.append(
                    ComponentCheck(
                        name=f"provider_{provider['name']}",
                        ok=provider["available"],
                        status="available" if provider["available"] else "unavailable",
                        details=f"Models: {', '.join(provider['models'][:3])}..."
                        if provider["models"]
                        else "No models listed",
                        recommendation=None
                        if provider["available"]
                        else f"Set API key for {provider['name']}",
                    )
                )
        except ImportError as exc:
            checks.append(
                ComponentCheck(
                    name="provider_registry",
                    ok=False,
                    status="error",
                    details=f"Provider registry error: {exc}",
                )
            )

        return checks
