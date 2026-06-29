"""Build the live Capability Graph by REUSING existing detection (CP-004..CP-006).

The detector does not reimplement detection. It folds three existing sources into
typed ``CapabilityNode``s:

* ``sdd_runtime.detect_test_capabilities`` — test/lint/type tooling (CP-001).
* ``providers.detect.detect_provider`` — the ambient LLM provider.
* ``agent_installer.AgentInstaller.detect_installed_agents`` — agent clients
  (the same detection ``doctor/component_checks.py`` uses).

It then wires dependency edges (e.g. ``strict_harness -> pytest``) so the graph
exposes readiness, not just a flat list.

Layering (doc 58): L3. It reads lower/leaf detection utilities only and is never
imported by them; upper layers receive the built graph by injection.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.capabilities.graph import CapabilityGraph, CapabilityKind, CapabilityNode

# Synthetic capability ids the graph derives from raw tooling facts. Kept as
# constants so PR-003 (required_capabilities) and the Brain reference one id scheme.
STRICT_HARNESS = "strict_harness"

# Map a detected TestCapability.scope onto a CapabilityNode.kind.
_SCOPE_KIND: dict[str, CapabilityKind] = {
    "focused": "test",
    "broad": "test",
    "e2e": "test",
    "lint": "lint",
    "type": "type",
}


def _kind_for_scope(scope: str) -> CapabilityKind:
    return _SCOPE_KIND.get(scope, "test")


def build_capability_graph(root: Path | str = ".") -> CapabilityGraph:
    """Build the live ``CapabilityGraph`` for ``root`` from existing detection.

    Never raises on a missing/odd environment: detection sources that fail are
    skipped so ``doctor`` and a first run always get a usable graph.
    """
    nodes: list[CapabilityNode] = []

    nodes.extend(_tooling_nodes(root))
    provider_node = _provider_node()
    if provider_node is not None:
        nodes.append(provider_node)
    nodes.extend(_agent_nodes(root))
    nodes.append(_strict_harness_node())

    return CapabilityGraph(nodes=nodes)


def _tooling_nodes(root: Path | str) -> list[CapabilityNode]:
    """Lift ``detect_test_capabilities`` records into typed nodes (no new detection)."""
    from opencontext_core.sdd_runtime import detect_test_capabilities

    nodes: list[CapabilityNode] = []
    try:
        for cap in detect_test_capabilities(root):
            nodes.append(
                CapabilityNode(
                    id=cap.name,
                    kind=_kind_for_scope(cap.scope),
                    available=True,
                    evidence=cap.evidence,
                )
            )
    except Exception:
        return []
    return nodes


def _provider_node() -> CapabilityNode | None:
    """Fold ambient provider detection into a provider capability node."""
    try:
        from opencontext_core.providers.detect import detect_provider

        detected = detect_provider()
    except Exception:
        return None
    # A "fallback"/mock provider means no real provider is available.
    available = detected.source != "fallback"
    return CapabilityNode(
        id=f"provider.{detected.name}",
        kind="provider",
        available=available,
        evidence=f"source={detected.source}; model={detected.model}",
    )


def _agent_nodes(root: Path | str) -> list[CapabilityNode]:
    """Reuse the agent installer's detection (same source as doctor component checks)."""
    try:
        from opencontext_core.agent_installer import AgentInstaller

        installer = AgentInstaller(root)
        detected = installer.detect_installed_agents()
    except Exception:
        return []
    return [
        CapabilityNode(
            id=f"agent.{agent.value}",
            kind="agent",
            available=True,
            evidence="agent installer detection",
        )
        for agent in detected
    ]


def _strict_harness_node() -> CapabilityNode:
    """A strict harness capability that depends on a focused test runner (CP-005).

    The node itself is "available" (the harness feature exists), but it is only
    *ready* when its dependency (``pytest``) is ready — so ``is_ready`` /
    ``unmet_dependencies`` surface a missing test runner.
    """
    return CapabilityNode(
        id=STRICT_HARNESS,
        kind="harness",
        available=True,
        evidence="depends on a focused test runner",
        depends_on=["pytest"],
    )
