"""WR1 / SDD1 / YAML1 — registry, built-in SDD, and YAML template tests."""

from __future__ import annotations

import pytest

from opencontext_core.agents.sdd_orchestrator import (
    PHASE_DEPENDENCIES,
    PHASE_ORDER,
    sdd_definition_source,
)
from opencontext_core.workflows import (
    WorkflowDefinition,
    WorkflowEdgeDefinition,
    WorkflowNodeDefinition,
    WorkflowNotFound,
    WorkflowRegistry,
    load_definition_from_yaml,
)
from opencontext_core.workflows.builtins import builtins_dir


def _oc_flow_like() -> WorkflowDefinition:
    """A minimal second-kind definition (proves WR1: no Runtime Core change)."""
    return WorkflowDefinition(
        id="oc-flow",
        version="1",
        label="OC Flow",
        kind="oc-flow",
        start_node="inspect",
        terminal_nodes=["report"],
        nodes={
            "inspect": WorkflowNodeDefinition(
                id="inspect", label="Inspect", role="oc-explorer", action="run_phase"
            ),
            "report": WorkflowNodeDefinition(
                id="report", label="Report", role="oc-reviewer", action="run_phase"
            ),
        },
        edges=[WorkflowEdgeDefinition(from_node="inspect", to_node="report")],
    )


def test_register_then_retrieve() -> None:
    """WR1: register then get returns the same definition; it appears in list()."""
    reg = WorkflowRegistry()
    defn = _oc_flow_like()
    reg.register(defn)
    assert reg.get("oc-flow") is defn
    assert "oc-flow" in [d.id for d in reg.list()]
    assert reg.has("oc-flow")


def test_unknown_get_raises() -> None:
    """WR1: get on an unknown id raises a typed lookup error."""
    with pytest.raises(WorkflowNotFound):
        WorkflowRegistry().get("does-not-exist")


def test_describe_summarizes_workflow() -> None:
    """WR1: describe returns an inspectable summary."""
    reg = WorkflowRegistry.with_builtins()
    desc = reg.describe("sdd")
    assert desc["id"] == "sdd"
    assert desc["kind"] == "sdd"
    assert desc["nodes"] == PHASE_ORDER


def test_builtin_sdd_present_and_consistent() -> None:
    """SDD1: built-in SDD is present; node ids == PHASE_ORDER; apply is oc-builder."""
    reg = WorkflowRegistry.with_builtins()
    sdd = reg.get("sdd")
    assert list(sdd.nodes.keys()) == PHASE_ORDER
    assert sdd.nodes["apply"].role == "oc-builder"


def test_builtin_sdd_personas_match_source() -> None:
    """SDD1: every node role matches PHASE_PERSONAS (no drift from the source)."""
    _order, _deps, personas = sdd_definition_source()
    sdd = WorkflowRegistry.with_builtins().get("sdd")
    for node_id, node in sdd.nodes.items():
        assert node.role == personas[node_id]


def test_builtin_sdd_edges_mirror_dependencies() -> None:
    """SDD1: YAML edges are the forward form of PHASE_DEPENDENCIES (no drift)."""
    sdd = WorkflowRegistry.with_builtins().get("sdd")
    yaml_edges = {(e.from_node, e.to_node) for e in sdd.edges}
    expected = {
        (dep, node) for node, deps in PHASE_DEPENDENCIES.items() for dep in deps
    }
    assert yaml_edges == expected


def test_yaml_template_parses_and_validates() -> None:
    """YAML1: builtins/sdd.yaml parses into a valid definition."""
    defn = load_definition_from_yaml(builtins_dir() / "sdd.yaml")
    assert defn.id == "sdd"
    assert defn.schema_version == "opencontext.workflow.v1"
    assert list(defn.nodes.keys()) == PHASE_ORDER
