"""Context domain models used by ranking, budgeting, compression, and prompts."""

from __future__ import annotations

from collections.abc import Iterable
from enum import IntEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import StrEnum


class ContextPriority(IntEnum):
    """Explicit context priorities, where lower numeric values are more important."""

    P0 = 0
    P1 = 1
    P2 = 2
    P3 = 3
    P4 = 4
    P5 = 5


class ContentFormat(StrEnum):
    """Structural format of content, detected at routing time."""

    PROSE = "prose"
    CODE = "code"
    JSON_STRUCTURED = "json_structured"
    JSON_ARRAY = "json_array"
    SHELL_OUTPUT = "shell_output"
    LOGS = "logs"
    MARKDOWN = "markdown"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class CompressionStrategy(StrEnum):
    """Supported v0.1 compression strategies."""

    NONE = "none"
    TRUNCATE = "truncate"
    EXTRACTIVE_HEAD_TAIL = "extractive_head_tail"
    BULLET_FACTS_PLACEHOLDER = "bullet_facts_placeholder"
    TERSE = "terse"
    COMPACT = "compact"
    DEEP = "deep"
    EFFICIENT = "efficient"
    SIGNATURE = "signature"
    SMART_CRUSHER = "smart_crusher"
    CODE_AST = "code_ast"
    CACHE_ALIGN = "cache_align"
    OUTPUT_REDUCE = "output_reduce"
    CCR = "ccr"

    @classmethod
    def _missing_(cls, value: object) -> CompressionStrategy | None:
        if value == "cave" + "man":
            return cls.TERSE
        return None


class DataClassification(StrEnum):
    """Security classification for any context-carrying object."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    SECRET = "secret"
    REGULATED = "regulated"


class RetrievalStrategy(StrEnum):
    """The seven named retrieval strategies (OC-CONTEXT-001 §Retrieval Strategies).

    The Context Harness selects one per workflow node; each is a deterministic
    re-ordering of an existing evidence plan, not a separate retriever.
    """

    SYMBOL_FIRST = "symbol_first"
    TEST_FIRST = "test_first"
    OWNER_FIRST = "owner_first"
    FAILURE_FIRST = "failure_first"
    ARCHITECTURE_FIRST = "architecture_first"
    DECISION_FIRST = "decision_first"
    COMMAND_FIRST = "command_first"


class ContextProfile(StrEnum):
    """The five context profiles (OC-CONTEXT-001 §Context Profiles).

    Each profile tunes retrieval depth, compression aggressiveness, memory limits,
    and file-loading thresholds. ``BALANCED`` reproduces current default behaviour.
    """

    BALANCED = "balanced"
    LOW_COST = "low-cost"
    PERFORMANCE = "performance"
    ENTERPRISE = "enterprise"
    RESEARCH = "research"


class ContextItem(BaseModel):
    """A candidate or selected unit of context that may be sent to an LLM."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable identifier for the context item.")
    content: str = Field(description="Text payload that may be assembled into the prompt.")
    source: str = Field(description="Human-readable source path, memory key, or tool name.")
    source_type: str = Field(description="Source category such as file, symbol, memory, or tool.")
    priority: ContextPriority = Field(description="Business priority for budget decisions.")
    tokens: int = Field(ge=0, description="Estimated token count for the content.")
    score: float = Field(ge=0.0, description="Current relevance or ranking score.")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Traceable decision metadata such as matched terms or compression details.",
    )
    classification: DataClassification = Field(
        default=DataClassification.INTERNAL,
        description="Security classification for this context item.",
    )
    trusted: bool = Field(default=False, description="Whether source is considered trusted.")
    redacted: bool = Field(default=False, description="Whether sensitive values were redacted.")
    source_trust: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Normalized trust score for source provenance.",
    )

    @property
    def source_path(self) -> str:
        """Bare source path with any ``path:line`` chunk suffix removed.

        Graph-symbol pack items carry chunk-suffixed sources (``src/auth.py:2``)
        internally, but public surfaces — API ``included_sources``, trace
        ``quality_inputs``, harness provenance gates — report bare file paths.
        This property is the single normalization point: it prefers the item's
        ``graph_provenance.file_path``, falls back to stripping a numeric
        ``:line`` suffix, and leaves non-chunked sources (files, ``memory:key``
        identifiers, tool names) untouched.
        """
        provenance = self.metadata.get("graph_provenance")
        if isinstance(provenance, dict):
            file_path = provenance.get("file_path")
            if isinstance(file_path, str) and file_path:
                return file_path
        base, sep, suffix = self.source.rpartition(":")
        if sep and suffix.isdigit():
            return base
        return self.source


def unique_source_paths(items: Iterable[ContextItem]) -> list[str]:
    """Order-preserving unique bare source paths for a sequence of pack items.

    The projection used by every surface bound to the public bare-path contract
    (``included_sources`` / ``omitted_sources``): chunks of the same file
    collapse to one entry, first-seen order wins.
    """
    return list(dict.fromkeys(item.source_path for item in items))


class ContextOmission(BaseModel):
    """Traceable reason a context item was omitted from a packed prompt."""

    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(description="Identifier of the omitted context item.")
    reason: str = Field(description="Decision reason for omission.")
    tokens: int = Field(ge=0, description="Token estimate of the omitted item.")
    score: float = Field(ge=0.0, description="Ranking or retrieval score of the omitted item.")


class CompressionPackMetadata(BaseModel):
    """Pack-level compression metadata. Only present when compression actually ran."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(description="True only when compression ran on at least one item.")
    tokens_before: int = Field(
        ge=0, description="Sum of original token estimates before compression."
    )
    tokens_after: int = Field(ge=0, description="Sum of token estimates after compression.")
    items_compressed: int = Field(ge=0, description="Number of items that were compressed.")


class ContextPackMetrics(BaseModel):
    """Mandatory pack metrics block (KG_CONTEXT_COMPRESSION_CONTRACT)."""

    model_config = ConfigDict(extra="forbid")

    budget_tokens: int = Field(ge=0, description="Token budget given to the packer.")
    input_tokens_estimated: int = Field(
        ge=0, description="Estimated tokens across all candidates considered."
    )
    output_tokens_estimated: int = Field(ge=0, description="Estimated tokens of the packed output.")
    compression_ratio: float | None = Field(
        default=None,
        description="tokens_after / tokens_before when compression ran; null otherwise.",
    )
    kg_used: bool = Field(description="Whether knowledge-graph candidates entered the pack.")
    kg_nodes_used: int = Field(ge=0, description="KG-backed nodes selected into the pack.")
    kg_edges_used: int = Field(
        ge=0, description="KG edges behind the selected nodes (provenance + expansion hops)."
    )
    test_nodes_included: int = Field(
        default=0,
        ge=0,
        description=(
            "KG-backed test nodes selected into the pack (plan kg block "
            "`test_nodes_included`). Defaults to 0 so legacy persisted packs validate."
        ),
    )
    kg_reason: str | None = Field(
        default=None,
        description=(
            "Pack-level KG selection rationale (plan kg block `reason`). Null on "
            "legacy persisted packs built before the field existed."
        ),
    )
    memory_hits: int = Field(ge=0, description="Memory-sourced items included in the pack.")
    protected_spans: int = Field(
        ge=0, description="Protected spans detected in selected candidates."
    )
    protected_spans_kept: int = Field(
        ge=0, description="Protected spans preserved in the final pack content."
    )
    excluded_files: int = Field(ge=0, description="Candidates omitted from the pack.")


class ContextPackResult(BaseModel):
    """Result of token-aware context packing."""

    model_config = ConfigDict(extra="forbid")

    included: list[ContextItem] = Field(description="Items included in the pack.")
    omitted: list[ContextItem] = Field(description="Items omitted from the pack.")
    used_tokens: int = Field(ge=0, description="Tokens used by included items.")
    available_tokens: int = Field(ge=0, description="Budget available to the packer.")
    omissions: list[ContextOmission] = Field(description="Traceable omission records.")
    compression: CompressionPackMetadata | None = Field(
        default=None,
        description=(
            "Pack-level compression metadata. Emitted only when compression actually ran "
            "on at least one item; absent (null) when no compression was applied."
        ),
    )
    context: ContextPackMetrics | None = Field(
        default=None,
        description="Additive pack metrics block (budget, KG usage, memory, protected spans).",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Additive advisory warnings (e.g. missing or empty index).",
    )

    @property
    def token_budget(self) -> int:
        """Alias for available_tokens — explicit budget given to the packer."""
        return self.available_tokens

    @property
    def tokens_used(self) -> int:
        """Alias for used_tokens — tokens consumed by included items."""
        return self.used_tokens


class TokenBudget(BaseModel):
    """Calculated token budget for one runtime invocation."""

    model_config = ConfigDict(extra="forbid")

    max_input_tokens: int = Field(gt=0, description="Maximum model input tokens.")
    reserve_output_tokens: int = Field(ge=0, description="Tokens reserved for model output.")
    available_context_tokens: int = Field(
        ge=0,
        description="Maximum input tokens available after reserving output tokens.",
    )
    sections: dict[str, int] = Field(
        description="Configured per-section token budgets such as system and retrieved_context.",
    )


class CompressionResult(BaseModel):
    """Result metadata for an attempted compression operation."""

    model_config = ConfigDict(extra="forbid")

    item: ContextItem = Field(description="The resulting context item.")
    original_tokens: int = Field(ge=0, description="Token estimate before compression.")
    compressed_tokens: int = Field(ge=0, description="Token estimate after compression.")
    strategy: CompressionStrategy = Field(description="Compression strategy that was applied.")
    lossiness: str = Field(description="Human-readable lossiness classification.")
    reversible: bool = Field(
        default=False,
        description="True when the original content can be fully recovered (e.g. CCR cache).",
    )
    expand_hint: str = Field(
        default="",
        description="How to recover the original if reversible=True (e.g. cache key).",
    )


class ProtectedSpan(BaseModel):
    """A span that compression must preserve or use to skip lossy compression."""

    model_config = ConfigDict(extra="forbid")

    start: int = Field(ge=0, description="Start character offset.")
    end: int = Field(ge=0, description="End character offset.")
    kind: str = Field(description="Protected span kind.")
    content: str = Field(description="Exact protected content.")


class CompressionDecision(BaseModel):
    """Adaptive compression policy decision for one context item."""

    model_config = ConfigDict(extra="forbid")

    strategy: CompressionStrategy = Field(description="Selected compression strategy.")
    max_ratio: float = Field(gt=0.0, le=1.0, description="Maximum compressed/original ratio.")
    allow_lossy: bool = Field(description="Whether lossy compression is allowed.")
    reason: str = Field(description="Deterministic policy reason.")


class PromptSection(BaseModel):
    """Named prompt section emitted by the prompt assembler."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Section name.")
    content: str = Field(description="Rendered section content.")
    stable: bool = Field(
        default=False,
        description="Whether this section belongs to the stable prompt-cache prefix.",
    )
    tokens: int = Field(ge=0, description="Estimated tokens for this section.")
    priority: ContextPriority = Field(
        default=ContextPriority.P2,
        description="Priority of the section for prompt planning.",
    )
    classification: DataClassification = Field(
        default=DataClassification.INTERNAL,
        description="Security classification for this prompt section.",
    )
    trusted: bool = Field(default=False, description="Whether section content is trusted.")
    redacted: bool = Field(default=False, description="Whether content was redacted.")
    source_ids: list[str] = Field(default_factory=list, description="Source identifiers.")


class CacheAlignment(BaseModel):
    """KV-cache alignment metadata produced by CacheAligner."""

    model_config = ConfigDict(extra="forbid")

    stable_prefix: str = Field(description="Byte-stable portion for KV cache hits.")
    compressible_payload: str = Field(description="Variable portion that may be compressed.")
    prefix_hash: str = Field(description="SHA-256 prefix of the stable portion (first 16 hex).")
    prefix_tokens_estimate: int = Field(ge=0, description="Estimated stable prefix token count.")
    is_cacheable: bool = Field(description="True when the stable prefix matches the prior turn.")


class AssembledPrompt(BaseModel):
    """Complete prompt and section-level accounting."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(description="Final prompt text sent to the LLM gateway.")
    sections: list[PromptSection] = Field(description="Prompt sections in assembly order.")
    total_tokens: int = Field(ge=0, description="Estimated total prompt tokens.")
    cache_alignment: CacheAlignment | None = Field(
        default=None,
        description="KV-cache alignment info. Present when CacheAligner was applied.",
    )
