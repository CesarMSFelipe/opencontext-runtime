"""Configuration loading for OpenContext Runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from opencontext_core.agentic.config import BudgetMode, FlowMode, MemoryMode
from opencontext_core.compat import StrEnum
from opencontext_core.errors import ConfigurationError
from opencontext_core.models.context import CompressionStrategy, ContextProfile
from opencontext_core.paths import StorageMode

DEFAULT_IGNORE_PATTERNS: tuple[str, ...] = (
    ".git",
    ".opencontext",
    ".storage",
    ".venv",
    "venv",
    # Catch non-standard virtualenv dir names (oc-audit-venv, .ci-venv, ...): a
    # basename glob, applied via fnmatch in is_ignored. Breadth is intentional —
    # any '*venv*' dir is treated as a venv; the canonical pyvenv.cfg marker check
    # in the scanner walk is the robust backstop for arbitrarily-named venvs.
    "*venv*",
    "*.egg-info",
    "__pycache__",
    "*.pyc",
    "vendor",
    "node_modules",
    "var/cache",
    "web/sites/default/files",
    "dist",
    "build",
    "coverage",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "cache",
    "logs",
    "*.log",
    "*.min.js",
    "*.min.css",
    ".claude/worktrees",
    ".claude/plugins/cache",
    # OpenContext-generated and configuration files — excluded from context retrieval
    # so OC's own config never appears as context for user tasks.
    ".mcp.json",
    ".claude/agents/oc-*.md",
    ".claude/agents/.opencontext-delegates/**",
    ".claude/commands/oc-*.md",
    "opencontext.yaml",
    "harness.yaml",
    "openspec/changes/**/receipt.json",
)


class ProjectProfile(BaseModel):
    """Durable, human-authored DOMAIN context for the project.

    Captures what the knowledge graph cannot derive from parsing code — what the
    project is FOR, who it serves, the problem it solves, and the load-bearing
    decisions behind it — so an agent is grounded in the PRODUCT, not just the
    code, on every task. Every field is optional; an unset profile renders to "".
    Distinct from ``project_index.profile``, which is a technology hint.
    """

    model_config = ConfigDict(extra="forbid")

    purpose: str = Field(default="", description="What this project is and what it is for.")
    audience: str = Field(default="", description="Who uses it / who it is for.")
    problem: str = Field(default="", description="The problem it solves / pain points addressed.")
    key_decisions: list[str] = Field(
        default_factory=list,
        description="Load-bearing design/product decisions and the why behind them.",
    )

    def is_empty(self) -> bool:
        """True when nothing was authored (so callers can skip rendering)."""
        return not (self.purpose or self.audience or self.problem or self.key_decisions)

    def to_context_block(self) -> str:
        """Render a compact markdown block for injection into agent context.

        Returns "" when empty so the caller can omit the section entirely.
        """
        if self.is_empty():
            return ""
        lines = ["## Project Profile"]
        if self.purpose:
            lines.append(f"- **Purpose:** {self.purpose}")
        if self.audience:
            lines.append(f"- **Audience:** {self.audience}")
        if self.problem:
            lines.append(f"- **Problem:** {self.problem}")
        if self.key_decisions:
            lines.append("- **Key decisions:**")
            lines.extend(f"  - {decision}" for decision in self.key_decisions)
        return "\n".join(lines)


class ProjectConfig(BaseModel):
    """Project-level runtime configuration."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Human-readable project name.")
    profile: ProjectProfile = Field(
        default_factory=ProjectProfile,
        description=(
            "Optional durable domain context (purpose/audience/problem/key_decisions) "
            "injected into task context. Distinct from project_index.profile (a tech hint)."
        ),
    )


class ModelProviderConfig(BaseModel):
    """Provider-neutral model selection."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(
        default="host",
        description=(
            "Provider key. Defaults to 'host' — the client/agent's own provider via "
            "MCP sampling (claude-code→Anthropic, codex→OpenAI). The client fixes the "
            "provider, so a role usually needs only a model. Set explicitly (anthropic, "
            "openai, ollama, mock, …) only for OpenContext's standalone provider gateways."
        ),
    )
    model: str = Field(description="Provider-specific model identifier.")
    private_endpoint: bool = Field(
        default=False,
        description="Whether this model is routed through a private endpoint.",
    )
    training_opt_in: bool = Field(
        default=False,
        description="Whether provider-side training/data opt-in is enabled for this model route.",
    )
    zero_data_retention: bool = Field(
        default=False,
        description="Whether the provider route is configured for zero data retention.",
    )


class ModelConfigMap(BaseModel):
    """Configured model aliases."""

    model_config = ConfigDict(extra="forbid")

    default: ModelProviderConfig = Field(description="Default model used by workflows.")
    roles: dict[str, ModelProviderConfig] = Field(
        default_factory=dict,
        description="Optional role-specific model routing.",
    )
    phases: dict[str, ModelProviderConfig] = Field(
        default_factory=dict,
        description="Per-phase model overrides. Keys: explore, spec, design, tasks, apply, verify, review, archive, judgment. Falls back to default.",  # noqa: E501
    )


class ContextArtifact(BaseModel):
    """A non-code file (schema, spec, config) to index alongside the codebase."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(description="Path relative to project root.")
    name: str = Field(description="Human-readable label, e.g. 'DB Schema'.")
    type: str = Field(
        default="artifact",
        description="Artifact type hint: 'schema', 'openapi', 'config', 'docs', or 'artifact'.",
    )


class ProjectIndexConfig(BaseModel):
    """Project indexer configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, description="Whether project indexing is enabled.")
    root: str = Field(default=".", description="Project root path.")
    profile: str = Field(
        default="generic",
        description="Technology profile hint; framework-specific logic lives outside core.",
    )
    ignore: list[str] = Field(
        default_factory=lambda: list(DEFAULT_IGNORE_PATTERNS),
        description="Project-relative ignore patterns.",
    )
    context_artifacts: list[ContextArtifact] = Field(
        default_factory=list,
        description="Non-code files (SQL schemas, OpenAPI specs, ADRs) indexed alongside code.",
    )

    @field_validator("ignore", mode="after")
    @classmethod
    def merge_default_ignores(cls, value: list[str]) -> list[str]:
        """Ensure required default ignore patterns are always present."""

        merged = list(dict.fromkeys([*DEFAULT_IGNORE_PATTERNS, *value]))
        return merged


class ContextSectionConfig(BaseModel):
    """Per-section prompt budget configuration."""

    model_config = ConfigDict(extra="forbid")

    system: int = Field(ge=0, description="System section token budget.")
    instructions: int = Field(ge=0, description="Instruction section token budget.")
    tool_schemas: int = Field(default=500, ge=0, description="Tool schema section token budget.")
    project_manifest: int = Field(
        default=1000,
        ge=0,
        description="Project manifest section token budget.",
    )
    repo_map: int = Field(default=3000, ge=0, description="Repository map section token budget.")
    workflow_contract: int = Field(
        default=500,
        ge=0,
        description="Workflow contract section token budget.",
    )
    memory: int = Field(ge=0, description="Memory section token budget.")
    retrieved_context: int = Field(ge=0, description="Retrieved context token budget.")
    conversation: int = Field(ge=0, description="Conversation section token budget.")
    tools: int = Field(ge=0, description="Tools section token budget.")

    def as_dict(self) -> dict[str, int]:
        """Return budgets as a plain dictionary."""

        return self.model_dump()


class RankingWeightsConfig(BaseModel):
    """Ranking formula weights."""

    model_config = ConfigDict(extra="forbid")

    relevance: float = Field(ge=0.0, description="Weight for retrieval relevance.")
    priority: float = Field(ge=0.0, description="Weight for explicit priority.")
    source_trust: float = Field(ge=0.0, description="Weight for source trust.")
    token_efficiency: float = Field(ge=0.0, description="Weight for token efficiency.")


class RankingConfig(BaseModel):
    """Context ranking configuration."""

    model_config = ConfigDict(extra="ignore")

    weights: RankingWeightsConfig = Field(description="Ranking formula weights.")
    # v2 semantic ranking weights — OPTIONAL per-field overrides of RetrievalWeights
    # (retrieval/scoring.py), the single source of truth (RD1). Unset (None) means
    # "defer to the dataclass default", so a config that omits these is byte-identical
    # to default ranking. The historical 0.25-style numbers ship as the documented
    # opt-in preset RANKING_PRESET_V2_SEMANTIC in scoring.py, NOT as a default here.
    # ge=0.0 still validates any value that IS set; Pydantic skips it for None.
    _V2_OVERRIDE = "v2 override; unset -> RetrievalWeights default."
    semantic_relevance: float | None = Field(default=None, ge=0.0, description=_V2_OVERRIDE)
    graph_centrality: float | None = Field(default=None, ge=0.0, description=_V2_OVERRIDE)
    call_distance: float | None = Field(default=None, ge=0.0, description=_V2_OVERRIDE)
    test_affinity: float | None = Field(default=None, ge=0.0, description=_V2_OVERRIDE)
    memory_confidence: float | None = Field(default=None, ge=0.0, description=_V2_OVERRIDE)
    recent_failure: float | None = Field(default=None, ge=0.0, description=_V2_OVERRIDE)
    risk_requirement: float | None = Field(default=None, ge=0.0, description=_V2_OVERRIDE)
    freshness: float | None = Field(default=None, ge=0.0, description=_V2_OVERRIDE)
    provenance: float | None = Field(default=None, ge=0.0, description=_V2_OVERRIDE)


class CacheAlignerConfig(BaseModel):
    """CacheAligner — KV cache prefix stabilization."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=False, description="Align prompt prefixes for KV cache hits.")
    stable_prefix_tokens: int = Field(
        default=1200, ge=100, description="Tokens in the stable prefix (NOT compressed)."
    )
    provider_cache_hints: bool = Field(
        default=True,
        description="Emit provider-specific cache boundary markers.",
    )
    max_cache_age_turns: int = Field(
        default=10, ge=1, description="Max turns before forcing a full re-send."
    )


class SmartCrusherConfig(BaseModel):
    """SmartCrusher — JSON structural compression."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, description="Compress JSON arrays to tabular form.")
    min_array_length: int = Field(
        default=3, ge=2, description="Minimum array length to trigger smart crushing."
    )
    max_inline_schema_keys: int = Field(
        default=20, ge=1, description="Max schema keys before falling back to prose compress."
    )
    tabular_format: str = Field(
        default="compact_table",
        description="Output format: 'compact_table' or 'aligned_columns'.",
    )


class CodeCompressorConfig(BaseModel):
    """CodeCompressor — AST-aware code compression."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, description="Compress source code using AST.")
    strip_docstrings: bool = Field(default=True, description="Replace docstrings with signatures.")
    strip_comments: bool = Field(default=True, description="Strip comments in non-PLAN mode.")
    shorten_locals: bool = Field(default=True, description="Shorten local identifiers.")
    preserve_exports: bool = Field(default=True, description="Never shorten exported symbols.")


class CCRCacheConfig(BaseModel):
    """CCR — reversible compression cache."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=False, description="Cache originals for reversible compression.")
    ttl_seconds: int = Field(default=300, ge=30, description="Time-to-live for cached originals.")
    max_entries: int = Field(default=500, ge=10, description="Max entries in the CCR cache.")
    storage_path: str | None = Field(default=None, description="Override for cache file path.")


class OutputReducerConfig(BaseModel):
    """OutputReducer — reduce what the model writes back."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=False, description="Steer LLM output to be terse.")
    verbosity_instruction: str = Field(
        default=(
            "Be concise. Omit recaps of code already in context. "
            "Avoid preambles like 'Sure, let me'. Answer directly."
        ),
        description="Instruction appended to system prompt.",
    )
    effort_routing: bool = Field(
        default=True,
        description="Dial thinking effort down on tool-result turns.",
    )
    holdout_fraction: float = Field(
        default=0.1, ge=0.0, le=1.0, description="Fraction of turns left unshaped as control group."
    )


class CompressionConfig(BaseModel):
    """Safe compression configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, description="Whether compression is enabled.")
    strategy: CompressionStrategy = Field(
        default=CompressionStrategy.EXTRACTIVE_HEAD_TAIL,
        description="Configured compression strategy.",
    )
    terse_intensity: str = Field(
        default="full",
        validation_alias=AliasChoices("terse_intensity", "cave" + "man_intensity"),
        description="Terse compression intensity: 'lite', 'full', or 'ultra'.",
    )
    max_compression_ratio: float = Field(
        default=0.5,
        gt=0.0,
        le=1.0,
        description="Maximum compressed/original token ratio for lossy strategies.",
    )
    adaptive: bool = Field(default=True, description="Whether adaptive compression is enabled.")
    protected_spans: bool = Field(
        default=True,
        description="Whether protected spans prevent unsafe lossy compression.",
    )
    cache_aligner: CacheAlignerConfig = Field(
        default_factory=CacheAlignerConfig,
        description="KV cache prefix alignment.",
    )
    smart_crusher: SmartCrusherConfig = Field(
        default_factory=SmartCrusherConfig,
        description="JSON structural compression.",
    )
    code_compressor: CodeCompressorConfig = Field(
        default_factory=CodeCompressorConfig,
        description="AST-aware code compression.",
    )
    ccr_cache: CCRCacheConfig = Field(
        default_factory=CCRCacheConfig,
        description="Reversible compression cache.",
    )
    output_reducer: OutputReducerConfig = Field(
        default_factory=OutputReducerConfig,
        description="Output token reduction.",
    )


class CrossProjectConfig(BaseModel):
    """Cross-project graph tunnel configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=False, description="Cross-project retrieval disabled in v0.1.")
    max_hops: int = Field(default=1, ge=1, le=3, description="Maximum project-hop depth.")
    max_tokens_per_project: int = Field(
        default=1000, ge=100, description="Token budget per linked project."
    )
    auto_discover: bool = Field(
        default=True, description="Auto-discover tunnels from dependency paths."
    )


class RetrievalConfig(BaseModel):
    """Retrieval configuration."""

    model_config = ConfigDict(extra="forbid")

    strategy: str = Field(default="hybrid", description="Retrieval strategy name.")
    top_k: int = Field(default=20, gt=0, description="Number of candidates to retrieve.")
    rerank_top_k: int = Field(default=8, gt=0, description="Candidates kept after reranking.")
    cross_project: CrossProjectConfig = Field(default_factory=CrossProjectConfig)


class RepoMapConfig(BaseModel):
    """Repository map configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, description="Whether repo maps are generated.")
    max_tokens: int = Field(default=3000, gt=0, description="Repo map render budget.")
    include_symbols: bool = Field(default=True, description="Whether to include symbols.")
    include_dependencies: bool = Field(
        default=True,
        description="Reserved flag for future dependency graph summaries.",
    )


class ContextPackingConfig(BaseModel):
    """Token-aware context packing configuration."""

    model_config = ConfigDict(extra="forbid")

    strategy: str = Field(
        default="priority_value_density",
        description="Context packing strategy.",
    )
    preserve_priorities: list[str] = Field(
        default_factory=lambda: ["P0", "P1"],
        description="Priority names considered required by the packer.",
    )


class ContextConfig(BaseModel):
    """Token budget, ranking, and compression configuration."""

    model_config = ConfigDict(extra="forbid")

    max_input_tokens: int = Field(gt=0, description="Maximum model input tokens.")
    reserve_output_tokens: int = Field(ge=0, description="Tokens reserved for output.")
    sections: ContextSectionConfig = Field(description="Per-section budgets.")
    ranking: RankingConfig = Field(description="Ranking settings.")
    compression: CompressionConfig = Field(description="Compression settings.")
    budget_mode: BudgetMode = Field(
        default=BudgetMode.WARN,
        description="Token budget enforcement strategy (off/warn/strict/adaptive/ask).",
    )
    # --- PR-010 Context Engine v2 (OC-CONTEXT-001 §Configuration) ----------------
    # All defaulted so an unset config resolves to today's behaviour byte-for-byte;
    # the engine is additionally gated behind ``runtime.context_engine_enabled``.
    profile: ContextProfile = Field(
        default=ContextProfile.BALANCED,
        description="Context profile tuning retrieval/compression/limits (balanced=today).",
    )
    budgets: dict[str, int] = Field(
        default_factory=dict,
        description="Optional per-workflow context budget overrides (book §Context Budget).",
    )
    semantic_gc: bool = Field(
        default=False,
        description="Enable incremental context garbage collection (book §Garbage Collection).",
    )
    receipts: bool = Field(
        default=False,
        description="Emit the four typed retrieval receipts out-of-band.",
    )
    kg_first: bool = Field(
        default=True, description="Consult the knowledge graph before repository traversal."
    )
    symbol_first: bool = Field(
        default=True, description="Prefer symbols over whole files during retrieval."
    )
    full_file_threshold: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Relevance threshold below which a whole file is not loaded.",
    )


class CompressionPolicyConfig(BaseModel):
    """Top-level compression policy defaults."""

    model_config = ConfigDict(extra="forbid")

    adaptive: bool = Field(default=True, description="Whether adaptive compression is enabled.")
    protected_spans: bool = Field(default=True, description="Whether spans are protected.")
    default_strategy: CompressionStrategy = Field(
        default=CompressionStrategy.EXTRACTIVE_HEAD_TAIL,
        description="Default compression strategy.",
    )


class ExactCacheConfig(BaseModel):
    """Exact prompt cache configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, description="Whether exact prompt cache is enabled.")
    storage: str = Field(default="local", description="Exact cache storage backend key.")


class SemanticCacheConfig(BaseModel):
    """Semantic cache interface configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=False, description="Semantic cache is disabled by default.")
    similarity_threshold: float = Field(default=0.92, ge=0.0, le=1.0)
    require_same_workflow: bool = Field(default=True)
    require_same_project_hash: bool = Field(default=True)


class MCPCacheConfig(BaseModel):
    """MCP-specific cache and compression configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=False, description="MCP cache/compression disabled in v0.1.")
    compression_enabled: bool = Field(
        default=True, description="Enable terse compression for MCP responses."
    )
    compression_ratio: float = Field(
        default=0.5,
        gt=0.0,
        le=1.0,
        description="Target compression ratio for MCP responses.",
    )
    preserve_code_blocks: bool = Field(
        default=True,
        description="Always preserve code blocks in MCP compression.",
    )
    cache_ttl_seconds: int = Field(default=3600, ge=0, description="MCP response cache TTL.")


class RuntimeCacheConfig(BaseModel):
    """Unified typed cache layer + Runtime Optimizer controls (PR-000.3).

    Default-conservative: with ``enabled=False`` the typed caches
    (tool/ast/provider/kg/memory) stay pass-through (every lookup recomputes) and
    the optimizer emits no recommendations. The whole PR-000.3 layer is reverted
    by leaving this off.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        default=False,
        description="Enable the unified typed cache layer (off = pass-through recompute).",
    )
    backend: Literal["memory", "sqlite"] = Field(
        default="memory", description="Default CacheStore backend (reuses ccr_cache backends)."
    )
    default_ttl_seconds: int = Field(
        default=3600, ge=0, description="Default TTL for typed cache entries."
    )
    semantic_threshold: float = Field(
        default=0.95, ge=0.0, le=1.0, description="Semantic-cache similarity threshold."
    )
    optimizer_enabled: bool = Field(
        default=False, description="Enable the recommend-only Runtime Optimizer."
    )


class CacheConfig(BaseModel):
    """Runtime cache configuration."""

    model_config = ConfigDict(extra="forbid")

    exact: ExactCacheConfig = Field(default_factory=ExactCacheConfig)
    semantic: SemanticCacheConfig = Field(default_factory=SemanticCacheConfig)
    mcp: MCPCacheConfig = Field(default_factory=MCPCacheConfig)
    runtime: RuntimeCacheConfig = Field(default_factory=RuntimeCacheConfig)


class SecretScanningConfig(BaseModel):
    """Secret scanning configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, description="Whether secret scanning is enabled.")
    redact: bool = Field(default=True, description="Whether secret values are redacted.")


class PromptInjectionDetectionConfig(BaseModel):
    """Prompt injection detection configuration placeholder."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        default=True, description="Whether prompt injection detection is enabled."
    )


class SafetyConfig(BaseModel):
    """Safety layer configuration."""

    model_config = ConfigDict(extra="forbid")

    secret_scanning: SecretScanningConfig = Field(default_factory=SecretScanningConfig)
    prompt_injection_detection: PromptInjectionDetectionConfig = Field(
        default_factory=PromptInjectionDetectionConfig
    )


class SecurityMode(StrEnum):
    """Runtime security posture."""

    DEVELOPER = "developer"
    PRIVATE_PROJECT = "private_project"
    ENTERPRISE = "enterprise"
    AIR_GAPPED = "air_gapped"


class SecurityConfig(BaseModel):
    """Security governance defaults."""

    model_config = ConfigDict(extra="forbid")

    mode: SecurityMode = Field(default=SecurityMode.PRIVATE_PROJECT)
    fail_closed: bool = Field(default=True)
    default_classification: str = Field(default="internal")
    external_providers_enabled: bool = Field(default=False)


class PolicyConfig(BaseModel):
    """Unified Policy Engine settings (PR-005).

    ``preset`` selects one of the four postures (``permissive``/``balanced``/
    ``restricted``/``air_gapped``); ``balanced`` is the default and preserves the
    current fail-closed behaviour. ``command_enforcement`` wires the (previously
    inert) ``forbidden_commands`` deny-list into real enforcement; set it ``False``
    to revert to the legacy advisory-only behaviour.
    """

    model_config = ConfigDict(extra="forbid")

    preset: str = Field(default="balanced", description="Active policy preset.")
    engine_enabled: bool = Field(
        default=True, description="Route governed operations through the unified PolicyEngine."
    )
    command_enforcement: bool = Field(
        default=True, description="Enforce forbidden_commands on the command path (CMD-1)."
    )


class ProvidersConfig(BaseModel):
    """Provider availability defaults."""

    model_config = ConfigDict(extra="forbid")

    external_enabled: bool = Field(
        default=False,
        description="External providers disabled by default.",
    )
    # PR-012 Provider Gateway knobs (book §25). All defaulted so existing configs
    # validate unchanged; ``strategy=balanced`` reproduces today's routing.
    strategy: str = Field(
        default="balanced",
        description=(
            "Provider routing strategy: cheapest / fastest / balanced / "
            "highest_quality / local_first / enterprise."
        ),
    )
    retry_limit: int = Field(
        default=2, ge=0, description="Bounded provider fallback retries on error/timeout/quota."
    )
    fallback: bool = Field(
        default=True,
        description="Fall back to an alternate provider on error/timeout/quota/unsupported.",
    )
    streaming: bool = Field(
        default=False, description="Streaming transport (delivered by a later provider PR)."
    )


class ProviderPolicyConfig(BaseModel):
    """Policy for one provider."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    allowed: bool = False
    allowed_classifications: set[str] = Field(default_factory=set)
    require_redaction: bool = True
    require_zero_data_retention: bool = False
    require_private_endpoint: bool = False
    allow_training_opt_in: bool = False
    notes: str | None = None


class LocalTraceConfig(BaseModel):
    """Local trace exporter configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, description="Whether local JSON traces are persisted.")


class OpenTelemetryConfig(BaseModel):
    """OpenTelemetry exporter configuration placeholder."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=False, description="No OTel dependency is used in v0.1.")


class ObservabilityConfig(BaseModel):
    """Observability configuration."""

    model_config = ConfigDict(extra="forbid")

    local_traces: LocalTraceConfig = Field(default_factory=LocalTraceConfig)
    opentelemetry: OpenTelemetryConfig = Field(default_factory=OpenTelemetryConfig)


class TraceStorageConfig(BaseModel):
    """Trace storage safety defaults."""

    model_config = ConfigDict(extra="forbid")

    store_raw_context: bool = Field(default=False, description="Raw trace context disabled.")
    store_redacted_context: bool = Field(
        default=True,
        description="Store redacted context decisions.",
    )


class NativeToolsConfig(BaseModel):
    """Native tool registry configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        default=False,
        description="Whether native tools can be registered. Disabled by default.",
    )


class McpToolsConfig(BaseModel):
    """Future MCP adapter boundary configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=False, description="MCP adapter is disabled in v0.1.")
    require_allowlist: bool = Field(default=True)
    allow_stdio: bool = Field(default=False)
    sandbox: bool = Field(default=True)
    require_write_approval: bool = Field(
        default=False,
        description=(
            "When True, the symbol-edit write tools (replace/insert/rename) must "
            "pass the human-approval gate before touching disk. Default False "
            "preserves current MCP-edit behavior exactly."
        ),
    )


class ToolsConfig(BaseModel):
    """Tool runtime configuration."""

    model_config = ConfigDict(extra="forbid")

    native: NativeToolsConfig = Field(default_factory=NativeToolsConfig)
    mcp: McpToolsConfig = Field(default_factory=McpToolsConfig)


class LoopConfig(BaseModel):
    """Post-run Learning Loop gate (PR-000.4, SPEC DL-006).

    Default OFF and fully revertible: with ``enabled=False`` the harness runs the
    legacy propose-only evolution hook unchanged and writes no Decision Log
    artifact. The loop is always best-effort/non-blocking.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        default=False,
        description="Run the post-run LearningLoop (Decision Log + learning candidates).",
    )
    feed_runtime_intelligence: bool = Field(
        default=True,
        description="Feed learning outcomes to Runtime Intelligence via the feedback substrate.",
    )
    require_benchmark_evidence: bool = Field(
        default=True,
        description="Block promotion of any improvement proposal lacking a benchmark-evidence ref.",
    )


class LearningConfig(BaseModel):
    """Self-improvement (learning orchestrator) gate.

    ``enabled`` defaults to ``True`` so the runtime behaves exactly as it does
    today. Setting it ``False`` prevents the ``LearningOrchestrator`` from being
    constructed/active on the runtime; a no-op stand-in is used instead so the
    runtime still starts cleanly and the in-loop ``learning.*`` call-sites never
    raise.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        default=True,
        description="Whether the self-improvement learning orchestrator is active.",
    )
    loop: LoopConfig = Field(
        default_factory=LoopConfig,
        description="Post-run Learning Loop settings (PR-000.4; default off).",
    )


class MemoryPolicyConfig(BaseModel):
    """Memory defaults for progressive disclosure and harvesting."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, description="Local memory layer enabled.")
    mode: MemoryMode = Field(
        default=MemoryMode.AUTO,
        description="Memory backend mode (auto/engram/local/off/hybrid/engram_only).",
    )
    provider: str = Field(
        default="local",
        description=(
            "Memory backend provider. 'local' (default): OpenContext's own SQLite "
            "memory — its full capability (cognitive layers, decay, reinforce, "
            "supersede, hybrid recall). 'engram': couple to a co-resident Engram "
            "(EPISODIC/SEMANTIC -> Engram, the rest local). 'auto': couple to Engram "
            "if present, else local. Engram coupling is an explicit opt-in (offered "
            "by the setup wizard when an install is detected), not a silent default."
        ),
    )
    harvest_after_run: bool = Field(
        default=True, description="Harvest memory automatically after each run."
    )
    require_approval: bool = Field(default=True, description="Harvested memories require approval.")
    store_raw: bool = Field(default=False, description="Raw memory storage disabled.")
    default_classification: str = Field(default="internal", description="Default memory class.")
    retention_days: int = Field(default=90, ge=1, description="Default retention window.")
    prune_low_reuse: bool = Field(default=True)
    prune_superseded: bool = Field(default=True)
    prune_expired: bool = Field(default=True)


class EmbeddingConfig(BaseModel):
    """Async embedding generation and vector storage configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=False, description="Async embedding generation enabled.")
    provider: str = Field(
        default="local", description="Embedding provider: local, openai, cohere, etc."
    )
    model: str = Field(default="text-embedding-3-small", description="Embedding model identifier.")
    dimensions: int = Field(default=1536, ge=1, description="Embedding vector dimensions.")
    batch_size: int = Field(
        default=100, ge=1, le=1000, description="Batch size for embedding generation."
    )
    async_worker: bool = Field(
        default=True, description="Use background worker for embedding writes."
    )
    write_path_sync_timeout_ms: int = Field(
        default=150,
        ge=10,
        le=1000,
        description="Synchronous write path must complete within this timeout (milliseconds).",
    )
    storage_backend: str = Field(default="null", description="Vector storage backend.")
    queue_max_size: int = Field(default=10000, ge=100, description="Maximum embedding queue size.")
    worker_concurrency: int = Field(
        default=4, ge=1, le=32, description="Number of concurrent embedding workers."
    )


class OutputPolicyConfig(BaseModel):
    """Output token budget defaults."""

    model_config = ConfigDict(extra="forbid")

    mode: str = Field(default="concise", description="Default output mode.")
    max_output_tokens: int = Field(default=1500, ge=0, description="Default output token cap.")
    preserve: list[str] = Field(
        default_factory=lambda: ["code", "commands", "paths", "symbols", "warnings", "numbers"],
        description="Important content classes preserved by terse modes.",
    )


class EgressConfig(BaseModel):
    """Default egress policy for outputs, tools, network, and exports."""

    model_config = ConfigDict(extra="forbid")

    network: str = Field(default="deny", description="Network egress policy.")
    external_urls: str = Field(default="ask", description="External URL output policy.")
    webhooks: str = Field(default="deny", description="Webhook egress policy.")
    clipboard: str = Field(default="allow_redacted", description="Clipboard export policy.")
    file_export: str = Field(default="allow_redacted", description="File export policy.")
    tool_output_forwarding: str = Field(
        default="deny",
        description="Whether tool output can be forwarded to external sinks.",
    )


class ProviderCacheConfig(BaseModel):
    """Provider-neutral context-cache policy scaffold."""

    model_config = ConfigDict(extra="forbid")

    strategy: str = Field(default="auto", description="Provider-cache planning strategy.")
    explicit_cache_enabled: bool = Field(
        default=False,
        description="Whether provider explicit cache APIs may be used.",
    )
    ttl_seconds: int = Field(default=3600, ge=0, description="Requested provider cache TTL.")
    cacheable_sections: list[str] = Field(
        default_factory=lambda: [
            "tool_schemas",
            "system",
            "project_manifest",
            "repo_map",
            "workflow_contract",
        ],
        description="Prompt sections considered stable/cacheable.",
    )


class ContextLayerConfig(BaseModel):
    """Policy for one context layer."""

    model_config = ConfigDict(extra="forbid")

    cacheable: bool | str = Field(default=False, description="Cache eligibility.")
    budget_tokens: int = Field(default=1000, ge=0, description="Layer token budget.")
    trust_level: str = Field(default="internal", description="Layer trust boundary.")
    refresh_policy: str = Field(default="on_demand", description="Layer refresh policy.")


class WorkflowTokenBudgetConfig(BaseModel):
    """Input/output token budget for one workflow class."""

    model_config = ConfigDict(extra="forbid")

    input: int = Field(gt=0, description="Input token budget.")
    output: int = Field(ge=0, description="Output token budget.")


class LatencyConfig(BaseModel):
    """Latency budgets by workflow."""

    model_config = ConfigDict(extra="forbid")

    max_seconds: dict[str, int] = Field(
        default_factory=lambda: {"ask": 20, "plan": 60, "audit": 120},
        description="Maximum latency budget by workflow name.",
    )


class ServerConfig(BaseModel):
    """Thin API server defaults."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=False, description="Whether the API server is enabled.")
    host: str = Field(default="127.0.0.1", description="Default API bind host.")
    port: int = Field(default=8000, ge=1, le=65535, description="Default API port.")


class WorkflowStepDef(BaseModel):
    """A single workflow step — either a simple step name or a structured step."""

    model_config = ConfigDict(extra="forbid")

    step: str | None = Field(
        default=None,
        description="Simple step name (for basic steps).",
    )
    type: str | None = Field(
        default=None,
        description="Step type: parallel, if, switch, while, fan-out, fan-in.",
    )
    steps: list[str] | None = Field(
        default=None,
        description="Child steps (for parallel, if/else, sequential containers).",
    )
    condition: str | None = Field(
        default=None,
        description="Expression or reference for conditional steps.",
    )
    then: list[str] | None = Field(
        default=None,
        description="Steps to run when condition is true (for if/switch).",
    )
    else_: list[str] | None = Field(
        default=None,
        description="Steps to run when condition is false (for if/switch).",
        alias="else",
    )
    fan_step: str | None = Field(
        default=None,
        description="Step to fan out (for fan-out).",
    )
    inputs: list[str] | None = Field(
        default=None,
        description="Inputs to pass to each fan-out iteration.",
    )
    join_strategy: str | None = Field(
        default=None,
        description="How to merge fan-in results (concatenate, merge, pick_first).",
    )
    output_key: str | None = Field(
        default=None,
        description="Metadata key to store fan-in results.",
    )


class WorkflowConfig(BaseModel):
    """Named workflow definition loaded from YAML."""

    model_config = ConfigDict(extra="forbid")

    steps: list[str | dict[str, Any]] = Field(
        description="Ordered workflow steps (strings or structured step dicts)."
    )


class RetentionConfig(BaseModel):
    """Durable-evidence retention policy (PR-002, doc 24 §20).

    Each value is a retention rule: ``always`` (never auto-pruned),
    ``until_archive``, ``until_success``, or a duration like ``30d``. Auto-pruning
    beyond this documented table is out of scope for PR-002 (no sweeper ships yet).
    """

    model_config = ConfigDict(extra="forbid")

    summaries: str = Field(default="always")
    receipts: str = Field(default="always")
    patches: str = Field(default="always")
    checkpoints: str = Field(default="until_archive")
    logs: str = Field(default="30d")
    ephemeral_context: str = Field(default="until_success")


class RuntimeMigrationConfig(BaseModel):
    """Per-subsystem dual-run migration flags (pr-000-0 compatibility layer).

    Each ``*_enabled`` flag defaults to the legacy path, so a subsystem is switched
    to the vNext substrate by flipping exactly one flag (CL-005). ``registry_enabled``
    is the PR-003 rollback switch: when ``False`` the Runtime resolves workflows via
    the legacy ``_WORKFLOW_TRACK_ALIASES``/``WORKFLOW_TRACKS`` path unchanged.
    """

    model_config = ConfigDict(extra="forbid")

    session_wrapper: bool = Field(
        default=True, description="Bracket legacy runs with a RuntimeApi session."
    )
    registry_enabled: bool = Field(
        default=True,
        description=(
            "Resolve workflows through the PR-003 WorkflowRegistry. Flipped to vNext "
            "(VDM-003/004): the legacy-track parity gap is closed (no spurious "
            "workflow.validation.failed); the registry emits resolution AUDIT events on "
            "success (EVT1) while the EXECUTED-PHASE ledger stays identical to legacy."
        ),
    )
    persona_registry_enabled: bool = Field(
        default=True,
        description="Resolve personas through the PR-006 PersonaRegistry/Resolver.",
    )
    skill_registry_enabled: bool = Field(
        default=True,
        description="Resolve skills through the PR-006 SkillRegistryV2 (bundles/tiers).",
    )
    harness_registry_enabled: bool = Field(
        default=True,
        description="Resolve harnesses through the PR-006 HarnessRegistry.",
    )
    gateway_enabled: bool = Field(
        default=True, description="Route provider calls through the unified gateway."
    )
    context_engine_enabled: bool = Field(
        default=True, description="Build context through the PR-010 ContextEngine."
    )
    execution_profile: str = Field(
        default="balanced",
        description=(
            "Built-in execution profile (PR-000.2) that binds token budget / "
            "retries / harness strictness / provider routing: one of 'balanced', "
            "'low-cost', 'enterprise', 'research', 'performance'. An empty string "
            "disables profile influence and restores legacy behaviour (the "
            "capability graph is still reported read-only by 'doctor')."
        ),
    )
    durable_artifacts: bool = Field(
        default=True,
        description=(
            "Persist the PR-002 durable evidence layer "
            "(.opencontext/sessions/<id>/runs/<id>/{artifacts,receipts,checkpoints,patches}"
            " + manifest). Off (default) reproduces the PR-001 flat .opencontext/runs dump."
        ),
    )
    retention: RetentionConfig = Field(
        default_factory=RetentionConfig,
        description="Durable-evidence retention policy (doc 24 §20).",
    )
    sdd_strict: bool = Field(
        default=False,
        description=(
            "Block an SDD phase whose output is a detected scaffold/placeholder "
            "(report FAILED and stop the run) instead of merely WARNing. Off "
            "(default) preserves the legacy advisory scaffold reporting "
            "(spec PR-004 SDD-CONV: scaffold blocking in strict mode)."
        ),
    )
    oc_flow_enabled: bool = Field(
        default=True,
        description=(
            "Enable the PR-007 OC Flow operational workflow "
            '(`opencontext run "<task>" --workflow oc-flow`). Off (default-legacy) '
            "until the localized-bugfix benchmark passes; flip one flag to enable."
        ),
    )
    kg_v2_enabled: bool = Field(
        default=True,
        description=(
            "Enable the PR-008 Knowledge Graph v2 retrieval path (task-aware "
            "KgQueryPlanner -> budgeted ContextSubgraph consulted before broad file "
            "reads). Off (default-legacy) restores the RetrievalPlanner path verbatim; "
            "flip one flag to enable."
        ),
    )
    memory_v2_enabled: bool = Field(
        default=True,
        description=(
            "Enable the PR-009 Memory v2 governance path: route all durable memory "
            "promotion through the single MemoryHarness (8-step write lifecycle, "
            "evidence/no-CoT promotion policy, MemoryReceipt + named memory events). "
            "Off (default-legacy) keeps the 18-verb memory subsystem and the direct "
            "harvester writes verbatim; flip one flag to enable."
        ),
    )


class ArtifactStoreMode(StrEnum):
    """Artifact store backend mode."""

    ENGRAM = "engram"
    OPEN_SPEC = "openspec"
    HYBRID = "hybrid"
    NONE = "none"


class EngramStoreConfig(BaseModel):
    """Engram artifact store configuration."""

    model_config = ConfigDict(extra="forbid")

    project: str | None = Field(default=None, description="Engram project override.")


class OpenSpecStoreConfig(BaseModel):
    """OpenSpec file-based artifact store configuration."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(default="openspec/", description="OpenSpec root path.")


class ArtifactStoreConfig(BaseModel):
    """Artifact store configuration."""

    model_config = ConfigDict(extra="forbid")

    mode: ArtifactStoreMode = Field(
        default=ArtifactStoreMode.NONE, description="Artifact store backend."
    )
    engram: EngramStoreConfig = Field(default_factory=EngramStoreConfig)
    openspec: OpenSpecStoreConfig = Field(default_factory=OpenSpecStoreConfig)


class DeliveryStrategy(StrEnum):
    """Delivery and review strategy."""

    ASK_ON_RISK = "ask-on-risk"
    AUTO_CHAIN = "auto-chain"
    SINGLE_PR = "single-pr"
    EXCEPTION_OK = "exception-ok"
    PLAN_ONLY = "plan-only"


class ChainStrategy(StrEnum):
    """Chained PR merge strategy."""

    STACKED_TO_MAIN = "stacked-to-main"
    FEATURE_BRANCH_CHAIN = "feature-branch-chain"


class SDDConfig(BaseModel):
    """SDD orchestrator configuration."""

    model_config = ConfigDict(extra="forbid")

    artifact_store: ArtifactStoreConfig = Field(default_factory=ArtifactStoreConfig)
    delivery_strategy: DeliveryStrategy = Field(default=DeliveryStrategy.PLAN_ONLY)
    chain_strategy: ChainStrategy = Field(default=ChainStrategy.STACKED_TO_MAIN)
    flow_mode: FlowMode = Field(
        default=FlowMode.HYBRID,
        description="Pause and execution policy for the agentic flow.",
    )
    track: str = Field(
        default="full",
        description=(
            "SDD workflow track: quick (3 phases), standard (5 phases), or full (8 phases)."
        ),
    )

    @field_validator("track")
    @classmethod
    def _validate_track(cls, value: str) -> str:
        valid = {"quick", "standard", "full"}
        if value not in valid:
            raise ValueError(f"Invalid track '{value}'. Must be one of: {', '.join(sorted(valid))}")
        return value

    model_assignments: dict[str, str] = Field(
        default_factory=lambda: {
            "explore": "default",
            "propose": "default",
            "spec": "default",
            "design": "default",
            "tasks": "default",
            "apply": "default",
            "verify": "default",
            "archive": "default",
        },
        description="Per-phase model assignment map.",
    )
    persona_models: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Per-persona model overrides (persona id -> model), e.g. "
            "{'oc-orchestrator': 'opus', 'oc-explorer': 'sonnet'}. A persona override "
            "wins over the phase's profile model. Set via `opencontext persona set-model`."
        ),
    )
    interactive: bool = Field(default=False, description="Pause after each phase for review.")


class KnowledgeGraphConfig(BaseModel):
    """Code knowledge graph configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, description="Whether knowledge graph indexing is enabled.")
    languages: list[str] = Field(
        default_factory=list, description="Languages to index; empty = auto-detect."
    )
    exclude: list[str] = Field(
        default_factory=lambda: [
            "node_modules/**",
            "vendor/**",
            "__pycache__/**",
            ".git/**",
            "*.min.js",
            "*.min.css",
        ],
        description="Glob patterns to exclude from indexing.",
    )
    max_file_size: int = Field(
        default=1_048_576, ge=1024, description="Skip files larger than this in bytes."
    )
    track_call_sites: bool = Field(default=True, description="Track call site locations.")
    auto_sync: bool = Field(default=True, description="Auto-sync on file changes.")
    track_class_hierarchy: bool = Field(default=True, description="Track extends/implements edges.")


class MutationConfig(BaseModel):
    """Mutation analysis configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=False, description="Whether mutation analysis is enabled.")
    threshold: int = Field(default=80, ge=0, le=100, description="Minimum mutation score (0-100).")
    fail_on_low_score: bool = Field(
        default=False, description="Fail phase when score is below threshold."
    )


class TestingConfig(BaseModel):
    """Testing configuration including mutation analysis."""

    model_config = ConfigDict(extra="forbid")

    mutation: MutationConfig = Field(default_factory=MutationConfig)


class ContextPlanningConfig(BaseModel):
    """Context planning configuration for v2 contract-driven retrieval."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, description="Whether context planning is enabled.")
    default_mode: str = Field(default="progressive", description="Default planning mode.")
    contract_required: bool = Field(
        default=True, description="Whether a context contract is required."
    )
    risk_classifier: str = Field(default="deterministic", description="Risk classifier to use.")
    max_expansion_rounds: int = Field(default=3, ge=1, description="Maximum expansion rounds.")
    fail_on_unverified_critical_assumptions: bool = Field(
        default=False,
        description="Fail when critical assumptions cannot be verified.",
    )


class ContextStorageConfig(BaseModel):
    """Context vector storage configuration."""

    model_config = ConfigDict(extra="forbid")

    semantic_search: bool = Field(default=False, description="Whether semantic search is enabled.")
    host: str = Field(default="localhost", description="Vector storage host.")
    port: int = Field(default=6333, ge=1, le=65535, description="Vector storage port.")


class VerifyConfig(BaseModel):
    """Verify-phase options.

    Read by the harness verify phase (``harness/phases.py``) via attribute access
    (``verify.compliance_matrix``); it must be a typed sub-model, not an open
    mapping, and must exist here or the top-level ``extra='forbid'`` rejects a
    ``verify:`` block in opencontext.yaml — which previously made the flag
    unsettable and the ComplianceMatrix feature unreachable.
    """

    model_config = ConfigDict(extra="forbid")

    compliance_matrix: bool = Field(
        default=False, description="Enable the verify-phase ComplianceMatrix artifact."
    )


class SkillsConfig(BaseModel):
    """Skill registry configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=False, description="Whether skill registry is enabled.")
    registry_path: str = Field(
        default=".atl/skill-registry.md", description="Skill registry file path."
    )
    auto_discover: bool = Field(
        default=True, description="Auto-discover skills from configured directories."
    )
    user_dirs: list[str] = Field(
        default_factory=lambda: [
            "~/.config/opencode/skills/",
            "~/.claude/skills/",
        ],
        description="User-level skill directories.",
    )
    project_dirs: list[str] = Field(
        default_factory=lambda: [
            ".claude/skills/",
            "skills/",
        ],
        description="Project-level skill directories.",
    )


class AutoImproveConfig(BaseModel):
    """Opt-in, bounded auto-improvement (self-tuning) controls.

    Disabled by default. Nothing changes runtime behavior without either an
    approved proposal (``apply_policy="propose"``) or an explicit ``auto`` policy
    the developer set, and even then no more than ``max_auto_apply_per_cycle``
    proposals are applied per cycle.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        default=False,
        description="Master switch. When False, no proposal is auto-applied.",
    )
    apply_policy: Literal["propose", "auto"] = Field(
        default="propose",
        description="'propose' requires developer approval; 'auto' applies within bounds.",
    )
    max_auto_apply_per_cycle: int = Field(
        default=3,
        ge=1,
        description="Maximum proposals auto-applied in a single cycle.",
    )
    max_weight_delta: float = Field(
        default=0.1,
        ge=0.0,
        description="Cap on per-field retrieval-weight change a proposal may apply.",
    )
    min_confidence: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Minimum proposal confidence eligible for auto-apply.",
    )
    applied_budgets: dict[str, int] = Field(
        default_factory=dict,
        description="Applied per-operation token budgets (written by approved proposals).",
    )


class HarnessSettingsConfig(BaseModel):
    """Agentic harness governance settings.

    Drives the apply pre-gates (TDD failing-test ordering and human approval
    before writes). These are read by ``HarnessRunner`` and are intentionally
    decoupled from token ``budget_mode`` — TDD enforcement and write approval
    are governance concerns, not budget concerns.
    """

    model_config = ConfigDict(extra="forbid")

    tdd_mode: Literal["ask", "strict", "off"] = Field(
        default="ask",
        description=(
            "TDD failing-test pre-gate mode. 'strict' blocks apply until a "
            "failing test exists for the task; 'ask'/'off' do not block."
        ),
    )
    strict_tdd: bool = Field(
        default=False,
        description="Whether a strict test harness was detected/required for this project.",
    )
    approval_required_for_writes: bool = Field(
        default=False,
        description=(
            "When True, ApplyPhase requires an explicit human approval gate to "
            "pass before any file is edited, independent of budget_mode."
        ),
    )


class RuntimeBrainConfig(BaseModel):
    """Advisory Runtime Brain controls (PR-000.1).

    The Brain *recommends*; the deterministic State Machine always governs
    transitions. When ``enabled`` is False (the default) the runtime uses the
    legacy implicit selectors directly and writes no Decision Log — the layer is
    inert and instantly revertible.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        default=True,
        description=(
            "Enable advisory Runtime Brain decision recording. Off restores the "
            "legacy implicit selectors with no Decision Log writes; the State "
            "Machine governs transitions regardless of this flag."
        ),
    )


class PluginHostConfig(BaseModel):
    """Plugin host configuration (PR-015, book §12 Configuration).

    Types the previously open ``plugins`` v2 section. ``extra="allow"`` keeps the
    v2 open-section contract (unknown keys still validate and round-trip) while
    giving the documented knobs typed defaults. Defaults match book §12:
    discovery on, auto-update off, signatures off, benchmark-on-install on.
    ``contracts_enabled`` is the rollout guard (off routes the legacy
    ``load()``/``register_commands`` path; mirrors PR-003's registry guard).
    """

    model_config = ConfigDict(extra="allow")

    auto_discovery: bool = Field(default=True, description="Discover installed plugins.")
    auto_update: bool = Field(default=False, description="Auto-update plugins.")
    require_signatures: bool = Field(
        default=False, description="Require signed plugin distributions (PR-016)."
    )
    benchmark_on_install: bool = Field(
        default=True, description="Run a plugin's benchmark suite before activation."
    )
    contracts_enabled: bool = Field(
        default=True,
        description="Route plugins through the typed-contract lifecycle (rollout guard).",
    )
    marketplace_enabled: bool = Field(
        default=False,
        description=(
            "Route multi-asset marketplace bundles through the PR-016 install "
            "enforcement (compat/signature/trust/receipt). Off ⇒ legacy single-asset "
            "install path only (rollback guard); marketplace stays optional."
        ),
    )


class StorageConfig(BaseModel):
    """Storage location configuration for runtime-generated state.

    Controls where OpenContext writes KG, memory, traces, embeddings, and
    workspace artifacts. Defaults to ``user`` mode (XDG / %LOCALAPPDATA%).
    Override via ``OPENCONTEXT_STORAGE_MODE=local`` env var or ``mode: local``
    in ``opencontext.yaml`` to restore legacy in-repo layout.
    """

    model_config = ConfigDict(extra="forbid")

    mode: StorageMode = Field(
        default=StorageMode.user,
        description=(
            "Storage mode: 'user' writes to XDG/LOCALAPPDATA user dirs; "
            "'local' writes to .storage/opencontext inside the project repo."
        ),
    )
    custom_path: str | None = Field(
        default=None,
        description=(
            "Absolute path override for storage. When set, overrides both mode and XDG computation."
        ),
    )

    @classmethod
    def from_env_and_config(
        cls,
        mode: StorageMode = StorageMode.user,
        custom_path: str | None = None,
    ) -> StorageConfig:
        """Build a StorageConfig, honouring OPENCONTEXT_STORAGE_MODE env var."""
        import os

        env_val = os.environ.get("OPENCONTEXT_STORAGE_MODE", "").strip().lower()
        if env_val == "local":
            mode = StorageMode.local
        return cls(mode=mode, custom_path=custom_path)


class OpenContextConfig(BaseModel):
    """Top-level runtime configuration."""

    model_config = ConfigDict(extra="forbid")

    # opencontext.yaml schema version (PR-013). A v1 file (no ``version`` key)
    # resolves to ``1`` and keeps loading unchanged; ``version: 2`` opts a config
    # into the sectioned v2 envelope. The v2-only sections below are optional and
    # defaulted, so a v1 config round-trips and a v2 config validates without a
    # Studio/runtime-intelligence implementation having to exist yet.
    version: int = Field(default=1, description="opencontext.yaml schema version (1 or 2).")

    # Selected built-in configuration profile (PR-013, SPEC-CLI-013-02). One of
    # balanced/low-cost/enterprise/research/performance. Resolved against the
    # seven-level resolver (``config_resolver``); ``balanced`` is the default.
    profile: str = Field(default="balanced", description="Active configuration profile.")

    # Test/dev provider override for deterministic OC Flow mutation without live
    # credentials (PROD-002). When ``provider == "test_stub"`` and ``edits_file``
    # resolves under the project root, the CLI builds a TestStubGateway executor.
    # Test-only: a normal config leaves these None and never activates the stub.
    provider: str | None = Field(
        default=None,
        description="Provider override (test/dev: 'test_stub' for deterministic mutation).",
    )
    edits_file: str | None = Field(
        default=None, description="JSON ApplyEdit file used by the test_stub provider."
    )

    project: ProjectConfig = Field(description="Project configuration.")
    models: ModelConfigMap = Field(description="Model aliases.")
    project_index: ProjectIndexConfig = Field(description="Project indexing configuration.")
    context: ContextConfig = Field(description="Context optimization configuration.")
    retrieval: RetrievalConfig = Field(description="Retrieval configuration.")
    repo_map: RepoMapConfig = Field(default_factory=RepoMapConfig)
    context_packing: ContextPackingConfig = Field(default_factory=ContextPackingConfig)
    compression: CompressionPolicyConfig = Field(default_factory=CompressionPolicyConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    provider_policies: list[ProviderPolicyConfig] = Field(default_factory=list)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    traces: TraceStorageConfig = Field(default_factory=TraceStorageConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    memory: MemoryPolicyConfig = Field(default_factory=MemoryPolicyConfig)
    learning: LearningConfig = Field(default_factory=LearningConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    output: OutputPolicyConfig = Field(default_factory=OutputPolicyConfig)
    egress: EgressConfig = Field(default_factory=EgressConfig)
    provider_cache: ProviderCacheConfig = Field(default_factory=ProviderCacheConfig)
    context_layers: dict[str, ContextLayerConfig] = Field(default_factory=dict)
    token_budgets: dict[str, WorkflowTokenBudgetConfig] = Field(default_factory=dict)
    latency: LatencyConfig = Field(default_factory=LatencyConfig)
    commands: dict[str, dict[str, Any]] = Field(default_factory=dict)
    ui_language: str = Field(default="en", description="UI language: en or es.")
    hooks: dict[str, list[str]] = Field(default_factory=dict)
    profiles: dict[str, Any] = Field(default_factory=dict)
    server: ServerConfig = Field(default_factory=ServerConfig)
    workflows: dict[str, WorkflowConfig] = Field(description="Named workflows.")
    sdd: SDDConfig = Field(default_factory=SDDConfig, description="SDD orchestrator configuration.")
    knowledge_graph: KnowledgeGraphConfig = Field(
        default_factory=KnowledgeGraphConfig, description="Code knowledge graph configuration."
    )
    skills: SkillsConfig = Field(
        default_factory=SkillsConfig, description="Skill registry configuration."
    )
    testing: TestingConfig = Field(
        default_factory=TestingConfig, description="Testing configuration."
    )
    verify: VerifyConfig = Field(
        default_factory=VerifyConfig, description="Verify-phase options (e.g. compliance_matrix)."
    )
    storage: StorageConfig = Field(
        default_factory=StorageConfig,
        description=(
            "Storage mode configuration: 'user' (default) writes generated state to "
            "XDG/LOCALAPPDATA; 'local' writes to .storage/opencontext in the repo."
        ),
    )
    context_planning: ContextPlanningConfig = Field(
        default_factory=ContextPlanningConfig, description="Context planning configuration."
    )
    context_storage: ContextStorageConfig = Field(
        default_factory=ContextStorageConfig, description="Context vector storage configuration."
    )
    auto_improve: AutoImproveConfig = Field(
        default_factory=AutoImproveConfig,
        description="Opt-in auto-improvement (self-tuning) controls.",
    )
    harness: HarnessSettingsConfig = Field(
        default_factory=HarnessSettingsConfig,
        description="Agentic harness governance settings (TDD / approval pre-gates).",
    )
    runtime_brain: RuntimeBrainConfig = Field(
        default_factory=RuntimeBrainConfig,
        description="Advisory Runtime Brain decision-layer controls (default off).",
    )
    runtime: RuntimeMigrationConfig = Field(
        default_factory=RuntimeMigrationConfig,
        description="Per-subsystem dual-run migration flags (legacy <-> Runtime vNext).",
    )
    runtime_intelligence_enabled: bool = Field(
        default=True,
        description=(
            "Enable the Runtime Intelligence layer (PR-011): cost/confidence/"
            "simulation/profiler/benchmark/health/evolution reports. Optional and "
            "first-class; default off (advisory — recommends, never overrides)."
        ),
    )

    # ── opencontext.yaml v2 section envelope (PR-013) ────────────────────────
    # The book's v2 schema groups settings into named sections. The sections
    # already modelled above (project/context/memory/compression/providers/
    # observability/skills/workflows/sdd/knowledge_graph/harness/runtime/...)
    # keep their existing typed models for backward compatibility. The sections
    # below are v2-only and have no legacy v1 equivalent, so they are accepted as
    # open mappings (validated, carried into the resolved snapshot) until a
    # downstream PR gives each its own typed model. ``studio`` is reserved here
    # (SPEC-CLI-013-18); the Studio surface itself ships in PR-014.
    workflow: dict[str, Any] = Field(
        default_factory=dict,
        description="v2 workflow-defaults section (selection/lane defaults).",
    )
    personas: dict[str, Any] = Field(default_factory=dict, description="v2 personas section.")
    harnesses: dict[str, Any] = Field(
        default_factory=dict, description="v2 harnesses section (registry overlay)."
    )
    policies: dict[str, Any] = Field(
        default_factory=dict, description="v2 policies section (overlay over `policy`)."
    )
    capabilities: dict[str, Any] = Field(
        default_factory=dict, description="v2 capabilities section (capability graph)."
    )
    runtime_intelligence: dict[str, Any] = Field(
        default_factory=dict,
        description="v2 runtime_intelligence section (cost/confidence/simulator knobs).",
    )
    plugins: PluginHostConfig = Field(
        default_factory=PluginHostConfig,
        description="v2 plugins section (plugin host config, PR-015).",
    )
    studio: dict[str, Any] = Field(
        default_factory=dict,
        description="v2 studio section — reserved for PR-014 (validates, no impl required).",
    )


def find_config(start_dir: str | Path = ".") -> Path | None:
    """Search for ``opencontext.yaml`` in *start_dir* and parent directories.

    Checks up to 10 levels up.  Returns the first ``opencontext.yaml`` found,
    or ``None`` if none exists.
    """
    search_root = Path(start_dir).resolve()
    candidates = ("opencontext.yaml",)
    for _ in range(10):
        for candidate in candidates:
            path = search_root / candidate
            if path.exists():
                return path
        parent = search_root.parent
        if parent == search_root:
            break
        search_root = parent
    return None


def load_config(path: str | Path = "configs/opencontext.yaml") -> OpenContextConfig:
    """Load and validate an OpenContext YAML configuration file.

    If the file does not exist, raises :class:`ConfigurationError`.
    Use :func:`load_config_or_defaults` for a zero-config fallback.
    """

    config_path = Path(path)
    if not config_path.exists():
        raise ConfigurationError(f"Configuration file not found: {config_path}")

    try:
        raw_data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Invalid YAML in {config_path}: {exc}") from exc

    if not isinstance(raw_data, dict):
        raise ConfigurationError(f"Configuration root must be a mapping: {config_path}")

    merged_data = _deep_merge(default_config_data(), _normalize_legacy_config(raw_data))

    try:
        return OpenContextConfig.model_validate(merged_data)
    except Exception as exc:
        raise ConfigurationError(f"Invalid OpenContext configuration: {exc}") from exc


def _normalize_legacy_config(data: dict[str, object]) -> dict[str, object]:
    context = data.get("context")
    if not isinstance(context, dict):
        return data
    compression = context.get("compression")
    if not isinstance(compression, dict):
        return data
    legacy_key = "cave" + "man_intensity"
    if legacy_key in compression:
        compression = dict(compression)
        compression["terse_intensity"] = compression.pop(legacy_key)
        context = dict(context)
        context["compression"] = compression
        data = dict(data)
        data["context"] = context
    return data


def load_config_or_defaults(
    path: str | Path | None = None,
    *,
    auto_detect: bool = True,
) -> OpenContextConfig:
    """Load configuration, or return defaults with auto-detected project name.

    This is the **zero-config** entry point.  When *path* is given and the
    file exists, it loads normally.  When the file is missing and
    *auto_detect* is ``True`` (the default) it:
      1. Searches parent directories for ``opencontext.yaml``.
      2. Falls back to ``default_config_data()`` with the directory name as
         the project name.

    Args:
        path: Explicit config path.  If ``None``, searches from the current
            working directory.
        auto_detect: Enable parent-directory search and fallback defaults.
    """
    if path is not None:
        config_path = Path(path)
        if config_path.exists():
            return load_config(config_path)

    if auto_detect:
        found = find_config(Path.cwd())
        if found is not None:
            return load_config(found)

    # Zero-config fallback
    data = default_config_data()
    project_name = Path.cwd().name or "example-project"
    data["project"] = {"name": project_name}
    return OpenContextConfig.model_validate(data)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def default_config_data() -> dict[str, Any]:
    """Return a default configuration dictionary suitable for YAML serialization."""

    return {
        "project": {"name": "example-project"},
        "models": {
            "default": {
                "provider": "mock",
                "model": "mock-llm",
                "private_endpoint": True,
                "training_opt_in": False,
                "zero_data_retention": True,
            },
            "roles": {
                "classify": {"provider": "mock", "model": "mock-llm"},
                "retrieve": {"provider": "mock", "model": "mock-llm"},
                "rerank": {"provider": "mock", "model": "mock-llm"},
                "compress": {"provider": "mock", "model": "mock-llm"},
                "generate": {"provider": "mock", "model": "mock-llm"},
                "validate": {"provider": "mock", "model": "mock-llm"},
                "audit": {"provider": "mock", "model": "mock-llm"},
                "summarize": {"provider": "mock", "model": "mock-llm"},
                "orchestrate": {"provider": "mock", "model": "mock-llm"},
            },
            "phases": {},
        },
        "project_index": {
            "enabled": True,
            "root": ".",
            "profile": "generic",
            "ignore": list(DEFAULT_IGNORE_PATTERNS),
        },
        "context": {
            "max_input_tokens": 12000,
            "reserve_output_tokens": 1500,
            "sections": {
                "system": 1000,
                "instructions": 1000,
                "tool_schemas": 500,
                "project_manifest": 1000,
                "repo_map": 3000,
                "workflow_contract": 500,
                "memory": 2000,
                "retrieved_context": 6500,
                "conversation": 1000,
                "tools": 500,
            },
            "ranking": {
                "weights": {
                    "relevance": 0.45,
                    "priority": 0.25,
                    "source_trust": 0.15,
                    "token_efficiency": 0.15,
                },
            },
            "compression": {
                "enabled": True,
                "strategy": "extractive_head_tail",
                "terse_intensity": "full",
                "max_compression_ratio": 0.5,
                "adaptive": True,
                "protected_spans": True,
            },
        },
        "retrieval": {"strategy": "hybrid", "top_k": 20, "rerank_top_k": 8},
        "repo_map": {
            "enabled": True,
            "max_tokens": 3000,
            "include_symbols": True,
            "include_dependencies": True,
        },
        "context_packing": {
            "strategy": "priority_value_density",
            "preserve_priorities": ["P0", "P1"],
        },
        "compression": {
            "adaptive": True,
            "protected_spans": True,
            "default_strategy": "extractive_head_tail",
        },
        "cache": {
            "exact": {"enabled": True, "storage": "local"},
            "semantic": {
                "enabled": False,
                "similarity_threshold": 0.92,
                "require_same_workflow": True,
                "require_same_project_hash": True,
            },
            "mcp": {
                "enabled": False,
                "compression_enabled": True,
                "compression_ratio": 0.5,
                "preserve_code_blocks": True,
                "cache_ttl_seconds": 3600,
            },
        },
        "safety": {
            "secret_scanning": {"enabled": True, "redact": True},
            "prompt_injection_detection": {"enabled": True},
        },
        "security": {
            "mode": "private_project",
            "fail_closed": True,
            "default_classification": "internal",
            "external_providers_enabled": False,
        },
        "providers": {"external_enabled": False},
        "provider_policies": [
            {
                "provider": "mock",
                "allowed": True,
                "allowed_classifications": [
                    "public",
                    "internal",
                    "confidential",
                    "secret",
                    "regulated",
                ],
                "require_redaction": False,
                "require_zero_data_retention": False,
                "require_private_endpoint": False,
                "allow_training_opt_in": False,
                "notes": "Local deterministic provider used for development and tests.",
            },
            {
                "provider": "local",
                "allowed": True,
                "allowed_classifications": [
                    "public",
                    "internal",
                    "confidential",
                    "secret",
                    "regulated",
                ],
                "require_redaction": False,
                "require_zero_data_retention": False,
                "require_private_endpoint": False,
                "allow_training_opt_in": False,
                "notes": "Reserved local provider policy; no external SDK is enabled in core.",
            },
            {
                "provider": "openai",
                "allowed": False,
                "allowed_classifications": [
                    "public",
                    "internal",
                ],
                "require_redaction": True,
                "require_zero_data_retention": True,
                "require_private_endpoint": False,
                "allow_training_opt_in": False,
                "notes": "External providers are disabled by default.",
            },
        ],
        "observability": {
            "local_traces": {"enabled": True},
            "opentelemetry": {"enabled": False},
        },
        "traces": {
            "store_raw_context": False,
            "store_redacted_context": True,
        },
        "tools": {
            "native": {"enabled": False},
            "mcp": {
                "enabled": False,
                "require_allowlist": True,
                "allow_stdio": False,
                "sandbox": True,
                "require_write_approval": False,
            },
        },
        "memory": {
            "enabled": True,
            "provider": "local",
            "harvest_after_run": True,
            "require_approval": True,
            "store_raw": False,
            "default_classification": "internal",
            "retention_days": 90,
            "prune_low_reuse": True,
            "prune_superseded": True,
            "prune_expired": True,
        },
        "learning": {"enabled": True},
        "embedding": {
            "enabled": False,
            "provider": "local",
            "model": "deterministic-1536",
            "dimensions": 1536,
            "batch_size": 100,
            "async_worker": True,
            "write_path_sync_timeout_ms": 150,
            "storage_backend": "null",
            "queue_max_size": 10000,
            "worker_concurrency": 4,
        },
        "output": {
            "mode": "concise",
            "max_output_tokens": 1500,
            "preserve": ["code", "commands", "paths", "symbols", "warnings", "numbers"],
        },
        "egress": {
            "network": "deny",
            "external_urls": "ask",
            "webhooks": "deny",
            "clipboard": "allow_redacted",
            "file_export": "allow_redacted",
            "tool_output_forwarding": "deny",
        },
        "provider_cache": {
            "strategy": "auto",
            "explicit_cache_enabled": False,
            "ttl_seconds": 3600,
            "cacheable_sections": [
                "tool_schemas",
                "system",
                "project_manifest",
                "repo_map",
                "workflow_contract",
            ],
        },
        "context_layers": {
            "static": {
                "cacheable": True,
                "budget_tokens": 2000,
                "trust_level": "trusted",
                "refresh_policy": "versioned",
            },
            "project": {
                "cacheable": True,
                "budget_tokens": 4000,
                "trust_level": "internal",
                "refresh_policy": "on_index",
            },
            "memory": {
                "cacheable": "partial",
                "budget_tokens": 1500,
                "trust_level": "internal",
                "refresh_policy": "on_demand",
            },
            "turn": {
                "cacheable": False,
                "budget_tokens": 2000,
                "trust_level": "user_input",
                "refresh_policy": "per_turn",
            },
            "tool": {
                "cacheable": False,
                "budget_tokens": 1000,
                "trust_level": "untrusted",
                "refresh_policy": "per_call",
            },
        },
        "token_budgets": {
            "ask": {"input": 6000, "output": 1000},
            "plan": {"input": 10000, "output": 2000},
            "review": {"input": 12000, "output": 2500},
            "audit": {"input": 12000, "output": 3000},
            "implement_pack": {"input": 16000, "output": 2000},
        },
        "latency": {"max_seconds": {"ask": 20, "plan": 60, "audit": 120}},
        "commands": {
            "review-pr": {
                "workflow": "code-review",
                "mode": "review",
                "output_mode": "concise",
            },
            "security-audit": {
                "workflow": "security-audit",
                "mode": "audit",
                "output_mode": "report",
            },
        },
        "hooks": {
            "pre_context_pack": ["security.scan", "prompt.audit"],
            "post_context_pack": ["trace.persist", "tokens.report"],
            "pre_release": ["release.audit", "prompt.audit", "security.scan"],
        },
        "profiles": {},
        "server": {"enabled": False, "host": "127.0.0.1", "port": 8000},
        "workflows": {
            "code_assistant": {
                "steps": [
                    "project.load_manifest",
                    "project.retrieve",
                    "context.rank",
                    "context.pack",
                    "context.compress",
                    "prompt.assemble",
                    "llm.generate",
                    "trace.persist",
                ],
            },
            "sdd": {
                "steps": [
                    "project.load_manifest",
                    "context.explore",
                    "context.propose",
                    "context.test",
                    "context.verify",
                    "context.review",
                    "context.archive",
                    "trace.sdd_persist",
                ],
            },
            "sdd_apply": {
                "steps": [
                    "project.load_manifest",
                    "context.explore",
                    "context.propose",
                    "context.apply",
                    "context.test",
                    "context.verify",
                    "context.review",
                    "context.up-code",
                    "context.archive",
                    "trace.sdd_persist",
                ],
            },
        },
        "sdd": {
            "artifact_store": {
                "mode": "none",
                "engram": {},
                "openspec": {"path": "openspec/"},
            },
            "delivery_strategy": "plan-only",
            "chain_strategy": "stacked-to-main",
            "model_assignments": {
                "explore": "default",
                "propose": "default",
                "spec": "default",
                "design": "default",
                "tasks": "default",
                "apply": "default",
                "verify": "default",
                "archive": "default",
            },
            "interactive": False,
        },
        "knowledge_graph": {
            "enabled": True,
            "languages": [],
            "exclude": [
                "node_modules/**",
                "vendor/**",
                "__pycache__/**",
                ".git/**",
                "*.min.js",
                "*.min.css",
            ],
            "max_file_size": 1048576,
            "track_call_sites": True,
            "auto_sync": True,
            "track_class_hierarchy": True,
        },
        "skills": {
            "enabled": False,
            "registry_path": ".atl/skill-registry.md",
            "auto_discover": True,
            "user_dirs": [
                "~/.config/opencode/skills/",
                "~/.claude/skills/",
            ],
            "project_dirs": [
                ".claude/skills/",
                "skills/",
            ],
        },
        "ui_language": "en",
        "runtime": {
            "session_wrapper": True,
            "registry_enabled": True,
            "persona_registry_enabled": True,
            "skill_registry_enabled": True,
            "harness_registry_enabled": True,
            "gateway_enabled": True,
            "context_engine_enabled": True,
            "execution_profile": "balanced",
            "durable_artifacts": True,
            "oc_flow_enabled": True,
            "kg_v2_enabled": True,
            "memory_v2_enabled": True,
            "retention": {
                "summaries": "always",
                "receipts": "always",
                "patches": "always",
                "checkpoints": "until_archive",
                "logs": "30d",
                "ephemeral_context": "until_success",
            },
            "sdd_strict": False,
        },
        # Runtime Intelligence layer (PR-011): vNext-default (parity-gated flip,
        # tests/compat/flip_baseline/runtime_intelligence.json). Advisory — recommends,
        # never overrides. Top-level flag (not under ``runtime``).
        "runtime_intelligence_enabled": True,
        # Studio surface (PR-014). Optional + default off: the runtime/CLI/MCP run
        # headless with no Studio (SPEC-STU-014-12). The local read-only web shell
        # is launched explicitly via ``opencontext studio``; this flag records
        # whether the surface is enabled and is surfaced read-only by Studio.
        "studio": {"enabled": False},
    }
