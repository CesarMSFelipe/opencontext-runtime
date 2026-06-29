"""Tests for graph NodeKind and EdgeKind enumerations."""

from opencontext_core.graph.edges import EdgeKind
from opencontext_core.graph.nodes import NodeKind

# PR-008 KG v2 expanded the unified enums additively (OC-KG-001 §6-7). The original
# unified-graph kinds MUST all survive (no rename/removal); the book's KgNodeType /
# KgEdgeType vocabulary MUST now be representable. This test asserts both, instead of
# the pre-v2 exact-cardinality equality it used to make.
_LEGACY_NODE_KINDS = {
    "CODE_SYMBOL",
    "FILE",
    "ROUTE",
    "SERVICE",
    "CONFIG",
    "TEST",
    "MEMORY_BELIEF",
    "MEMORY_DECISION",
    "FAILURE_PATTERN",
    "VALIDATION_GATE",
    "TRACE_RUN",
    "TRACE_OMISSION",
    "TRACE_FAILURE",
}
_LEGACY_EDGE_KINDS = {
    "CALLS",
    "IMPORTS",
    "IMPLEMENTS",
    "EXTENDS",
    "ROUTES_TO",
    "TESTS",
    "BROKE_BEFORE",
    "FIXED_BY",
    "MENTIONED_IN",
    "APPLIES_TO",
    "JUSTIFIES_RULE",
    "SUPERSEDES",
    "CONTRADICTS",
    "REINFORCES",
    "OMITTED",
    "SELECTED",
    "VALIDATED_BY",
}
# OC-KG-001 §6 KgNodeType (26) / §7 KgEdgeType (21) book vocabularies.
_BOOK_NODE_KINDS = {
    "FILE", "DIRECTORY", "PACKAGE", "MODULE", "SYMBOL", "FUNCTION", "METHOD",
    "CLASS", "INTERFACE", "TEST", "COMMAND", "CONFIG", "SERVICE", "ROUTE",
    "PLUGIN", "OWNER", "TEAM", "DECISION", "CONSTRAINT", "FAILURE_PATTERN",
    "SESSION", "RUN", "ARTIFACT", "SKILL", "PERSONA", "HARNESS",
}
_BOOK_EDGE_KINDS = {
    "CONTAINS", "DEFINES", "IMPORTS", "CALLS", "REFERENCES", "TESTS", "COVERS",
    "OWNS", "DEPENDS_ON", "IMPLEMENTS", "EXTENDS", "CONFIGURES", "CHANGED_BY",
    "PRODUCED_BY", "SUPERSEDES", "CONTRADICTS", "SUPPORTS", "FAILED_WITH",
    "FIXED_BY", "USED_SKILL", "USED_HARNESS",
}


def test_all_node_kinds_present():
    actual = {k.name for k in NodeKind}
    # Additive: every legacy kind survives.
    assert _LEGACY_NODE_KINDS <= actual
    # KG v2: every book KgNodeType kind is representable; toward 40 total.
    assert _BOOK_NODE_KINDS <= actual
    assert len(actual) >= 40


def test_all_edge_kinds_present():
    actual = {k.name for k in EdgeKind}
    assert _LEGACY_EDGE_KINDS <= actual
    assert _BOOK_EDGE_KINDS <= actual
    assert len(actual) >= 20


def test_strenum_string_values():
    assert NodeKind.CODE_SYMBOL == "code_symbol"
    assert EdgeKind.CALLS == "calls"


def test_memory_trace_kinds_distinct_from_code():
    code_kinds = {
        NodeKind.CODE_SYMBOL,
        NodeKind.FILE,
        NodeKind.ROUTE,
        NodeKind.SERVICE,
        NodeKind.CONFIG,
        NodeKind.TEST,
    }
    memory_kinds = {NodeKind.MEMORY_BELIEF, NodeKind.MEMORY_DECISION, NodeKind.FAILURE_PATTERN}
    trace_kinds = {NodeKind.TRACE_RUN, NodeKind.TRACE_OMISSION, NodeKind.TRACE_FAILURE}
    assert code_kinds.isdisjoint(memory_kinds)
    assert code_kinds.isdisjoint(trace_kinds)
    assert memory_kinds.isdisjoint(trace_kinds)
