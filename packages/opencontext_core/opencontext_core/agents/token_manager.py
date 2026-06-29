"""Token budget management for agents."""

from dataclasses import dataclass
from typing import Any


# DEPRECATED(2.0): dead agent SDK helper (used only by the deprecated AgentOrchestrator;
# not the live models.context.TokenBudget). Remove in 2.0.
@dataclass
class TokenBudget:
    """Manages token allocation and tracking."""

    max_per_query: int = 6500
    max_total: int = 50000
    context_ratio: float = 0.7  # proportion for context vs output

    total_used: int = 0
    query_count: int = 0

    @property
    def remaining_total(self) -> int:
        """Get remaining tokens from total budget."""
        return max(0, self.max_total - self.total_used)

    @property
    def remaining_per_query(self) -> int:
        """Get remaining tokens for next query."""
        return min(self.max_per_query, self.remaining_total)

    @property
    def is_exhausted(self) -> bool:
        """Check if budget is exhausted."""
        return self.total_used >= self.max_total

    def allocate_for_query(self, tokens_needed: int) -> bool:
        """Check if tokens can be allocated for query.

        Args:
            tokens_needed: Tokens needed for query

        Returns:
            True if allocation is possible, False otherwise
        """
        if self.is_exhausted:
            return False
        if tokens_needed > self.remaining_per_query:
            return False
        return True

    def record_usage(self, tokens_used: int) -> None:
        """Record token usage.

        Args:
            tokens_used: Tokens consumed in query
        """
        self.total_used += tokens_used
        self.query_count += 1

    @property
    def utilization_percent(self) -> float:
        """Get budget utilization as percentage."""
        if self.max_total == 0:
            return 0.0
        return (self.total_used / self.max_total) * 100

    def reset(self) -> None:
        """Reset token tracking (but keep limits)."""
        self.total_used = 0
        self.query_count = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "max_per_query": self.max_per_query,
            "max_total": self.max_total,
            "context_ratio": self.context_ratio,
            "total_used": self.total_used,
            "query_count": self.query_count,
            "remaining_total": self.remaining_total,
            "utilization_percent": self.utilization_percent,
        }
