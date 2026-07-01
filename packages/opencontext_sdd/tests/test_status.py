"""Tests for the canonical SDD Status Pydantic model (REQ-OSS-001/002/003).

Per strict-TDD: this file is the source of truth for the Status model
contract. The model in ``opencontext_sdd.status`` is written to satisfy
these tests.

T1.5 — the single test below is written FIRST. T1.7 tests are added
in a subsequent commit, RED-first, before extending ``status.py``.
"""

from __future__ import annotations

import json

from opencontext_sdd.status import Status


def test_REQ_OSS_001_default_schema_name_and_14_fields_round_trip() -> None:
    """A fresh Status has the canonical schema name, and a fully-populated
    Status round-trips through JSON with all 14 fields preserved."""
    fresh = Status()
    assert fresh.schemaName == "opencontext.sdd-status"
    assert fresh.schemaVersion == 1

    populated = Status(
        changeName="agentic-parity-engram-gentle",
        artifactStore="hybrid",
        planningHome="openspec",
        changeRoot="openspec/changes/agentic-parity-engram-gentle",
        artifactPaths={
            "proposal": "openspec/changes/agentic-parity-engram-gentle/proposal.md",
            "design": "openspec/changes/agentic-parity-engram-gentle/design.md",
        },
        artifacts={"proposal": "done", "design": "partial", "tasks": "missing"},
        taskProgress={"total": 12, "done": 1},
        dependencies={"pr1": "opencontext-core", "pr2": "opencontext-memory"},
        applyState="running",
        actionContext={"allowedEditRoots": ["packages/opencontext_sdd"]},
        relationships={"extends": "opencontext-core.sdd_runtime"},
        nextRecommended="design",
        blockedReasons=["artifact:partial:design"],
    )
    raw = populated.model_dump_json()
    reparsed = Status.model_validate_json(raw)
    assert reparsed == populated
    # The 14 top-level fields are all present in the JSON payload.
    payload = json.loads(raw)
    expected_keys = {
        "schemaName",
        "schemaVersion",
        "changeName",
        "artifactStore",
        "planningHome",
        "changeRoot",
        "artifactPaths",
        "artifacts",
        "taskProgress",
        "dependencies",
        "applyState",
        "actionContext",
        "relationships",
        "nextRecommended",
        "blockedReasons",
    }
    assert expected_keys.issubset(payload.keys())
    assert len(payload) == len(expected_keys)
