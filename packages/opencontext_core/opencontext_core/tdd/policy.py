"""TDDPolicyResolver — map ``OpenSpecConfig.tdd.mode`` to a policy enum.

Three enforcement levels:
  * STRICT — RED-first required (write failing test before any implementation).
  * LITE   — Tests required alongside implementation, no RED-first gate.
  * OFF    — Advisory only; tests optional.
"""

from __future__ import annotations

from enum import Enum

from opencontext_core.openspec.config import OpenSpecConfig


class TDDPolicy(Enum):
    """TDD enforcement level."""

    STRICT = "strict"
    LITE = "lite"
    OFF = "off"


class TDDPolicyResolver:
    """Resolve the active TDD policy from OpenSpecConfig."""

    def resolve(self, config: OpenSpecConfig) -> TDDPolicy:
        return TDDPolicy(config.tdd.mode)