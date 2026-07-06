"""Safe and explicitly lossy context compression."""

from __future__ import annotations

from typing import Any

from opencontext_core.compression.code_compressor import CodeCompressionMode, CodeCompressor
from opencontext_core.compression.terse import TerseCompressor
from opencontext_core.config import CompressionConfig
from opencontext_core.context.budgeting import estimate_tokens
from opencontext_core.context.protection import ProtectedSpanManager
from opencontext_core.models.context import (
    CompressionResult,
    CompressionStrategy,
    ContentFormat,
    ContextItem,
)

# --- PR-010 §Semantic Compression priority taxonomy (OC-CONTEXT-001) -----------
# Declarative keep/compress/discard rules. KEEP kinds are never lossy-compressed
# (enforced via ProtectedSpanManager KEEP spans); COMPRESS kinds may be reduced
# aggressively; DISCARD kinds are dropped and recorded as omissions (see context/gc).
KEEP_KINDS: tuple[str, ...] = (
    "acceptance_criteria",
    "constraint",
    "signature",
    "diagnostic",
    "evidence",
    "failed_strategy",
    # CTX-PROTECTED-LIST (DOC2 §13.4): imports, relevant configuration,
    # memory/KG-referenced fragments, recent changes, recent decisions.
    "import",
    "configuration",
    "referenced_fragment",
    "recent_change",
    "recent_decision",
)
COMPRESS_KINDS: tuple[str, ...] = (
    "repeated_log",
    "duplicate_snippet",
    "long_stack_trace",
    "repetitive_plan",
)
DISCARD_KINDS: tuple[str, ...] = (
    "obsolete_reasoning",
    "superseded_attempt",
    "transient",
    "duplicated_tool_output",
)

# Protected-span kinds that map onto the KEEP taxonomy (so a detected span of one of
# these kinds means "do not lossy-compress this item").
_PROTECTED_KEEP_KINDS: frozenset[str] = frozenset(
    {
        "acceptance_criteria",
        "signature",
        "diagnostic",
        "evidence",
        "warning",
        "constraint",
        "import",
        "configuration",
        "referenced_fragment",
        "recent_change",
        "recent_decision",
    }
)

# Span kinds that are NOT load-bearing: a bare number or import path fires on
# virtually every real code/text item, so treating them as "protected" blocked
# all compression. Everything else (code_block, json_schema, citation, warning,
# and the semantic-KEEP kinds) still blocks lossy compression.
_TRIVIAL_SPAN_KINDS: frozenset[str] = frozenset({"numeric_value", "file_path"})


def compression_priority(kind: str) -> str:
    """Classify a span/content ``kind`` as ``keep`` | ``compress`` | ``discard``.

    Unknown kinds default to ``compress`` (safe: compressible, never silently kept
    or dropped). The three buckets are the book's §Semantic Compression taxonomy.
    """
    if kind in KEEP_KINDS:
        return "keep"
    if kind in DISCARD_KINDS:
        return "discard"
    if kind in COMPRESS_KINDS:
        return "compress"
    return "compress"


# Maps detected ContentFormat to a CompressionStrategy when adaptive routing is active.
# Falls back to config.strategy for MIXED / UNKNOWN.
_FORMAT_TO_STRATEGY: dict[ContentFormat, CompressionStrategy] = {
    ContentFormat.CODE: CompressionStrategy.CODE_AST,
    ContentFormat.JSON_ARRAY: CompressionStrategy.SMART_CRUSHER,
    ContentFormat.JSON_STRUCTURED: CompressionStrategy.SMART_CRUSHER,
    ContentFormat.SHELL_OUTPUT: CompressionStrategy.EXTRACTIVE_HEAD_TAIL,
    ContentFormat.LOGS: CompressionStrategy.TERSE,
    ContentFormat.MARKDOWN: CompressionStrategy.EXTRACTIVE_HEAD_TAIL,
    ContentFormat.PROSE: CompressionStrategy.EXTRACTIVE_HEAD_TAIL,
}


class CompressionEngine:
    """Applies deterministic compression strategies and records lossiness."""

    def __init__(self, config: CompressionConfig, *, semantic_protection: bool = False) -> None:
        self.config = config
        self.protected_spans = ProtectedSpanManager()
        # PR-010: when set, the engine also treats acceptance criteria / signatures /
        # diagnostics / evidence as protected (book §Semantic Compression KEEP rules).
        # Default off so legacy compression is byte-identical.
        self.semantic_protection = semantic_protection
        self._code_compressor: CodeCompressor | None = None
        self._cache_aligner: Any | None = None
        self._output_reducer: Any | None = None
        # ContentRouter is imported lazily to avoid circular imports.
        self._content_router: Any | None = None

    def _get_strategy(self, item: ContextItem) -> CompressionStrategy:
        """Return compression strategy for an item.

        When adaptive routing is enabled, detects content format and selects
        the best strategy. Falls back to config.strategy for unknown formats.
        """
        if not getattr(self.config, "adaptive", False):
            return self.config.strategy

        if self._content_router is None:
            try:
                from opencontext_core.memory_usability.content_router import ContentRouter

                self._content_router = ContentRouter()
            except ImportError:
                return self.config.strategy

        try:
            route = self._content_router.route(item.content)
            return _FORMAT_TO_STRATEGY.get(route.content_format, self.config.strategy)
        except Exception:
            return self.config.strategy

    def compress_item(self, item: ContextItem) -> CompressionResult:
        """Compress a single context item according to configuration."""

        if not self.config.enabled or self.config.strategy is CompressionStrategy.NONE:
            return self._result(item, item, CompressionStrategy.NONE, "none")

        spans = (
            self.protected_spans.detect(item.content, include_semantic=self.semantic_protection)
            if self.config.protected_spans
            else []
        )
        # Only LOAD-BEARING spans block compression. `numeric_value` and `file_path`
        # fire on virtually every real code/text item (any digit, any import path),
        # so bailing on *any* span meant compression NEVER ran on real content —
        # savings came only from selection, not compression. Warnings, constraints,
        # schemas, code blocks, citations and the semantic-KEEP kinds still refuse
        # lossy compression so critical spans are preserved verbatim.
        load_bearing = [s for s in spans if s.kind not in _TRIVIAL_SPAN_KINDS]
        if load_bearing:
            metadata = dict(item.metadata)
            metadata["protected_spans"] = [span.model_dump() for span in load_bearing]
            metadata["compression"] = {
                "original_token_estimate": item.tokens,
                "compressed_token_estimate": item.tokens,
                "strategy": CompressionStrategy.NONE.value,
                "lossiness": "none",
                "reason": "protected_spans_detected",
            }
            preserved = item.model_copy(update={"metadata": metadata})
            return self._result(preserved, preserved, CompressionStrategy.NONE, "none")

        target_tokens = max(1, int(item.tokens * self.config.max_compression_ratio))
        strategy = self._get_strategy(item)
        strategy_value = strategy.value

        # Route by strategy
        if strategy_value == CompressionStrategy.NONE.value:
            return self._result(item, item, CompressionStrategy.NONE, "none")
        elif strategy_value == CompressionStrategy.TERSE.value:
            return self._compress_terse(item)
        elif strategy_value == CompressionStrategy.SMART_CRUSHER.value:
            return self._compress_smart_crusher(item)
        elif strategy_value == CompressionStrategy.CODE_AST.value:
            return self._compress_code_ast(item)
        elif strategy_value == CompressionStrategy.TRUNCATE.value:
            compressed_content = _truncate_to_tokens(item.content, target_tokens)
            lossiness = "lossy_truncation"
        elif strategy_value == CompressionStrategy.EXTRACTIVE_HEAD_TAIL.value:
            compressed_content = _extractive_head_tail(item.content, target_tokens)
            lossiness = "lossy_extractive"
        elif strategy_value == CompressionStrategy.BULLET_FACTS_PLACEHOLDER.value:
            compressed_content = _bullet_facts_placeholder(item.content, target_tokens)
            lossiness = "lossy_placeholder"
        elif strategy_value == CompressionStrategy.COMPACT.value:
            return self._compress_compact(item)
        elif strategy_value == CompressionStrategy.DEEP.value:
            return self._compress_deep_with_fallback(item)
        elif strategy_value == CompressionStrategy.EFFICIENT.value:
            return self._compress_efficient(item)
        elif strategy_value == CompressionStrategy.SIGNATURE.value:
            return self._compress_signature(item)
        else:
            raise ValueError(f"Unsupported compression strategy: {strategy_value}")

        compressed_tokens = estimate_tokens(compressed_content)
        if compressed_tokens > target_tokens:
            compressed_content = _truncate_to_tokens(compressed_content, target_tokens)
            compressed_tokens = estimate_tokens(compressed_content)

        metadata = dict(item.metadata)
        metadata["compression"] = {
            "original_token_estimate": item.tokens,
            "compressed_token_estimate": compressed_tokens,
            "strategy": strategy.value,
            "lossiness": lossiness,
        }
        compressed_item = item.model_copy(
            update={
                "content": compressed_content,
                "tokens": compressed_tokens,
                "metadata": metadata,
            }
        )
        return self._result(item, compressed_item, strategy, lossiness)

    def compress_items(
        self,
        items: list[ContextItem],
        budget_tokens: int | None = None,
    ) -> tuple[list[ContextItem], list[CompressionResult]]:
        """Compress items and optionally keep only those that fit a token budget."""

        results: list[CompressionResult] = []
        compressed_items: list[ContextItem] = []
        used_tokens = 0
        for item in items:
            result = self.compress_item(item)
            candidate = result.item
            if budget_tokens is not None and used_tokens + candidate.tokens > budget_tokens:
                remaining_tokens = budget_tokens - used_tokens
                if remaining_tokens <= 0:
                    results.append(result)
                    continue
                candidate = _clamp_to_budget(candidate, remaining_tokens)
                result = CompressionResult(
                    item=candidate,
                    original_tokens=result.original_tokens,
                    compressed_tokens=candidate.tokens,
                    strategy=result.strategy,
                    # Mirror the item's own lossiness so a consumer reading
                    # result.lossiness learns when a protected span was dropped
                    # (was hardcoded "lossy_budget_clamp", hiding the protected case).
                    lossiness=candidate.metadata.get("compression", {}).get(
                        "lossiness", "lossy_budget_clamp"
                    ),
                )
            results.append(result)
            if budget_tokens is None or used_tokens + candidate.tokens <= budget_tokens:
                compressed_items.append(candidate)
                used_tokens += candidate.tokens
        return compressed_items, results

    def _result(
        self,
        original_item: ContextItem,
        compressed_item: ContextItem,
        strategy: CompressionStrategy,
        lossiness: str,
    ) -> CompressionResult:
        reversible = strategy is CompressionStrategy.CCR
        return CompressionResult(
            item=compressed_item,
            original_tokens=original_item.tokens,
            compressed_tokens=compressed_item.tokens,
            strategy=strategy,
            lossiness=lossiness,
            reversible=reversible,
            expand_hint="ccr_cache" if reversible else "",
        )

    def _compress_terse(self, item: ContextItem) -> CompressionResult:
        """Apply terse compression to preserve technical content."""

        compressor = TerseCompressor(intensity=self.config.terse_intensity)
        compressed_content = compressor.compress(item.content)
        compressed_tokens = estimate_tokens(compressed_content)

        metadata = dict(item.metadata)
        savings = compressor.get_token_savings(item.content, compressed_content)
        metadata["compression"] = {
            "original_token_estimate": item.tokens,
            "compressed_token_estimate": compressed_tokens,
            "strategy": CompressionStrategy.TERSE.value,
            "lossiness": "lossy_terse",
            "savings": savings,
        }
        compressed_item = item.model_copy(
            update={
                "content": compressed_content,
                "tokens": compressed_tokens,
                "metadata": metadata,
            }
        )
        return self._result(item, compressed_item, CompressionStrategy.TERSE, "lossy_terse")

    def _compress_compact(self, item: ContextItem) -> CompressionResult:
        """Apply structural compact compression."""
        from opencontext_core.backends.compression.compact import CompactCompressionBackend

        backend = CompactCompressionBackend()
        spans = self.protected_spans.detect(item.content) if self.config.protected_spans else []
        compressed_content = backend.compress(item.content, spans)
        compressed_tokens = estimate_tokens(compressed_content)
        metadata = dict(item.metadata)
        metadata["compression"] = {
            "original_token_estimate": item.tokens,
            "compressed_token_estimate": compressed_tokens,
            "strategy": CompressionStrategy.COMPACT.value,
            "lossiness": "lossy_structural",
        }
        compressed_item = item.model_copy(
            update={
                "content": compressed_content,
                "tokens": compressed_tokens,
                "metadata": metadata,
            }
        )
        return self._result(item, compressed_item, CompressionStrategy.COMPACT, "lossy_structural")

    def _compress_efficient(self, item: ContextItem) -> CompressionResult:
        """Apply maximum efficient compression (compact + terse + extended dict)."""
        from opencontext_core.backends.compression.efficient import EfficientCompressionBackend

        backend = EfficientCompressionBackend()
        spans = self.protected_spans.detect(item.content) if self.config.protected_spans else []
        compressed_content = backend.compress(item.content, spans)
        compressed_tokens = estimate_tokens(compressed_content)
        metadata = dict(item.metadata)
        metadata["compression"] = {
            "original_token_estimate": item.tokens,
            "compressed_token_estimate": compressed_tokens,
            "strategy": CompressionStrategy.EFFICIENT.value,
            "lossiness": "lossy_maximum",
        }
        compressed_item = item.model_copy(
            update={
                "content": compressed_content,
                "tokens": compressed_tokens,
                "metadata": metadata,
            }
        )
        return self._result(item, compressed_item, CompressionStrategy.EFFICIENT, "lossy_maximum")

    def _compress_signature(self, item: ContextItem) -> CompressionResult:
        """Reduce source code to signatures and docstring summaries."""
        from opencontext_core.context.signature_compression import SignatureCompressor

        language = _language_for_item(item)
        compressor = SignatureCompressor()
        compressed_content = compressor.compress(item.content, language=language)
        compressed_tokens = estimate_tokens(compressed_content)
        metadata = dict(item.metadata)
        metadata["compression"] = {
            "original_token_estimate": item.tokens,
            "compressed_token_estimate": compressed_tokens,
            "strategy": CompressionStrategy.SIGNATURE.value,
            "lossiness": "lossy_signature",
        }
        compressed_item = item.model_copy(
            update={
                "content": compressed_content,
                "tokens": compressed_tokens,
                "metadata": metadata,
            }
        )
        return self._result(item, compressed_item, CompressionStrategy.SIGNATURE, "lossy_signature")

    def _compress_deep_with_fallback(self, item: ContextItem) -> CompressionResult:
        """Attempt deep compression; degrade to compact if unavailable."""
        from opencontext_core.exceptions import BackendUnavailableError

        try:
            from opencontext_core.backends.compression.deep import DeepCompressionBackend

            spans = self.protected_spans.detect(item.content) if self.config.protected_spans else []
            backend = DeepCompressionBackend()
            compressed_content = backend.compress(item.content, spans)
            compressed_tokens = estimate_tokens(compressed_content)
            metadata = dict(item.metadata)
            metadata["compression"] = {
                "original_token_estimate": item.tokens,
                "compressed_token_estimate": compressed_tokens,
                "strategy": CompressionStrategy.DEEP.value,
                "lossiness": "lossy_deep",
            }
            compressed_item = item.model_copy(
                update={
                    "content": compressed_content,
                    "tokens": compressed_tokens,
                    "metadata": metadata,
                }
            )
            return self._result(item, compressed_item, CompressionStrategy.DEEP, "lossy_deep")
        except BackendUnavailableError:
            return self._compress_compact(item)

    def _compress_smart_crusher(self, item: ContextItem) -> CompressionResult:
        """Compress JSON arrays using SmartCrusher."""
        from opencontext_core.compression.smart_crusher import compress as _sc

        compressed_content = _sc(
            item.content,
            min_array_length=self.config.smart_crusher.min_array_length,
            tabular_format=self.config.smart_crusher.tabular_format,
        )
        compressed_tokens = estimate_tokens(compressed_content)
        metadata = dict(item.metadata)
        metadata["compression"] = {
            "original_token_estimate": item.tokens,
            "compressed_token_estimate": compressed_tokens,
            "strategy": CompressionStrategy.SMART_CRUSHER.value,
            "lossiness": "lossy_structural",
        }
        compressed_item = item.model_copy(
            update={
                "content": compressed_content,
                "tokens": compressed_tokens,
                "metadata": metadata,
            }
        )
        return self._result(
            item, compressed_item, CompressionStrategy.SMART_CRUSHER, "lossy_structural"
        )

    def _compress_code_ast(self, item: ContextItem) -> CompressionResult:
        """Compress source code using AST-aware compression."""
        compressor = CodeCompressor()
        language = _language_for_item(item)
        compressed_content = compressor.compress(
            item.content,
            language=language,
            mode=CodeCompressionMode.REVIEW,
            strip_docstrings=self.config.code_compressor.strip_docstrings,
            strip_comments=self.config.code_compressor.strip_comments,
            shorten_locals=self.config.code_compressor.shorten_locals,
            preserve_exports=self.config.code_compressor.preserve_exports,
        )
        compressed_tokens = estimate_tokens(compressed_content)
        metadata = dict(item.metadata)
        metadata["compression"] = {
            "original_token_estimate": item.tokens,
            "compressed_token_estimate": compressed_tokens,
            "strategy": CompressionStrategy.CODE_AST.value,
            "lossiness": "lossy_code_ast",
        }
        compressed_item = item.model_copy(
            update={
                "content": compressed_content,
                "tokens": compressed_tokens,
                "metadata": metadata,
            }
        )
        return self._result(item, compressed_item, CompressionStrategy.CODE_AST, "lossy_code_ast")


def _language_for_item(item: ContextItem) -> str | None:
    """Infer a source language for an item from metadata or its source path."""

    language = item.metadata.get("language")
    if isinstance(language, str) and language:
        return language

    from pathlib import Path

    from opencontext_core.indexing.tree_sitter_parser import LANGUAGE_EXTENSIONS

    suffix = Path(item.source).suffix.lower()
    return LANGUAGE_EXTENSIONS.get(suffix)


def _truncate_to_tokens(content: str, target_tokens: int) -> str:
    target_chars = max(1, target_tokens * 4)
    return content[:target_chars].rstrip()


def _extractive_head_tail(content: str, target_tokens: int) -> str:
    if estimate_tokens(content) <= target_tokens:
        return content
    target_chars = max(1, target_tokens * 4)
    if target_chars < 40:
        return content[:target_chars].rstrip()
    head_chars = target_chars // 2
    tail_chars = target_chars - head_chars - len("\n[... lossy excerpt ...]\n")
    tail_chars = max(0, tail_chars)
    tail = content[-tail_chars:].lstrip() if tail_chars else ""
    return (content[:head_chars].rstrip() + "\n[... lossy excerpt ...]\n" + tail).strip()


def _bullet_facts_placeholder(content: str, target_tokens: int) -> str:
    lines = [line.strip("-* \t") for line in content.splitlines() if line.strip()]
    selected = lines[: max(1, min(len(lines), target_tokens // 6 or 1))]
    if not selected:
        selected = [content[: max(1, target_tokens * 4)].strip()]
    bullets = "\n".join(f"- {line}" for line in selected if line)
    suffix = "\n- Additional details omitted by lossy placeholder compression."
    return (bullets + suffix).strip()


def _clamp_to_budget(item: ContextItem, remaining_tokens: int) -> ContextItem:
    content = _truncate_to_tokens(item.content, remaining_tokens)
    tokens = estimate_tokens(content)
    metadata = dict(item.metadata)
    compression_metadata = dict(metadata.get("compression", {}))
    compression_metadata["budget_clamped"] = True
    compression_metadata["compressed_token_estimate"] = tokens
    compression_metadata["lossiness"] = "lossy_budget_clamp"
    # Lossiness guard: a budget clamp keeps only the head, so any protected span that
    # falls past the cut point is being dropped. Record it instead of silently losing it.
    omitted = _omitted_protected_spans(item.content, kept_chars=len(content))
    if omitted:
        compression_metadata["omitted_protected_spans"] = omitted
        compression_metadata["lossiness"] = "lossy_budget_clamp_protected"
    metadata["compression"] = compression_metadata
    return item.model_copy(update={"content": content, "tokens": tokens, "metadata": metadata})


def _omitted_protected_spans(content: str, kept_chars: int) -> list[dict[str, Any]]:
    """Return protected spans the head clamp dropped OR truncated. Uses ``end >
    kept_chars`` (not ``start >=``) so a span that STRADDLES the cut is recorded too —
    a clamp that turns "must not" into "must" silently inverts the constraint, so the
    half-cut case must surface, not just the fully-dropped one."""

    spans = ProtectedSpanManager().detect(content)
    return [span.model_dump() for span in spans if span.end > kept_chars]
