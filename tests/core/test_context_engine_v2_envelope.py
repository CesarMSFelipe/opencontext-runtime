"""PR-010 SPEC-CTX-010-08: typed three-layer ContextEnvelope."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from opencontext_core.models.context import ContextOmission
from opencontext_core.models.context_envelope import (
    CONTEXT_CONTRACT_VERSION,
    ContextEnvelope,
)
from opencontext_core.models.evidence import EvidenceRef


def test_envelope_defaults_construct() -> None:
    env = ContextEnvelope()
    assert env.schema_version == "opencontext.context.v1"
    assert env.l3 == {} and env.l2 == {} and env.l1 == {}
    assert env.token_estimate == 0
    assert env.evidence_refs == [] and env.omissions == []
    assert env.confidence == 0.0


def test_envelope_separates_three_layers() -> None:
    env = ContextEnvelope(
        workflow="oc_flow",
        node="gather_context",
        task="add a method",
        l3={"kg_nodes": [{"name": "Foo"}]},
        l2={"acceptance_criteria": ["does X"]},
        l1={"items": [{"source": "foo.py"}]},
        token_estimate=120,
        evidence_refs=[EvidenceRef(source="foo.py", source_type="file", confidence=0.8)],
        omissions=[
            ContextOmission(item_id="bar", reason="token_budget_exceeded", tokens=5, score=0.1)
        ],
        confidence=0.7,
    )
    assert env.l3["kg_nodes"][0]["name"] == "Foo"  # structural
    assert env.l2["acceptance_criteria"] == ["does X"]  # task contract
    assert env.l1["items"][0]["source"] == "foo.py"  # working files
    assert env.token_estimate == 120
    assert env.confidence == 0.7


def test_l1_is_ephemeral_l2_immutable_view() -> None:
    env = ContextEnvelope(l2={"contract": "frozen"}, l1={"items": [1, 2, 3]})
    purged = env.purge_l1()
    assert purged.l1 == {}  # L1 purged after consolidation
    assert purged.l2 == {"contract": "frozen"}  # L2 preserved
    assert env.l1 == {"items": [1, 2, 3]}  # original untouched (copy semantics)


def test_confidence_and_token_estimate_bounds() -> None:
    with pytest.raises(ValidationError):
        ContextEnvelope(confidence=1.5)
    with pytest.raises(ValidationError):
        ContextEnvelope(token_estimate=-1)


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        ContextEnvelope(unexpected="x")


def test_contract_version_is_pinned() -> None:
    # Guard test (doc 59 internal contract versioning).
    assert CONTEXT_CONTRACT_VERSION == 1
