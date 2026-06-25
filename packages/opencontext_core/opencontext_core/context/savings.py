"""ContextSavingsReport — honest, degradation-friendly token-savings accounting.

If ``ContextPackBuilder`` is unavailable we MUST NOT fabricate savings metrics.
Instead ``ContextSavingsReport.build()`` returns a report with
``degraded=True`` and a labelled ``warning`` field so downstream tooling
can surface the absence rather than trusting invented numbers.

When the builder IS available, real token counts are measured via the
word-count x 1.3 approximation (no external dependencies required).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextSavingsReport:
    """Token-savings accounting with explicit degradation signalling."""

    degraded: bool
    warning: str
    tokens_saved: int
    tokens_without_pack: int
    estimated_savings_ratio: float = 0.0

    @classmethod
    def build(cls, content: str | None = None) -> ContextSavingsReport:
        """Build a savings report for the current run.

        When ``ContextPackBuilder`` is absent the report degrades: zeroed
        metrics, ``degraded=True``, and a labelled warning. Never raises.

        When *content* is supplied and the builder is available, real token
        counts are estimated via ``len(content.split()) * 1.3``.
        """
        try:
            from opencontext_core.context.packing import ContextPackBuilder
        except ImportError:
            return cls(
                degraded=True,
                warning="ContextPackBuilder unavailable; savings not measured.",
                tokens_saved=0,
                tokens_without_pack=0,
                estimated_savings_ratio=0.0,
            )

        if ContextPackBuilder is None:
            return cls(
                degraded=True,
                warning="ContextPackBuilder unavailable; savings not measured.",
                tokens_saved=0,
                tokens_without_pack=0,
                estimated_savings_ratio=0.0,
            )

        # Builder is available.
        if content is not None:
            # NOTE: Approximate tokens via word-count x 1.3 (no tiktoken dependency).
            baseline_tokens = int(len(content.split()) * 1.3)
            # Without a live pack we cannot compute real selected_tokens.
            # Report what we measured; ratio = 0.0 (no pack built yet).
            return cls(
                degraded=False,
                warning="",
                tokens_saved=0,
                tokens_without_pack=baseline_tokens,
                estimated_savings_ratio=0.0,
            )

        # No run snapshot available to diff against.
        return cls(
            degraded=True,
            warning="No run snapshot available; savings not measured.",
            tokens_saved=0,
            tokens_without_pack=0,
            estimated_savings_ratio=0.0,
        )


if __name__ == "__main__":
    # Self-check: graceful degradation path.
    report = ContextSavingsReport.build()
    assert report.degraded is True
    assert report.warning
    assert report.tokens_saved == 0
    assert report.estimated_savings_ratio == 0.0
    print("context/savings.py self-check passed.")
