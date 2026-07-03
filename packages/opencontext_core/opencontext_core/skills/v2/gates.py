"""Skill v2 gates — AND-combined gate evaluation (commit 011)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class GateOutcome(StrEnum):
    """Per-gate verdict. Skill registration requires an overall PASS."""

    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass(frozen=True)
class GateResult:
    name: str
    outcome: GateOutcome
    detail: str = ""


@dataclass(frozen=True)
class GateReport:
    results: tuple[GateResult, ...]

    @property
    def overall(self) -> GateOutcome:
        """AND-combine: any FAIL wins, otherwise PASS unless nothing ran."""
        if any(r.outcome is GateOutcome.FAIL for r in self.results):
            return GateOutcome.FAIL
        if not self.results:
            return GateOutcome.SKIP
        return GateOutcome.PASS

    @property
    def can_register(self) -> bool:
        return self.overall is GateOutcome.PASS


def evaluate_gates(gates: list[tuple[str, GateOutcome]]) -> GateReport:
    """Evaluate a flat list of ``(name, outcome)`` gates AND-combined."""
    return GateReport(results=tuple(GateResult(name=n, outcome=o) for n, o in gates))


__all__ = ["GateOutcome", "GateReport", "GateResult", "evaluate_gates"]
