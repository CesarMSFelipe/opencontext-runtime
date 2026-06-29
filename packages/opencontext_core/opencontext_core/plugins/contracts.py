"""Public SDK contract surface for plugins (PR-015, book §12 Contracts, §37).

This module is the *only* surface a plugin should import. It re-exports the
existing in-tree Protocols/Definitions as the stable public contract per
extension point (no parallel types), and declares thin Protocols for the points
without an existing in-tree contract. Plugins bind to these contracts and never
import private Runtime modules (doc 58: plugins compile against public contracts
only; doc 59: Plugin Contract v1 — also public).

``__all__`` is the stable public surface; nothing private is exported. Each name
maps to one extension point in ``plugins/extension_points.py``.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

# ── Re-exported existing contracts (reuse, do not redefine) ──────────────────
from opencontext_core.cache.base import ResponseCache, SemanticCache
from opencontext_core.evaluation.evaluator import Evaluator
from opencontext_core.harness.definition import HarnessDefinition
from opencontext_core.harness.results import HarnessResult
from opencontext_core.llm.gateway import LLMGateway
from opencontext_core.memory.provider import MemoryProvider
from opencontext_core.oc_new.models import PhaseDefinition
from opencontext_core.personas.definition import PersonaDefinition
from opencontext_core.plugins.knowledge_provider import KnowledgeProvider
from opencontext_core.plugins.manifest import (
    PLUGIN_CONTRACT_VERSION,
    PLUGIN_SCHEMA_VERSION,
    PluginContributions,
    PluginManifest,
    PluginPermissions,
    PluginRequires,
)
from opencontext_core.profiles.definition import (
    ExecutionProfile,
    ExecutionProfileStrategy,
)
from opencontext_core.providers.adapters import ProviderAdapter
from opencontext_core.registries.base import RegistryMetadata, TrustLevel
from opencontext_core.skills.definition import SkillDefinition
from opencontext_core.tools.registry import ToolDefinition
from opencontext_core.workflows.definition import WorkflowDefinition


# ── Thin Protocols for points without an existing in-tree contract ───────────
@runtime_checkable
class PolicyContract(Protocol):
    """A contributed policy: decides on a request, never self-grants (book §12)."""

    def decide(self, request: Any) -> Any: ...


@runtime_checkable
class ContextStrategy(Protocol):
    """A contributed context-assembly strategy (book §12 Context strategies)."""

    def build(self, task: str, budget: Any) -> Any: ...


@runtime_checkable
class RuntimeIntelligenceAnalyzer(Protocol):
    """A contributed Runtime Intelligence analyzer (read-only report producer)."""

    def analyze(self, snapshot: Any) -> Any: ...


@runtime_checkable
class StudioPanel(Protocol):
    """A contributed Studio panel.

    Studio panels consume public contracts only and expose no mutation route
    (book §37: "Studio panels cannot execute Runtime operations directly";
    SPEC PLG-CONV — read-only). The contract intentionally declares only a
    read-shaped ``render``; it must NOT carry any write/execute method.
    """

    def render(self, view_model: Any) -> Any: ...


@runtime_checkable
class CliCommand(Protocol):
    """A contributed CLI command (book §12 CLI commands)."""

    name: str

    def run(self, args: Any) -> int: ...


@runtime_checkable
class ProjectTemplate(Protocol):
    """A contributed project template (book §12 Project templates)."""

    name: str

    def files(self) -> dict[str, str]: ...


@runtime_checkable
class BenchmarkSuite(Protocol):
    """A contributed benchmark suite, runnable by the PR-017 runner (book §12).

    A suite reports a pass/fail verdict the benchmark gate consumes before
    activation (SPEC PR-015-BENCH; PLG-CONV — benchmarkable).
    """

    name: str

    def cases(self) -> list[Any]: ...


# The public contract name (as referenced by CONTRIBUTION_ROUTES) → the type.
# Lets the conformance suite verify every extension point resolves to a contract.
CONTRACTS: dict[str, type] = {
    "WorkflowDefinition": WorkflowDefinition,
    "PersonaDefinition": PersonaDefinition,
    "SkillDefinition": SkillDefinition,
    "HarnessDefinition": HarnessDefinition,
    "PolicyContract": PolicyContract,
    "ProviderAdapter": ProviderAdapter,
    "KnowledgeProvider": KnowledgeProvider,
    "MemoryProvider": MemoryProvider,
    "ContextStrategy": ContextStrategy,
    "RuntimeIntelligenceAnalyzer": RuntimeIntelligenceAnalyzer,
    "StudioPanel": StudioPanel,
    "CliCommand": CliCommand,
    "ToolDefinition": ToolDefinition,
    "ProjectTemplate": ProjectTemplate,
    "BenchmarkSuite": BenchmarkSuite,
    "ExecutionProfile": ExecutionProfile,
    "ResponseCache": ResponseCache,
}


__all__ = [
    "CONTRACTS",
    "PLUGIN_CONTRACT_VERSION",
    "PLUGIN_SCHEMA_VERSION",
    "BenchmarkSuite",
    "CliCommand",
    "ContextStrategy",
    "Evaluator",
    "ExecutionProfile",
    "ExecutionProfileStrategy",
    "HarnessDefinition",
    "HarnessResult",
    "KnowledgeProvider",
    "LLMGateway",
    "MemoryProvider",
    "PersonaDefinition",
    "PhaseDefinition",
    "PluginContributions",
    # manifest / envelope
    "PluginManifest",
    "PluginPermissions",
    "PluginRequires",
    "PolicyContract",
    "ProjectTemplate",
    "ProviderAdapter",
    "RegistryMetadata",
    "ResponseCache",
    "RuntimeIntelligenceAnalyzer",
    "SemanticCache",
    "SkillDefinition",
    "StudioPanel",
    "ToolDefinition",
    "TrustLevel",
    # extension-point contracts
    "WorkflowDefinition",
]
