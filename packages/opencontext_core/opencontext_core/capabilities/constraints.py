"""Capability constraints and graceful degradation (CP-005, CP-011).

A ``CapabilityConstraint`` declares that a capability requires others to be ready
and carries an actionable message used when the requirement is unmet. The gate
degradation helper (``plan_gate_degradation``) turns a missing test/lint
capability into a *downgrade-to-advisory* decision with a recorded note, instead
of a hard failure — the convergence "first run must work" guarantee (doc §9.1).

Layering (doc 58): L3. Imports only ``pydantic`` and the sibling L3 graph module.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.capabilities.graph import CapabilityGraph


class CapabilityConstraint(BaseModel):
    """A requirement that a capability depends on other capabilities being ready."""

    model_config = ConfigDict(extra="forbid")

    capability_id: str = Field(description="The capability the constraint applies to.")
    requires: list[str] = Field(
        default_factory=list, description="Capability ids that must be ready."
    )
    message: str = Field(
        default="", description="Actionable guidance surfaced when the constraint is unmet."
    )

    def evaluate(self, graph: CapabilityGraph) -> tuple[bool, list[str]]:
        """Return ``(satisfied, missing)`` for this constraint against ``graph``.

        ``satisfied`` is True only when every required capability is ready;
        ``missing`` lists the required ids that are not ready (absent or with an
        unmet dependency of their own).
        """
        missing = [cap for cap in self.requires if not graph.is_ready(cap)]
        return (not missing, missing)


class GateDegradation(BaseModel):
    """A single gate's degradation decision under the live capability graph."""

    model_config = ConfigDict(extra="forbid")

    gate: str = Field(description="Gate id (e.g. 'lint', 'tests').")
    capability_id: str = Field(description="Capability the gate requires.")
    downgraded: bool = Field(
        description="True when the capability is missing and the gate runs advisory."
    )
    note: str = Field(default="", description="Actionable, recorded reason for the decision.")


def plan_gate_degradation(
    graph: CapabilityGraph, gate_capabilities: dict[str, str]
) -> list[GateDegradation]:
    """Plan graceful degradation for gates whose required capability is missing.

    ``gate_capabilities`` maps a gate id to the capability id it needs (e.g.
    ``{"lint": "ruff", "tests": "pytest"}``). For each gate whose capability is
    not ready, the gate is downgraded to advisory with an actionable note; gates
    whose capability is ready are recorded as not downgraded. The run continues
    in both cases — a missing linter never fails the workflow (CP-011).
    """
    plan: list[GateDegradation] = []
    for gate, capability_id in gate_capabilities.items():
        ready = graph.is_ready(capability_id)
        if ready:
            plan.append(
                GateDegradation(
                    gate=gate,
                    capability_id=capability_id,
                    downgraded=False,
                    note=f"{capability_id} available; '{gate}' gate enforced.",
                )
            )
        else:
            plan.append(
                GateDegradation(
                    gate=gate,
                    capability_id=capability_id,
                    downgraded=True,
                    note=(
                        f"{capability_id} not detected; '{gate}' gate downgraded to "
                        f"advisory and the run continues. Install {capability_id} to "
                        f"enforce this gate."
                    ),
                )
            )
    return plan
