"""ContextReceipt — unified receipt model composing agentic, substrate, and savings reports.

Re-exports ``AgenticReceipt`` and ``ContextSubstrateReport`` from their authoritative
modules and introduces ``ContextReceipt`` as a composition wrapper.

``ContextReceipt.passed_quality_gate()`` returns ``True`` when
``estimated_savings_ratio >= 0.0`` and ``degraded=False`` on the savings report.
"""

from __future__ import annotations

from dataclasses import dataclass

from opencontext_core.agentic.context_substrate import (
    ContextSubstrateBuilder as ContextSubstrateBuilder,
)
from opencontext_core.agentic.context_substrate import (
    ContextSubstrateReport as ContextSubstrateReport,
)

# Re-exports — preserves existing import surfaces.
from opencontext_core.agentic.receipt import AgenticReceipt as AgenticReceipt
from opencontext_core.context.savings import (
    ContextSavingsReport as ContextSavingsReport,
)


@dataclass
class ContextReceipt:
    """Unified receipt composing agentic, substrate, and savings sub-reports."""

    agentic: AgenticReceipt | None = None
    substrate: ContextSubstrateReport | None = None
    savings: ContextSavingsReport | None = None

    def passed_quality_gate(self) -> bool:
        """Return True when the savings report is real (not degraded) and ratio >= 0.0.

        A degraded report (ContextPackBuilder absent) always fails the gate.
        A non-degraded report with ratio = 0.0 passes (zero savings is valid).
        """
        if self.savings is None:
            return False
        if self.savings.degraded:
            return False
        return self.savings.estimated_savings_ratio >= 0.0

    @classmethod
    def build_degraded(cls, reason: str = "") -> ContextReceipt:
        """Build a receipt with a degraded savings report."""
        savings = ContextSavingsReport(
            degraded=True,
            warning=reason or "ContextPackBuilder unavailable; savings not measured.",
            tokens_saved=0,
            tokens_without_pack=0,
            estimated_savings_ratio=0.0,
        )
        return cls(savings=savings)
