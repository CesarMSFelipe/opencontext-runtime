"""PR-012 FallbackReceipt — record fallback triggers (REQ-pg-v2-003)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class FallbackReason(str, Enum):
    timeout = "timeout"
    quota = "quota"
    error = "error"
    unsupported_capability = "unsupported_capability"


@dataclass
class FallbackReceipt:
    """A single failure that triggered fallback to the next provider."""

    provider_id: str
    reason: FallbackReason
    error_message: str
    attempted_at: str
    next_provider: str | None = None


@dataclass
class FallbackChain:
    """Ordered list of provider ids used as fallback candidates."""

    candidates: list[str] = field(default_factory=list)

    def record_failure(
        self,
        *,
        provider_id: str,
        reason: FallbackReason,
        error_message: str,
        attempted_at: str,
    ) -> FallbackReceipt:
        idx = self.candidates.index(provider_id) if provider_id in self.candidates else -1
        next_provider = self.candidates[idx + 1] if 0 <= idx + 1 < len(self.candidates) else None
        return FallbackReceipt(
            provider_id=provider_id,
            reason=reason,
            error_message=error_message,
            attempted_at=attempted_at,
            next_provider=next_provider,
        )