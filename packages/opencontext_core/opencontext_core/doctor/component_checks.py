"""Health checks for OpenContext components.

Doctor checks for knowledge graph, MCP server, agent configs,
and all new modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from opencontext_core.config import OpenContextConfig


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
        checks.extend(self.check_binary_path())
        return checks

    def check_binary_path(self) -> list[ComponentCheck]:
        """Detect a shadowed ``opencontext`` binary (multiple copies on PATH).

        When two installs (e.g. pip and pipx) both put ``opencontext`` on PATH,
        the first one wins and commands silently run an unexpected version. Report
        which copy resolves first and the others it shadows.
        """
        import os

        found: list[str] = []
        seen: set[str] = set()
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            if not directory:
                continue
            candidate = Path(directory) / "opencontext"
            try:
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    resolved = str(candidate.resolve())
                    if resolved not in seen:
                        seen.add(resolved)
                        found.append(str(candidate))
            except OSError:
                continue

        if len(found) <= 1:
            details = (
                f"opencontext resolves to {found[0]}"
                if found
                else "opencontext is not on PATH (running as a module)"
            )
            return [
                ComponentCheck(name="binary_path", ok=True, status="healthy", details=details)
            ]
        return [
            ComponentCheck(
                name="binary_path",
                ok=False,
                status="warning",
                details=(
                    f"{len(found)} opencontext binaries on PATH; '{found[0]}' shadows the rest: "
                    + ", ".join(found[1:])
                ),
                recommendation="Remove the older copies so one version resolves "
                "(e.g. 'pipx reinstall opencontext-cli').",
            )
        ]

    def check_knowledge_graph(self) -> list[ComponentCheck]:
        """Check knowledge graph health."""

        checks = []

        # Check database. Mirror GraphDatabase's legacy-name shim: when the
        # canonical context_graph.db is absent, the runtime transparently uses an
        # older codegraph.db, so the doctor must too — otherwise it reports a
        # healthy legacy-named graph as "missing".
        db_path = Path(".storage/opencontext/context_graph.db")
        if not db_path.exists():
            legacy_path = db_path.with_name("codegraph.db")
            if legacy_path.exists():
                db_path = legacy_path
        if db_path.exists():
            from opencontext_core.indexing.graph_db import GraphDatabase

            try:
                db = GraphDatabase(db_path=db_path)
                stats = db.get_stats()
                db.close()

                node_count = stats.get("nodes", 0)
                if node_count == 0:
                    # Tables present but empty — the classic signature of an
                    # interrupted/failed index. Retrieval silently degrades to
                    # manifest-only (no call graph, no docstring search) with no
                    # error, so surface it as unhealthy.
                    checks.append(
                        ComponentCheck(
                            name="kg_database",
                            ok=False,
                            status="empty",
                            details="Knowledge graph database exists but has 0 nodes "
                            "(likely an interrupted index).",
                            recommendation="Re-run `opencontext index .` to rebuild the graph.",
                        )
                    )
                else:
                    checks.append(
                        ComponentCheck(
                            name="kg_database",
                            ok=True,
                            status="healthy",
                            details=(
                                f"Database exists with {node_count} nodes, "
                                f"{stats.get('edges', 0)} edges"
                            ),
                        )
                    )
                    checks.append(self._check_freshness(db_path))

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

    def _check_freshness(self, db_path: Path) -> ComponentCheck:
        """Flag indexed files that changed or were deleted since the last index.

        A stale graph silently feeds the agent context for code that no longer
        exists — the kind of quiet wrongness that erodes trust in verified
        context. Surfaces it with a one-command fix.
        """
        from opencontext_core.indexing.knowledge_graph import KnowledgeGraph

        try:
            kg = KnowledgeGraph(db_path=db_path)
            report = kg.stale_files(Path("."))
            kg.close()
        except Exception as exc:
            return ComponentCheck(
                name="kg_freshness", ok=True, status="unknown",
                details=f"Could not check freshness: {exc}",
            )
        if report.total == 0:
            return ComponentCheck(
                name="kg_freshness", ok=True, status="fresh",
                details="Index is up to date with the working tree.",
            )
        bits = []
        if report.changed:
            bits.append(f"{len(report.changed)} changed")
        if report.deleted:
            bits.append(f"{len(report.deleted)} deleted")
        return ComponentCheck(
            name="kg_freshness", ok=False, status="stale",
            details=f"Index is behind the working tree ({', '.join(bits)} files).",
            recommendation="Re-run `opencontext index .` to refresh the graph.",
        )

    def check_mcp_server(self) -> list[ComponentCheck]:
        """Check MCP server health."""

        checks = []

        # Check if server module loads
        import importlib.util

        try:
            if importlib.util.find_spec("opencontext_core.mcp_stdio"):
                checks.append(
                    ComponentCheck(
                        name="mcp_module",
                        ok=True,
                        status="healthy",
                        details="MCP server module loaded",
                    )
                )
            else:
                checks.append(
                    ComponentCheck(
                        name="mcp_module",
                        ok=False,
                        status="missing",
                        details="MCP server module not available",
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

        import importlib.util

        try:
            if importlib.util.find_spec("opencontext_core.agents.sdd_orchestrator"):
                checks.append(
                    ComponentCheck(
                        name="sdd_orchestrator",
                        ok=True,
                        status="healthy",
                        details="SDD orchestrator loaded",
                    )
                )
            else:
                checks.append(
                    ComponentCheck(
                        name="sdd_orchestrator",
                        ok=False,
                        status="missing",
                        details="SDD orchestrator not available",
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
            from opencontext_core.skills.registry import SkillRegistry  # type: ignore[attr-defined]

            SkillRegistry()
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

        import importlib.util

        try:
            if importlib.util.find_spec("opencontext_core.memory.topic_keys"):
                checks.append(
                    ComponentCheck(
                        name="memory_topic_keys",
                        ok=True,
                        status="healthy",
                        details="Topic key generator loaded",
                    )
                )
            else:
                checks.append(
                    ComponentCheck(
                        name="memory_topic_keys",
                        ok=False,
                        status="missing",
                        details="Topic key generator not available",
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
