"""PolicySimulator — preview policy decisions without executing tools."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from opencontext_core.tools.policy import ToolPermissionPolicy


class SimulatedDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    decision: Literal["allowed", "denied"]
    reason: str


class PolicySimulator:
    """Simulate ToolPermissionPolicy decisions without side-effects."""

    def __init__(self, policy: ToolPermissionPolicy) -> None:
        self.policy = policy

    def simulate(self, tool_names: list[str]) -> list[SimulatedDecision]:
        results: list[SimulatedDecision] = []
        for name in tool_names:
            if self.policy.allows(name):
                results.append(
                    SimulatedDecision(tool=name, decision="allowed", reason="allowlisted")
                )
            else:
                in_denied = name in self.policy.denied_tools
                results.append(
                    SimulatedDecision(
                        tool=name,
                        decision="denied",
                        reason="explicit_deny" if in_denied else "not_allowlisted",
                    )
                )
        return results
