"""KG-NODES / KG-EDGES: unified graph vocabulary covers the plan's minimum sets.

Pins that every minimum node kind and edge kind from the closure plan is
representable in the unified enums, using the documented nearest-member mapping
where the plan name and the enum member differ (e.g. ``config_key`` -> CONFIG,
``modified_by`` -> CHANGED_BY). Live index emission of the non-code kinds stays
a contract target (KG_CONTEXT_COMPRESSION_CONTRACT "Current -> Target" note).
"""

from __future__ import annotations

from opencontext_core.graph.edges import EdgeKind
from opencontext_core.graph.nodes import NodeKind

# Plan minimum node set -> unified NodeKind member name (nearest documented mapping).
_MIN_NODE_MAPPING = {
    "file": "FILE",
    "symbol": "SYMBOL",
    "test": "TEST",
    "module": "MODULE",
    "command": "COMMAND",
    "config_key": "CONFIG",
    "memory": "MEMORY_BELIEF",
    "decision": "DECISION",
    "artifact": "ARTIFACT",
    "run": "RUN",
    "task": "TASK",
    "spec": "SPEC",
}

# Plan minimum edge set -> unified EdgeKind member name (nearest documented mapping).
_MIN_EDGE_MAPPING = {
    "defines": "DEFINES",
    "calls": "CALLS",
    "imports": "IMPORTS",
    "tests": "TESTS",
    "depends_on": "DEPENDS_ON",
    "documents": "DOCUMENTS",
    "configured_by": "CONFIGURES",
    "produced_by": "PRODUCED_BY",
    "modified_by": "CHANGED_BY",
    "related_to": "RELATED_TO",
    "implements": "IMPLEMENTS",
    "verifies": "VERIFIED_BY",
}


def test_minimum_node_vocabulary_is_representable() -> None:
    """KG-NODES: every plan minimum node kind maps to a unified NodeKind member."""
    members = {member.name for member in NodeKind}
    for plan_kind, member in _MIN_NODE_MAPPING.items():
        assert member in members, f"plan node kind {plan_kind!r} lacks NodeKind.{member}"


def test_spec_node_kind_has_literal_value() -> None:
    """KG-NODES: the `spec` node kind exists with its literal string value."""
    assert NodeKind.SPEC.value == "spec"


def test_minimum_edge_vocabulary_is_representable() -> None:
    """KG-EDGES: every plan minimum edge kind maps to a unified EdgeKind member."""
    members = {member.name for member in EdgeKind}
    for plan_kind, member in _MIN_EDGE_MAPPING.items():
        assert member in members, f"plan edge kind {plan_kind!r} lacks EdgeKind.{member}"


def test_documents_and_related_to_edge_kinds_have_literal_values() -> None:
    """KG-EDGES: the `documents` and `related_to` edge kinds exist with literal values."""
    assert EdgeKind.DOCUMENTS.value == "documents"
    assert EdgeKind.RELATED_TO.value == "related_to"
