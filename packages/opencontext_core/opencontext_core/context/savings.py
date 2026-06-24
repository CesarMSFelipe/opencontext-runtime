"""ContextSavingsReport — honest, degradation-friendly token-savings accounting.

If ``ContextPackBuilder`` is unavailable we MUST NOT fabricate savings metrics.
Instead ``ContextSavingsReport.build()`` returns a report with
``degraded=True`` and a labelled ``warning`` field, so downstream tooling
can surface the absence rather than trusting invented numbers.
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

    @classmethod
    def build(cls) -> ContextSavingsReport:
        """Build a savings report for the current run.

        When ``ContextPackBuilder`` is absent the report degrades: zeroed
        metrics, ``degraded=True``, and a labelled warning. Never raises.
        """
        try:
            from opencontext_core.context.packing import ContextPackBuilder
        except ImportError:
            return cls(
                degraded=True,
                warning="ContextPackBuilder unavailable; savings not measured.",
                tokens_saved=0,
                tokens_without_pack=0,
            )

        if ContextPackBuilder is None:
            return cls(
                degraded=True,
                warning="ContextPackBuilder unavailable; savings not measured.",
                tokens_saved=0,
                tokens_without_pack=0,
            )

        # No completed run snapshot is available to diff against — degrade
        # honestly rather than fabricate a comparison.
        return cls(
            degraded=True,
            warning="No run snapshot available; savings not measured.",
            tokens_saved=0,
            tokens_without_pack=0,
        )


if __name__ == "__main__":
    # Self-check: graceful degradation path.
    report = ContextSavingsReport.build()
    assert report.degraded is True
    assert report.warning
    assert report.tokens_saved == 0
    print("context/savings.py self-check passed.")