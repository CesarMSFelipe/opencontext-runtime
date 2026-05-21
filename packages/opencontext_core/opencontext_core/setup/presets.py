"""Preset and component catalog for the OpenContext setup system.

A preset is a named collection of components that target a specific use case.
A component is an installable feature with dependencies and requirements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ComponentStatus(Enum):
    """Installation status of a component."""

    NOT_INSTALLED = "not_installed"
    INSTALLED = "installed"
    NEEDS_UPDATE = "needs_update"
    BLOCKED = "blocked"


@dataclass
class ComponentDef:
    """Definition of an installable component."""

    id: str
    name: str
    description: str
    dependencies: list[str] = field(default_factory=list)
    optional_deps: list[str] = field(default_factory=list)
    requires_network: bool = False
    requires_python_package: str | None = None
    estimated_size: str = "small"  # small, medium, large

    @property
    def all_dependencies(self) -> list[str]:
        """All dependencies including optional ones."""
        return self.dependencies + self.optional_deps


# ── Component Catalog ──────────────────────────────────────────────────────

COMPONENT_CATALOG: dict[str, ComponentDef] = {
    "knowledge-graph": ComponentDef(
        id="knowledge-graph",
        name="Knowledge Graph",
        description="Code indexing, symbol search, FTS5 full-text search",
        requires_python_package="tree-sitter-python",
        estimated_size="medium",
    ),
    "call-graph": ComponentDef(
        id="call-graph",
        name="Call Graph",
        description="Function call analysis, callers/callees, impact analysis",
        dependencies=["knowledge-graph"],
        estimated_size="small",
    ),
    "learning": ComponentDef(
        id="learning",
        name="Learning System",
        description="Auto-optimize token budgets from usage patterns",
        estimated_size="small",
    ),
    "governance": ComponentDef(
        id="governance",
        name="Governance",
        description="Audit trails, data classification, policy enforcement",
        estimated_size="medium",
    ),
    "mcp-server": ComponentDef(
        id="mcp-server",
        name="MCP Server",
        description="Agent integration via MCP protocol (8 tools)",
        dependencies=["knowledge-graph"],
        estimated_size="small",
    ),
    "git-integration": ComponentDef(
        id="git-integration",
        name="Git Integration",
        description="Context from git history, blame, diff analysis",
        estimated_size="small",
    ),
    "embeddings": ComponentDef(
        id="embeddings",
        name="Embeddings",
        description="Vector embeddings for semantic understanding",
        dependencies=["knowledge-graph"],
        requires_network=True,
        estimated_size="medium",
    ),
    "semantic-search": ComponentDef(
        id="semantic-search",
        name="Semantic Search",
        description="Embedding-based semantic code search",
        dependencies=["embeddings"],
        estimated_size="small",
    ),
    "plugins": ComponentDef(
        id="plugins",
        name="Plugin System",
        description="Extensible plugin architecture with security permissions",
        estimated_size="small",
    ),
}


# ── Presets ────────────────────────────────────────────────────────────────


@dataclass
class PresetDef:
    """Definition of a setup preset."""

    id: str
    name: str
    description: str
    components: list[str]
    profile: str = "developer"
    default_agent: str = "opencode"


PRESET_CATALOG: dict[str, PresetDef] = {
    "full": PresetDef(
        id="full",
        name="Full",
        description="Everything — KG, learning, governance, MCP, plugins, and more",
        components=[
            "knowledge-graph",
            "call-graph",
            "learning",
            "governance",
            "mcp-server",
            "git-integration",
            "plugins",
        ],
    ),
    "minimal": PresetDef(
        id="minimal",
        name="Minimal",
        description="Just the basics — KG and git integration",
        components=[
            "knowledge-graph",
            "git-integration",
        ],
    ),
    "enterprise": PresetDef(
        id="enterprise",
        name="Enterprise",
        description="Governance, audit, team policies with full KG",
        components=[
            "knowledge-graph",
            "call-graph",
            "learning",
            "governance",
            "plugins",
        ],
        profile="security-officer",
    ),
    "air-gapped": PresetDef(
        id="air-gapped",
        name="Air-Gapped",
        description="Completely offline — no network features",
        components=[
            "knowledge-graph",
            "call-graph",
            "learning",
            "git-integration",
        ],
        profile="security-officer",
    ),
}


# ── Profile Definitions ───────────────────────────────────────────────────


@dataclass
class ProfileDef:
    """Definition of a user profile."""

    id: str
    name: str
    description: str
    security_mode: str
    features_defaults: dict[str, bool]
    default_agent: str = "opencode"


PROFILE_CATALOG: dict[str, ProfileDef] = {
    "developer": ProfileDef(
        id="developer",
        name="Developer",
        description="Optimized for speed — learning, MCP, full KG",
        security_mode="private_project",
        features_defaults={
            "knowledge_graph": True,
            "call_graph": True,
            "learning": True,
            "governance": False,
            "mcp_server": True,
            "git_integration": True,
            "embeddings": False,
            "semantic_search": False,
        },
    ),
    "security-officer": ProfileDef(
        id="security-officer",
        name="Security Officer",
        description="Optimized for compliance — governance, audit, minimal attack surface",
        security_mode="enterprise",
        features_defaults={
            "knowledge_graph": True,
            "call_graph": True,
            "learning": True,
            "governance": True,
            "mcp_server": False,
            "git_integration": True,
            "embeddings": False,
            "semantic_search": False,
        },
    ),
    "researcher": ProfileDef(
        id="researcher",
        name="Researcher",
        description="Optimized for exploration — KG, embeddings, semantic search",
        security_mode="private_project",
        features_defaults={
            "knowledge_graph": True,
            "call_graph": True,
            "learning": True,
            "governance": False,
            "mcp_server": False,
            "git_integration": True,
            "embeddings": True,
            "semantic_search": True,
        },
    ),
    "minimal": ProfileDef(
        id="minimal",
        name="Minimal",
        description="Bare minimum — KG and git only",
        security_mode="private_project",
        features_defaults={
            "knowledge_graph": True,
            "call_graph": False,
            "learning": False,
            "governance": False,
            "mcp_server": False,
            "git_integration": True,
            "embeddings": False,
            "semantic_search": False,
        },
    ),
}


def resolve_preset_components(preset_id: str) -> list[str]:
    """Resolve all components for a preset, including transitive deps."""

    preset = PRESET_CATALOG.get(preset_id)
    if not preset:
        raise ValueError(f"Unknown preset: {preset_id}")

    resolved: list[str] = []
    seen: set[str] = set()

    def _resolve(comp_id: str) -> None:
        if comp_id in seen:
            return
        seen.add(comp_id)
        comp = COMPONENT_CATALOG.get(comp_id)
        if comp:
            for dep in comp.dependencies:
                _resolve(dep)
        if comp_id not in resolved:
            resolved.append(comp_id)

    for cid in preset.components:
        _resolve(cid)

    return resolved


def get_available_presets() -> list[PresetDef]:
    """Return all available presets."""
    return list(PRESET_CATALOG.values())


def get_available_profiles() -> list[ProfileDef]:
    """Return all available profiles."""
    return list(PROFILE_CATALOG.values())


def get_available_components() -> list[ComponentDef]:
    """Return all available components."""
    return list(COMPONENT_CATALOG.values())
