"""Context domain models used by ranking, budgeting, compression, and prompts."""

from __future__ import annotations

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


class ContextOmission(BaseModel):
    """Traceable reason a context item was omitted from a packed prompt."""

    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(description="Identifier of the omitted context item.")
    reason: str = Field(description="Decision reason for omission.")
    tokens: int = Field(ge=0, description="Token estimate of the omitted item.")
    score: float = Field(ge=0.0, description="Ranking or retrieval score of the omitted item.")


class ContextPackResult(BaseModel):
    """Result of token-aware context packing."""

    model_config = ConfigDict(extra="forbid")

    included: list[ContextItem] = Field(description="Items included in the pack.")
    omitted: list[ContextItem] = Field(description="Items omitted from the pack.")
    used_tokens: int = Field(ge=0, description="Tokens used by included items.")
    available_tokens: int = Field(ge=0, description="Budget available to the packer.")
    omissions: list[ContextOmission] = Field(description="Traceable omission records.")


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
