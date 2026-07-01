"""Gated promotion to memory (PR-000.4 / SPEC DL-003 / DL-009).

The honesty gate (OC-FINAL §9.8, doc 44 Risks 4 + 11): a learning candidate
is promotable to the memory harness ONLY when ``quality_score >= 80`` AND
the supplied evidence carries a non-empty ``benchmark_id``. Either gate
failing raises :class:`MemoryPromotionRejected`; the candidate is never
written to memory in either case.

This module owns the gate contract; persistence is the PR-009
``MemoryHarness`` destination (``destination="memory_harness"``). It does
NOT touch KG, Cache, or any Brain-adjacent port (doc 59 §6).
"""

from __future__ import annotations

from dataclasses import dataclass

_QUALITY_THRESHOLD = 80


class MemoryPromotionRejected(Exception):
    """Raised when a candidate fails either the quality or the benchmark gate."""


@dataclass(frozen=True)
class PromotionResult:
    """The outcome of a successful promotion."""

    candidate_id: str
    promoted: bool = True
    destination: str = "memory_harness"
    benchmark_id: str = ""
    quality_score: int = 0


class PromotionGate:
    """Block promotion unless ``quality_score >= 80`` AND ``benchmark_id`` present.

    The gate is structural: both predicates are required. There is no skip
    flag and no "fast-track" override — improvement must be *measured*
    ([[oc-value-eval-2026-06]]).
    """

    def __init__(
        self,
        *,
        quality_threshold: int = _QUALITY_THRESHOLD,
        destination: str = "memory_harness",
    ) -> None:
        if quality_threshold <= 0:
            raise ValueError("quality_threshold must be positive")
        self._threshold = quality_threshold
        self.destination = destination

    def promote(self, candidate: Any, *, evidence: dict | None) -> PromotionResult:
        """Promote *candidate* to the destination memory harness.

        ``candidate`` must expose ``candidate_id`` (str) and ``quality_score``
        (int|float). ``evidence`` must contain a non-empty ``benchmark_id``.

        Raises :class:`MemoryPromotionRejected` if either gate fails.
        """
        candidate_id = str(getattr(candidate, "candidate_id", "") or "")
        quality = float(getattr(candidate, "quality_score", 0) or 0)
        ev = evidence or {}

        if quality < self._threshold:
            raise MemoryPromotionRejected(
                f"quality_below_threshold: got {quality}, "
                f"need >= {self._threshold}"
            )

        benchmark_id = ev.get("benchmark_id")
        if not benchmark_id or not str(benchmark_id).strip():
            raise MemoryPromotionRejected(
                "benchmark_id_missing in evidence: improvement must be measured, "
                "not self-asserted (doc 44 Risk 11)"
            )

        return PromotionResult(
            candidate_id=candidate_id,
            destination=self.destination,
            benchmark_id=str(benchmark_id),
            quality_score=int(quality),
        )


__all__ = [
    "MemoryPromotionRejected",
    "PromotionGate",
    "PromotionResult",
]
