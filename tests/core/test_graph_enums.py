"""Tests for graph NodeKind and EdgeKind enumerations."""

from opencontext_core.graph.nodes import NodeKind
from opencontext_core.graph.edges import EdgeKind


def test_all_node_kinds_present():
    expected = {
        "CODE_SYMBOL", "FILE", "ROUTE", "SERVICE", "CONFIG", "TEST",
        "MEMORY_BELIEF", "MEMORY_DECISION", "FAILURE_PATTERN",
        "VALIDATION_GATE", "TRACE_RUN", "TRACE_OMISSION", "TRACE_FAILURE",
    }
    actual = {k.name for k in NodeKind}
    assert expected == actual


def test_all_edge_kinds_present():
    expected = {
        "CALLS", "IMPORTS", "IMPLEMENTS", "EXTENDS", "ROUTES_TO", "TESTS",
        "BROKE_BEFORE", "FIXED_BY", "MENTIONED_IN", "APPLIES_TO",
        "JUSTIFIES_RULE", "SUPERSEDES", "CONTRADICTS", "REINFORCES",
        "OMITTED", "SELECTED", "VALIDATED_BY",
    }
    actual = {k.name for k in EdgeKind}
    assert expected == actual


def test_strenum_string_values():
    assert NodeKind.CODE_SYMBOL == "code_symbol"
    assert EdgeKind.CALLS == "calls"


def test_memory_trace_kinds_distinct_from_code():
    code_kinds = {NodeKind.CODE_SYMBOL, NodeKind.FILE, NodeKind.ROUTE, NodeKind.SERVICE, NodeKind.CONFIG, NodeKind.TEST}
    memory_kinds = {NodeKind.MEMORY_BELIEF, NodeKind.MEMORY_DECISION, NodeKind.FAILURE_PATTERN}
    trace_kinds = {NodeKind.TRACE_RUN, NodeKind.TRACE_OMISSION, NodeKind.TRACE_FAILURE}
    assert code_kinds.isdisjoint(memory_kinds)
    assert code_kinds.isdisjoint(trace_kinds)
    assert memory_kinds.isdisjoint(trace_kinds)
