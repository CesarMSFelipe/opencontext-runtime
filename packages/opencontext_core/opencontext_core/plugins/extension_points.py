"""Extension-point vocabulary + contribution routing table (PR-015, PLG-CONV).

One :class:`ExtensionPoint` per ``contributes`` slot, and a routing table mapping
each point to (a) the public contract a contribution binds to and (b) the in-tree
registry/target it routes into. The lifecycle (``plugins/lifecycle.py``) walks a
manifest's typed ``contributes`` and uses this table to register contributions
into the target registries with PLUGIN provenance.

Layering (doc 58): plugin host (L11) — depends on the public contracts and the
L6 registry substrate downward, never the reverse.
"""

from __future__ import annotations

from dataclasses import dataclass

from opencontext_core.compat import StrEnum


class ExtensionPoint(StrEnum):
    """The extension points a plugin may contribute to (book §12 + PLG-CONV)."""

    WORKFLOWS = "workflows"
    PERSONAS = "personas"
    SKILLS = "skills"
    HARNESSES = "harnesses"
    POLICIES = "policies"
    PROVIDERS = "providers"
    KG_PROVIDERS = "kg_providers"
    MEMORY_PROVIDERS = "memory_providers"
    CONTEXT_STRATEGIES = "context_strategies"
    RUNTIME_INTELLIGENCE_ANALYZERS = "runtime_intelligence_analyzers"
    STUDIO_PANELS = "studio_panels"
    CLI_COMMANDS = "cli_commands"
    MCP_TOOLS = "mcp_tools"
    PROJECT_TEMPLATES = "project_templates"
    BENCHMARK_SUITES = "benchmark_suites"
    # PLG-CONV additions.
    EXECUTION_PROFILES = "execution_profiles"
    CACHE_PROVIDERS = "cache_providers"


@dataclass(frozen=True)
class ContributionRoute:
    """Where a contribution for one extension point goes.

    ``contract`` is the public contract name a contribution binds to (exported by
    ``plugins/contracts.py``). ``registry`` names the in-tree target the lifecycle
    registers the contribution into. ``permission`` is the deny-by-default
    capability the contribution's restricted operations are gated on (or ``None``
    when the point performs no restricted operation), enforced via the Policy
    Engine / ``PluginRegistry.is_allowed`` (book §12 Security; PLG-CONV).
    ``read_only`` marks points that may consume public contracts only and expose
    no mutation route (Studio panels — SPEC PLG-CONV).
    """

    point: ExtensionPoint
    contract: str
    registry: str
    permission: str | None = None
    read_only: bool = False


# Each point maps to its contract + target registry + the permission its restricted
# operations are gated on. ``None`` permission = the point performs no restricted
# operation at registration (gating still applies to any runtime capability use).
CONTRIBUTION_ROUTES: dict[ExtensionPoint, ContributionRoute] = {
    ExtensionPoint.WORKFLOWS: ContributionRoute(
        ExtensionPoint.WORKFLOWS, "WorkflowDefinition", "workflows.registry"
    ),
    ExtensionPoint.PERSONAS: ContributionRoute(
        ExtensionPoint.PERSONAS, "PersonaDefinition", "personas.registry.PersonaRegistry"
    ),
    ExtensionPoint.SKILLS: ContributionRoute(
        ExtensionPoint.SKILLS, "SkillDefinition", "skills.registry.SkillRegistryV2"
    ),
    ExtensionPoint.HARNESSES: ContributionRoute(
        ExtensionPoint.HARNESSES, "HarnessDefinition", "harness.registry.HarnessRegistry"
    ),
    ExtensionPoint.POLICIES: ContributionRoute(
        ExtensionPoint.POLICIES, "PolicyContract", "policy.engine", permission="provider"
    ),
    ExtensionPoint.PROVIDERS: ContributionRoute(
        ExtensionPoint.PROVIDERS,
        "ProviderAdapter",
        "providers.adapters.ProviderRegistry",
        permission="provider",
    ),
    ExtensionPoint.KG_PROVIDERS: ContributionRoute(
        ExtensionPoint.KG_PROVIDERS,
        "KnowledgeProvider",
        "graph.provider",
        permission="kg_write",
    ),
    ExtensionPoint.MEMORY_PROVIDERS: ContributionRoute(
        ExtensionPoint.MEMORY_PROVIDERS,
        "MemoryProvider",
        "memory.provider",
        permission="memory_write",
    ),
    ExtensionPoint.CONTEXT_STRATEGIES: ContributionRoute(
        ExtensionPoint.CONTEXT_STRATEGIES, "ContextStrategy", "context.strategies"
    ),
    ExtensionPoint.RUNTIME_INTELLIGENCE_ANALYZERS: ContributionRoute(
        ExtensionPoint.RUNTIME_INTELLIGENCE_ANALYZERS,
        "RuntimeIntelligenceAnalyzer",
        "runtime_intelligence.analyzers",
    ),
    ExtensionPoint.STUDIO_PANELS: ContributionRoute(
        ExtensionPoint.STUDIO_PANELS,
        "StudioPanel",
        "studio.panels",
        read_only=True,
    ),
    ExtensionPoint.CLI_COMMANDS: ContributionRoute(
        ExtensionPoint.CLI_COMMANDS, "CliCommand", "cli.commands", permission="command"
    ),
    ExtensionPoint.MCP_TOOLS: ContributionRoute(
        ExtensionPoint.MCP_TOOLS, "ToolDefinition", "tools.registry", permission="provider"
    ),
    ExtensionPoint.PROJECT_TEMPLATES: ContributionRoute(
        ExtensionPoint.PROJECT_TEMPLATES, "ProjectTemplate", "project.templates"
    ),
    ExtensionPoint.BENCHMARK_SUITES: ContributionRoute(
        ExtensionPoint.BENCHMARK_SUITES, "BenchmarkSuite", "evaluation.suites"
    ),
    ExtensionPoint.EXECUTION_PROFILES: ContributionRoute(
        ExtensionPoint.EXECUTION_PROFILES,
        "ExecutionProfile",
        "profiles.registry",
    ),
    ExtensionPoint.CACHE_PROVIDERS: ContributionRoute(
        ExtensionPoint.CACHE_PROVIDERS, "ResponseCache", "cache.registry"
    ),
}


def route_for(point: ExtensionPoint) -> ContributionRoute:
    """Return the :class:`ContributionRoute` for ``point`` (always present)."""
    return CONTRIBUTION_ROUTES[point]
