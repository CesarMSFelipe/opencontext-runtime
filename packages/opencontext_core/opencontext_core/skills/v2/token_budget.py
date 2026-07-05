"""Skill v2 token budget — per-run cap with refused-spend sentinel."""

from __future__ import annotations

from dataclasses import dataclass

BUDGET_EXCEEDED = "BUDGET_EXCEEDED"


@dataclass(frozen=True)
class SpendOutcome:
    accepted: bool
    reason: str = ""


class TokenBudget:
    """A per-run token budget with a hard cap.

    ``try_spend`` returns a :class:`SpendOutcome`; on rejection ``used`` is
    left unchanged so the caller can see what was previously committed.
    """

    __slots__ = ("_cap", "_used")

    def __init__(self, cap: int, used: int = 0) -> None:
        if cap < 0 or used < 0:
            raise ValueError("cap and used must be non-negative")
        self._cap = int(cap)
        self._used = int(used)

    @property
    def cap(self) -> int:
        return self._cap

    @property
    def used(self) -> int:
        return self._used

    @property
    def remaining(self) -> int:
        return max(0, self._cap - self._used)

    def try_spend(self, amount: int) -> SpendOutcome:
        if amount < 0:
            raise ValueError("spend amount must be non-negative")
        if self._used + amount > self._cap:
            return SpendOutcome(accepted=False, reason=BUDGET_EXCEEDED)
        self._used += amount
        return SpendOutcome(accepted=True)


__all__ = ["BUDGET_EXCEEDED", "SpendOutcome", "TokenBudget"]
