"""PR-012 ProviderSpec + CapabilityModel — capability-based provider contract.

Seven capability flags (REQ-pg-v2-001): structured_output | tool_use |
long_context | reasoning | streaming | vision | embeddings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CAPABILITY_FLAGS: tuple[str, ...] = (
    "structured_output",
    "tool_use",
    "long_context",
    "reasoning",
    "streaming",
    "vision",
    "embeddings",
)


@dataclass
class CapabilityModel:
    """Seven capability flags. Defaults: all False (deny-by-default)."""

    structured_output: bool = False
    tool_use: bool = False
    long_context: bool = False
    reasoning: bool = False
    streaming: bool = False
    vision: bool = False
    embeddings: bool = False

    def has(self, name: str) -> bool:
        return bool(getattr(self, name, False))

    def as_dict(self) -> dict[str, bool]:
        return {f: getattr(self, f) for f in CAPABILITY_FLAGS}


@dataclass
class ProviderSpec:
    """A provider advertisement: identity, capabilities, cost, latency, quality."""

    provider_id: str
    display_name: str = ""
    capabilities: CapabilityModel = field(default_factory=CapabilityModel)
    cost_input_per_1k: float = 0.0
    cost_output_per_1k: float = 0.0
    max_context_tokens: int = 4096
    avg_latency_ms: int = 100
    quality_score: float = 0.5
    local_only: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "display_name": self.display_name or self.provider_id,
            "capabilities": self.capabilities.as_dict(),
            "cost_input_per_1k": self.cost_input_per_1k,
            "cost_output_per_1k": self.cost_output_per_1k,
            "max_context_tokens": self.max_context_tokens,
            "avg_latency_ms": self.avg_latency_ms,
            "quality_score": self.quality_score,
            "local_only": self.local_only,
        }
