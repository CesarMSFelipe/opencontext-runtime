"""Configuration loading for OpenContext Runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from opencontext_core.compat import StrEnum
from opencontext_core.errors import ConfigurationError
from opencontext_core.models.context import CompressionStrategy

DEFAULT_IGNORE_PATTERNS: tuple[str, ...] = (
    ".git",
    ".opencontext",
    ".storage",
    ".venv",
    "venv",
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
)


class ProjectConfig(BaseModel):
    """Project-level runtime configuration."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Human-readable project name.")


class ModelProviderConfig(BaseModel):
    """Provider-neutral model selection."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(description="Provider key such as mock.")
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

    model_config = ConfigDict(extra="forbid")

    weights: RankingWeightsConfig = Field(description="Ranking formula weights.")


class CompressionConfig(BaseModel):
    """Safe compression configuration with caveman protocol."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, description="Whether compression is enabled.")
    strategy: CompressionStrategy = Field(
        default=CompressionStrategy.EXTRACTIVE_HEAD_TAIL,
        description="Configured compression strategy.",
    )
    caveman_intensity: str = Field(
        default="full",
        description="Caveman compression intensity: 'lite', 'full', or 'ultra'.",
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
        default=True, description="Enable caveman compression for MCP responses."
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


class CacheConfig(BaseModel):
    """Runtime cache configuration."""

    model_config = ConfigDict(extra="forbid")

    exact: ExactCacheConfig = Field(default_factory=ExactCacheConfig)
    semantic: SemanticCacheConfig = Field(default_factory=SemanticCacheConfig)
    mcp: MCPCacheConfig = Field(default_factory=MCPCacheConfig)


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


class ProvidersConfig(BaseModel):
    """Provider availability defaults."""

    model_config = ConfigDict(extra="forbid")

    external_enabled: bool = Field(
        default=False,
        description="External providers disabled by default.",
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


class ToolsConfig(BaseModel):
    """Tool runtime configuration."""

    model_config = ConfigDict(extra="forbid")

    native: NativeToolsConfig = Field(default_factory=NativeToolsConfig)
    mcp: McpToolsConfig = Field(default_factory=McpToolsConfig)


class MemoryPolicyConfig(BaseModel):
    """Memory defaults for progressive disclosure and harvesting."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, description="Local memory layer enabled.")
    harvest_after_run: bool = Field(default=False, description="Automatic harvest disabled.")
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

    enabled: bool = Field(default=True, description="Async embedding generation enabled.")
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
    storage_backend: str = Field(
        default="local", description="Vector storage: local, pgvector, qdrant, etc."
    )
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
    step: str | None = Field(
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


class OpenContextConfig(BaseModel):
    """Top-level runtime configuration."""

    model_config = ConfigDict(extra="forbid")

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
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    provider_policies: list[ProviderPolicyConfig] = Field(default_factory=list)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    traces: TraceStorageConfig = Field(default_factory=TraceStorageConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    memory: MemoryPolicyConfig = Field(default_factory=MemoryPolicyConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    output: OutputPolicyConfig = Field(default_factory=OutputPolicyConfig)
    egress: EgressConfig = Field(default_factory=EgressConfig)
    provider_cache: ProviderCacheConfig = Field(default_factory=ProviderCacheConfig)
    context_layers: dict[str, ContextLayerConfig] = Field(default_factory=dict)
    token_budgets: dict[str, WorkflowTokenBudgetConfig] = Field(default_factory=dict)
    latency: LatencyConfig = Field(default_factory=LatencyConfig)
    commands: dict[str, dict[str, Any]] = Field(default_factory=dict)
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

    merged_data = _deep_merge(default_config_data(), raw_data)

    try:
        return OpenContextConfig.model_validate(merged_data)
    except Exception as exc:
        raise ConfigurationError(f"Invalid OpenContext configuration: {exc}") from exc


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
                "caveman_intensity": "full",
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
            },
        },
        "memory": {
            "enabled": True,
            "harvest_after_run": False,
            "require_approval": True,
            "store_raw": False,
            "default_classification": "internal",
            "retention_days": 90,
            "prune_low_reuse": True,
            "prune_superseded": True,
            "prune_expired": True,
        },
        "embedding": {
            "enabled": True,
            "provider": "local",
            "model": "deterministic-1536",
            "dimensions": 1536,
            "batch_size": 100,
            "async_worker": True,
            "write_path_sync_timeout_ms": 150,
            "storage_backend": "local",
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
    }
