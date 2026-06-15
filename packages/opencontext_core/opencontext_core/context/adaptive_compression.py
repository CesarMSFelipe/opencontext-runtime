"""Deterministic adaptive compression policy."""

from __future__ import annotations

from opencontext_core.models.context import (
    CompressionDecision,
    CompressionStrategy,
    ContextPriority,
)


class AdaptiveCompressionController:
    """Chooses compression strategy from risk, pressure, confidence, and priority."""

    def decide(
        self,
        *,
        query_complexity: float,
        retrieval_confidence: float,
        task_risk: str,
        source_type: str,
        token_pressure: float,
        priority: ContextPriority,
        prefer_signature_for_code: bool = False,
    ) -> CompressionDecision:
        """Return a deterministic compression decision.

        When ``prefer_signature_for_code`` is set, low-priority code sources use
        signature-level compression instead of extractive head/tail. The flag
        defaults off so the standard policy is unchanged.
        """

        del query_complexity
        normalized_risk = task_risk.lower()
        if normalized_risk in {"high", "legal", "medical", "security"}:
            return CompressionDecision(
                strategy=CompressionStrategy.NONE,
                max_ratio=1.0,
                allow_lossy=False,
                reason="high_risk_task_preserves_context",
            )
        if priority in {ContextPriority.P0, ContextPriority.P1}:
            return CompressionDecision(
                strategy=CompressionStrategy.NONE,
                max_ratio=1.0,
                allow_lossy=False,
                reason="required_priority_preserves_context",
            )
        if token_pressure < 0.2:
            return CompressionDecision(
                strategy=CompressionStrategy.NONE,
                max_ratio=1.0,
                allow_lossy=False,
                reason="low_token_pressure",
            )
        if source_type in {"code", "file", "symbol"} and priority <= ContextPriority.P3:
            if prefer_signature_for_code:
                return CompressionDecision(
                    strategy=CompressionStrategy.SIGNATURE,
                    max_ratio=0.75 if retrieval_confidence < 0.5 else 0.6,
                    allow_lossy=True,
                    reason="code_uses_signature_compression",
                )
            return CompressionDecision(
                strategy=CompressionStrategy.EXTRACTIVE_HEAD_TAIL,
                max_ratio=0.75 if retrieval_confidence < 0.5 else 0.6,
                allow_lossy=True,
                reason="code_uses_extractive_compression",
            )
        if retrieval_confidence < 0.5:
            return CompressionDecision(
                strategy=CompressionStrategy.EXTRACTIVE_HEAD_TAIL,
                max_ratio=0.8,
                allow_lossy=True,
                reason="low_retrieval_confidence_preserves_more_context",
            )
        if token_pressure >= 0.75 and priority in {ContextPriority.P4, ContextPriority.P5}:
            return CompressionDecision(
                strategy=CompressionStrategy.TRUNCATE,
                max_ratio=0.35,
                allow_lossy=True,
                reason="high_pressure_low_priority_allows_stronger_compression",
            )
        return CompressionDecision(
            strategy=CompressionStrategy.EXTRACTIVE_HEAD_TAIL,
            max_ratio=0.6,
            allow_lossy=True,
            reason="default_extractive_policy",
        )
