"""OpenContext graph v2 (PR-008 / SPEC §3.2 graph).

Re-exports the v2 KG primitives (schema, evidence, planner, retriever,
freshness, confidence). Leaf boundary: the graph v2 module imports only
its own siblings and the typed cache layer; it does not import the
context, memory, or learning v2 modules — enforced by the architecture
coverage gate (``opencontext.architecture.coverage``).
"""

from __future__ import annotations

__capability__ = "graph.v2"
