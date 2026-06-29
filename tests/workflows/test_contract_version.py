"""Workflow Contract v1 guard (doc 59 — internal contract versioning).

An accidental breaking change to the workflow schema must be caught: the contract
version is pinned and the schema string is the v1 family. Bumping these is a
deliberate act that updates this guard.
"""

from __future__ import annotations

from opencontext_core.workflows import (
    WORKFLOW_CONTRACT_VERSION,
    WORKFLOW_SCHEMA_VERSION,
    WorkflowRegistry,
)
from opencontext_core.workflows.definition import node_uid, workflow_uid


def test_workflow_contract_version_is_one() -> None:
    assert WORKFLOW_CONTRACT_VERSION == 1


def test_workflow_schema_version_is_v1() -> None:
    assert WORKFLOW_SCHEMA_VERSION == "opencontext.workflow.v1"


def test_builtin_carries_v1_schema() -> None:
    assert WorkflowRegistry.with_builtins().get("sdd").schema_version == WORKFLOW_SCHEMA_VERSION


def test_global_id_scheme() -> None:
    """doc 59: WorkflowID = wf_<slug>, NodeID = node_<slug>."""
    assert workflow_uid("sdd") == "wf_sdd"
    assert node_uid("apply") == "node_apply"
