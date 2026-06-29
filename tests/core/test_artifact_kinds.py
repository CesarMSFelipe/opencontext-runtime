"""PR-002 ART-02 / REC-02: artifact + receipt kind registries are enforced."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from opencontext_core.models.artifact import ARTIFACT_KINDS, ArtifactWriteRequest
from opencontext_core.models.receipt import RECEIPT_KINDS, Receipt

_REQUIRED_ARTIFACT = {
    "context-envelope",
    "task-contract",
    "proposal",
    "spec",
    "design",
    "tasks",
    "mutation",
    "patch",
    "inspection-report",
    "diagnosis-attempt",
    "review-report",
    "escalation-report",
    "memory-delta",
    "graph-delta",
    "cost-report",
    "confidence-report",
    "summary",
}

_REQUIRED_RECEIPT = {
    "workflow-selection",
    "context-retrieval",
    "policy-decision",
    "provider-call",
    "mutation",
    "inspection",
    "diagnosis",
    "escalation",
    "memory-write",
    "kg-update",
    "consolidation",
    "benchmark",
}


def test_artifact_kinds_cover_the_17_required() -> None:
    assert len(_REQUIRED_ARTIFACT) == 17
    assert _REQUIRED_ARTIFACT <= ARTIFACT_KINDS


def test_convergence_artifact_kinds_present() -> None:
    assert {"decision-log", "program-plan"} <= ARTIFACT_KINDS


def test_receipt_kinds_are_exactly_the_12() -> None:
    assert _REQUIRED_RECEIPT == RECEIPT_KINDS
    assert len(RECEIPT_KINDS) == 12


def test_unknown_receipt_kind_rejected() -> None:
    with pytest.raises(ValidationError):
        Receipt(kind="not-a-kind", action="x")


def test_unknown_artifact_kind_rejected() -> None:
    with pytest.raises(ValidationError):
        ArtifactWriteRequest(run_id="r", session_id="s", kind="not-a-kind", content="x")


def test_known_kinds_accepted() -> None:
    assert Receipt(kind="mutation", action="applied").kind == "mutation"
    req = ArtifactWriteRequest(run_id="r", session_id="s", kind="patch", content="d")
    assert req.kind == "patch"
