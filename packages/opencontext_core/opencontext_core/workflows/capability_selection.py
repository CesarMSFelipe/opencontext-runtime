"""Capability-aware workflow selection bridge (PR-000.2 CP-011 / CP-CONV).

This is the seam where the L3 Capability Graph becomes an *input* to L6 workflow
selection. It injects the live graph's ready-capability set into the existing
``SelectionPolicy`` and plans graceful gate degradation (a missing test/lint
capability downgrades the gate to advisory and the run continues, never fails).

Layering (doc 58): L6 (Registries). It depends DOWNWARD on the L3 capabilities
package and on the sibling L6 selection/registry modules; the L3 packages never
import this module, so capabilities/profiles stay free of any upward import. The
graph is received by *injection* (constructor arg), matching the convergence
"feed selection via injected ports" rule.

Flag-gating: the bridge is active only when ``runtime.execution_profile`` is a
non-empty string. With the flag empty the bridge passes no capabilities, so
selection behaves exactly as before (instant rollback).
"""

from __future__ import annotations

from opencontext_core.capabilities.constraints import GateDegradation, plan_gate_degradation
from opencontext_core.capabilities.graph import CapabilityGraph
from opencontext_core.workflows.registry import WorkflowRegistry
from opencontext_core.workflows.selection import SelectionDecision, SelectionPolicy


class CapabilityAwareSelection:
    """Feeds a live ``CapabilityGraph`` into ``SelectionPolicy`` (flag-gated)."""

    def __init__(
        self,
        registry: WorkflowRegistry,
        *,
        graph: CapabilityGraph | None = None,
        enabled: bool = True,
    ) -> None:
        self._registry = registry
        self._policy = SelectionPolicy(registry)
        self._enabled = enabled
        # The graph is an injected port. Build a live one lazily only if enabled
        # and none was provided, so the disabled path does no detection work.
        if graph is None and enabled:
            from opencontext_core.capabilities.detector import build_capability_graph

            graph = build_capability_graph(".")
        self._graph = graph if graph is not None else CapabilityGraph()

    @classmethod
    def from_config(
        cls,
        registry: WorkflowRegistry,
        execution_profile: str,
        *,
        graph: CapabilityGraph | None = None,
    ) -> CapabilityAwareSelection:
        """Build the bridge from ``runtime.execution_profile`` (``""`` disables it)."""
        return cls(registry, graph=graph, enabled=bool(execution_profile))

    @property
    def graph(self) -> CapabilityGraph:
        """The capability graph this bridge consults (read-only)."""
        return self._graph

    @property
    def enabled(self) -> bool:
        """Whether capability availability influences selection."""
        return self._enabled

    def available_capabilities(self) -> set[str]:
        """The ready-capability set fed into selection (empty when disabled)."""
        return self._graph.available_ids() if self._enabled else set()

    def select(
        self,
        *,
        intent: str,
        profile: str,
        requested: str | None = None,
    ) -> SelectionDecision:
        """Recommend a workflow, consulting capability availability when enabled.

        When the flag is empty the available set is empty and selection behaves as
        it did before this PR (legacy path).
        """
        return self._policy.select(
            intent=intent,
            profile=profile,
            capabilities=self.available_capabilities(),
            requested=requested,
        )

    def degrade_gates(self, gate_capabilities: dict[str, str]) -> list[GateDegradation]:
        """Plan graceful degradation for gates whose capability is missing (CP-011).

        A gate whose required capability is not ready is downgraded to advisory
        with a recorded, actionable note; the run continues. With the flag empty
        every gate is reported enforced (no degradation), preserving legacy
        behaviour.
        """
        if not self._enabled:
            return [
                GateDegradation(
                    gate=gate,
                    capability_id=capability_id,
                    downgraded=False,
                    note="execution profile disabled; gate enforced as configured.",
                )
                for gate, capability_id in gate_capabilities.items()
            ]
        return plan_gate_degradation(self._graph, gate_capabilities)
