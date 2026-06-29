"""Performance, cache, model routing, and cost scaffolds."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import StrEnum
from opencontext_core.context.budgeting import estimate_tokens
from opencontext_core.context.prompt_cache import PromptPrefixCachePlanner
from opencontext_core.models.context import PromptSection
from opencontext_core.operating_model.call_budget import _LOCAL_DEFAULT_MODELS
from opencontext_core.providers.capabilities import (
    ProviderCapability,
    capabilities_for,
    providers_with,
)


class RoutingStrategy(StrEnum):
    """Named provider-selection strategy (book §25 "Routing Strategies").

    ``BALANCED`` (the default) reproduces the existing budget-first routing
    byte-for-byte; the other strategies are additive selection biases.
    """

    CHEAPEST = "cheapest"
    FASTEST = "fastest"
    BALANCED = "balanced"
    HIGHEST_QUALITY = "highest_quality"
    LOCAL_FIRST = "local_first"
    ENTERPRISE = "enterprise"


class CachePlan(BaseModel):
    """Cache-aware prompt plan."""

    model_config = ConfigDict(extra="forbid")

    stable_prefix_tokens: int = Field(ge=0, description="Stable prefix tokens.")
    dynamic_tokens: int = Field(ge=0, description="Dynamic section tokens.")
    cache_eligible_tokens: int = Field(ge=0, description="Tokens eligible for caching.")
    cache_breaking_sections: list[str] = Field(description="Dynamic sections.")
    recommended_order: list[str] = Field(description="Prompt section order.")
    estimated_cache_savings_tokens: int = Field(ge=0, description="Estimated reusable tokens.")


class CacheAwarePromptCompiler:
    """Plans stable prompt prefixes without invoking provider cache APIs."""

    def plan(self, sections: list[PromptSection]) -> CachePlan:
        """Return cache planning metrics for prompt sections."""

        ordered = PromptPrefixCachePlanner().order_sections(sections)
        stable = [section for section in ordered if section.stable]
        dynamic = [section for section in ordered if not section.stable]
        stable_tokens = sum(
            section.tokens or estimate_tokens(section.content) for section in stable
        )
        dynamic_tokens = sum(
            section.tokens or estimate_tokens(section.content) for section in dynamic
        )
        return CachePlan(
            stable_prefix_tokens=stable_tokens,
            dynamic_tokens=dynamic_tokens,
            cache_eligible_tokens=stable_tokens,
            cache_breaking_sections=[section.name for section in dynamic],
            recommended_order=[section.name for section in ordered],
            estimated_cache_savings_tokens=stable_tokens,
        )


class ProviderContextCacheAdapter:
    """Provider-neutral explicit-cache scaffold that never calls external APIs."""

    def __init__(self, *, enabled: bool = False) -> None:
        self.enabled = enabled
        self.created: dict[str, CachePlan] = {}

    def create(self, name: str, plan: CachePlan) -> str:
        """Record a cache plan locally if explicit caching is enabled."""

        if not self.enabled:
            return "provider_cache_disabled"
        self.created[name] = plan
        return f"local-cache-plan:{name}"


class ContextLayer(BaseModel):
    """One context layer with cache and budget metadata."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Layer name.")
    source: str = Field(description="Layer source.")
    classification: str = Field(description="Layer data classification.")
    stability: str = Field(description="stable or dynamic.")
    cacheable: bool | str = Field(description="Cache eligibility.")
    token_budget: int = Field(ge=0, description="Layer token budget.")
    trust_level: str = Field(description="Trust label.")
    refresh_policy: str = Field(description="Refresh policy.")


class ContextLayerManager:
    """Builds provider-neutral context-layer metadata."""

    def from_config(self, config: Mapping[str, Any]) -> list[ContextLayer]:
        """Create layers from config mappings."""

        layers: list[ContextLayer] = []
        for name, data in sorted(config.items()):
            if not isinstance(data, Mapping):
                continue
            layers.append(
                ContextLayer(
                    name=name,
                    source=str(data.get("source", name)),
                    classification=str(data.get("classification", "internal")),
                    stability="stable" if data.get("cacheable") is True else "dynamic",
                    cacheable=data.get("cacheable", False),
                    token_budget=int(data.get("budget_tokens", 0)),
                    trust_level=str(data.get("trust_level", "internal")),
                    refresh_policy=str(data.get("refresh_policy", "on_demand")),
                )
            )
        return layers


class CostEntry(BaseModel):
    """Cost/tokens for one run."""

    model_config = ConfigDict(extra="forbid")

    workflow: str = Field(description="Workflow name.")
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    tool_tokens: int = Field(default=0, ge=0)
    memory_tokens: int = Field(default=0, ge=0)
    estimated_cost: float = Field(default=0.0, ge=0.0)
    estimated_latency: float = Field(default=0.0, ge=0.0)
    actual_latency: float | None = Field(default=None, ge=0.0)
    # Provider-call attribution (PR-012 — SPEC-PROV-012-12). All defaulted so the
    # existing run-level CostEntry usages are unaffected.
    provider: str = Field(default="", description="Provider that served the call.")
    model: str = Field(default="", description="Model that served the call.")
    routing_reason: str = Field(default="", description="Why this provider/model was routed.")
    retries: int = Field(default=0, ge=0, description="Fallback/retry count for the call.")


class CostReport(BaseModel):
    """Aggregated cost ledger report."""

    model_config = ConfigDict(extra="forbid")

    runs: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(ge=0)
    estimated_cost: float = Field(ge=0.0)


class CostLedger:
    """In-memory cost ledger used by CLI/report scaffolds."""

    def __init__(self) -> None:
        self.entries: list[CostEntry] = []

    def record(self, entry: CostEntry) -> None:
        """Record one entry."""

        self.entries.append(entry)

    def report(self, *, workflow: str | None = None) -> CostReport:
        """Return aggregate costs."""

        entries = [
            entry for entry in self.entries if workflow is None or entry.workflow == workflow
        ]
        return CostReport(
            runs=len(entries),
            input_tokens=sum(entry.input_tokens for entry in entries),
            output_tokens=sum(entry.output_tokens for entry in entries),
            cached_input_tokens=sum(entry.cached_input_tokens for entry in entries),
            estimated_cost=sum(entry.estimated_cost for entry in entries),
        )


class LatencyBudgetManager:
    """Checks workflow latency budgets."""

    def __init__(self, budgets: Mapping[str, int] | None = None) -> None:
        self.budgets = dict(budgets or {"ask": 20, "plan": 60, "audit": 120})

    def within_budget(self, workflow: str, seconds: float) -> bool:
        """Return whether a workflow latency estimate is acceptable."""

        return seconds <= self.budgets.get(workflow, self.budgets.get("ask", 20))


class ModelRoleRouter:
    """Selects models by role without escalating to expensive providers first."""

    def __init__(
        self,
        roles: Mapping[str, Mapping[str, str]] | None = None,
        budget_manager: Any = None,
        local_providers: list[str] | None = None,
        free_registry: Any = None,
        strategy: RoutingStrategy | str = RoutingStrategy.BALANCED,
        required: frozenset[ProviderCapability] | None = None,
    ) -> None:
        self.roles = dict(roles or {})
        self.budget_manager = budget_manager
        self.local_providers = local_providers or ["ollama", "lmstudio", "localai", "mock"]
        self.free_registry = free_registry
        # Strategy + capability requirement are additive; BALANCED with no
        # required capabilities reproduces the original budget-first routing.
        self.strategy = RoutingStrategy(strategy) if strategy else RoutingStrategy.BALANCED
        self.required: frozenset[ProviderCapability] = required or frozenset()

    def _has_caps(self, provider: str) -> bool:
        """Whether *provider* advertises every required capability."""

        if not self.required:
            return True
        return self.required <= capabilities_for(provider)

    def _budget_ok(self, provider: str, model: str) -> bool:
        if self.budget_manager is None:
            return True
        available, _ = self.budget_manager.check_budget(provider, model)
        return bool(available)

    def _local_candidate(self, model: str) -> dict[str, str] | None:
        """First working, capable, budget-available local provider (if any)."""

        for local in self.local_providers:
            if self.free_registry and hasattr(self.free_registry, "is_working"):
                if not self.free_registry.is_working(local):
                    continue
            if not self._has_caps(local):
                continue
            if self._budget_ok(local, model):
                return {"provider": local, "model": _LOCAL_DEFAULT_MODELS.get(local, model)}
        return None

    def _strategy_route(self, preferred: dict[str, str]) -> dict[str, str] | None:
        """Apply the active strategy / capability filter; ``None`` falls through.

        Returning ``None`` means "use the default budget-first body", which keeps
        BALANCED with no required capabilities byte-identical to the legacy path.
        """

        provider = preferred["provider"]
        model = preferred["model"]
        # local_first / cheapest: prefer an available local backend up front.
        if self.strategy in (RoutingStrategy.LOCAL_FIRST, RoutingStrategy.CHEAPEST):
            local = self._local_candidate(model)
            if local is not None:
                return local
        # highest_quality: never downgrade to local; keep the preferred provider
        # when it satisfies the required capabilities.
        if self.strategy is RoutingStrategy.HIGHEST_QUALITY and self._has_caps(provider):
            return preferred
        # Capability requirement: if the preferred provider can't satisfy it, pick
        # a capable provider (preferring local) that advertises the requirement.
        if self.required and not self._has_caps(provider):
            local = self._local_candidate(model)
            if local is not None:
                return local
            for candidate in providers_with(self.required):
                if self._budget_ok(candidate, model):
                    return {"provider": candidate, "model": model}
        return None

    def route(self, role: str) -> dict[str, str]:
        """Return provider/model for a role."""

        default = {"provider": "mock", "model": "mock-llm"}
        selected = self.roles.get(role, self.roles.get("generate", default))
        return {
            "provider": str(selected.get("provider", "mock")),
            "model": str(selected.get("model", "mock-llm")),
        }

    def route_with_budget(self, role: str, task_complexity: str = "standard") -> dict[str, str]:
        """Route considering call budget and task complexity."""

        preferred = self.route(role)

        # Strategy / capability hooks are additive: BALANCED with no required
        # capabilities falls through to the legacy budget-first body below.
        if self.strategy is not RoutingStrategy.BALANCED or self.required:
            adjusted = self._strategy_route(preferred)
            if adjusted is not None:
                return adjusted

        if self.budget_manager is None:
            return preferred

        provider = preferred["provider"]
        model = preferred["model"]

        # 1. Check if task can be handled by local model regardless of budget
        should_delegate = False
        if self.free_registry and hasattr(self.free_registry, "should_delegate_to_local"):
            should_delegate = self.free_registry.should_delegate_to_local(task_complexity)
        elif task_complexity in ("summarize", "format", "classify", "extract", "translate"):
            should_delegate = True

        if should_delegate:
            for local in self.local_providers:
                # Check if provider is working according to registry
                if self.free_registry and hasattr(self.free_registry, "is_working"):
                    if not self.free_registry.is_working(local):
                        continue

                available, _ = self.budget_manager.check_budget(local, model)
                if available:
                    # Substitute a local-appropriate model: the paid model name
                    # (e.g. gpt-4o) 404s against a local backend like ollama.
                    return {"provider": local, "model": _LOCAL_DEFAULT_MODELS.get(local, model)}

        # 2. Use budget manager to select best provider based on remaining calls
        if hasattr(self.budget_manager, "select_provider"):
            # Filter working local providers
            working_locals = self.local_providers
            if self.free_registry and hasattr(self.free_registry, "is_working"):
                working_locals = [
                    p for p in self.local_providers if self.free_registry.is_working(p)
                ]

            provider, model, _ = self.budget_manager.select_provider(
                provider, model, working_locals
            )
            return {"provider": provider, "model": model}

        # Fallback to simple budget check
        available, _ = self.budget_manager.check_budget(provider, model)
        if not available:
            for local in self.local_providers:
                # Check if provider is working according to registry
                if self.free_registry and hasattr(self.free_registry, "is_working"):
                    if not self.free_registry.is_working(local):
                        continue

                local_available, _ = self.budget_manager.check_budget(local, model)
                if local_available:
                    return {"provider": local, "model": _LOCAL_DEFAULT_MODELS.get(local, model)}

        return {"provider": provider, "model": model}


class ModelEscalationPolicy:
    """Deterministic model escalation policy scaffold."""

    def decide(self, *, sufficient_context: bool, high_value: bool, approval: bool) -> str:
        """Return local, retrieve_more, ask_approval, or strong_model."""

        if sufficient_context:
            return "local_or_default"
        if not high_value:
            return "retrieve_more"
        if not approval:
            return "ask_approval"
        return "strong_model"


class BatchRunPlanner:
    """Plans shared retrieval for related questions."""

    def plan(self, questions: list[str]) -> dict[str, Any]:
        """Return a deterministic batch plan."""

        return {
            "questions": len(questions),
            "shared_repo_map": True,
            "shared_retrieval": len(questions) > 1,
            "separate_outputs": True,
        }


class OfflinePrecomputer:
    """Scaffolds local artifact precomputation."""

    def artifacts(self, root: Path | str) -> list[str]:
        """Return artifacts that can be prepared offline."""

        _ = Path(root)
        return [
            "repo_map",
            "symbol_index",
            "dependency_graph_scaffold",
            "token_heatmap",
            "security_scan",
            "memory_summaries",
            "workflow_static_prefixes",
        ]


class CacheWarmer:
    """Plans stable sections for cache warming without provider calls."""

    def warm(self, workflow: str) -> dict[str, Any]:
        """Return local cache warming plan."""

        return {
            "workflow": workflow,
            "provider_calls": 0,
            "sections": ["system", "tools", "project_manifest", "repo_map", "workflow_contract"],
            "status": "planned",
        }
