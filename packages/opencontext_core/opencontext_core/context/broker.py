"""Per-phase token budget tracking for the agentic runtime (slice 4).

Tracks how many tokens each phase (design, apply, verify, ...) consumes from
the run-level token budget. Pure bookkeeping — does not replace
``TokenBudgetManager`` (which selects items within a fixed budget) or
``EconomyStrategy`` (which decides caps per mode/phase).
"""

from __future__ import annotations


class ContextBudgetBroker:
    """Records token allocations per phase and reports remaining budget."""

    def __init__(self, total_budget: int) -> None:
        self._total = total_budget
        self._allocations: dict[str, int] = {}

    def allocate(self, phase: str, tokens: int) -> int:
        """Record *tokens* spent in *phase*; return remaining budget (>=0)."""
        self._allocations[phase] = self._allocations.get(phase, 0) + tokens
        return max(0, self._total - self.total_allocated())

    def remaining(self) -> int:
        return max(0, self._total - self.total_allocated())

    def total_allocated(self) -> int:
        return sum(self._allocations.values())

    def allocations(self) -> dict[str, int]:
        return dict(self._allocations)

    def over_budget(self) -> bool:
        return self.total_allocated() > self._total


if __name__ == "__main__":
    # Self-check: minimal scenarios from the spec.
    b = ContextBudgetBroker(10_000)
    assert b.allocate("design", 4_000) == 6_000
    assert b.remaining() == 6_000
    assert b.allocate("apply", 3_000) == 3_000
    assert b.over_budget() is False
    b2 = ContextBudgetBroker(1_000)
    assert b2.allocate("design", 1_500) == 0
    assert b2.over_budget() is True
    print("context/broker.py self-check passed.")