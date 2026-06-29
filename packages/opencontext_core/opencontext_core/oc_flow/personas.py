"""OC Flow node -> persona mapping (PR-007, FLOW-11, book doc 04 §15).

The personas themselves (incl. ``oc-diagnostician``) already live in the shared
persona registry (``personas/__init__.py``); OC Flow only declares which persona
drives each of its nodes. ``PHASE_PERSONAS`` (SDD) is untouched — this is the
operational-workflow equivalent.

Layering (doc 58): L9 importing the L6 persona package downward.
"""

from __future__ import annotations

from opencontext_core.personas import Persona, get_persona

# Book §15 — the default OC Flow node -> persona mapping. ``init`` and ``escalation``
# share the orchestrator; ``completed`` is a runtime terminal (orchestrator).
OC_FLOW_NODE_PERSONAS: dict[str, str] = {
    "init": "oc-orchestrator",
    "gather_context": "oc-context-engineer",
    "plan": "oc-architect",
    "mutate": "oc-builder",
    "local_inspection": "oc-harness-verifier",
    "diagnose": "oc-diagnostician",
    "escalation": "oc-orchestrator",
    "consolidation": "oc-archivist",
    "completed": "oc-orchestrator",
}


def persona_id_for_oc_flow_node(node: str) -> str | None:
    """Return the persona id mapped to ``node`` (or ``None`` if unmapped)."""
    return OC_FLOW_NODE_PERSONAS.get(node)


def persona_for_oc_flow_node(node: str) -> Persona | None:
    """Resolve the :class:`Persona` driving ``node`` (FLOW-11)."""
    persona_id = OC_FLOW_NODE_PERSONAS.get(node)
    return get_persona(persona_id) if persona_id else None
