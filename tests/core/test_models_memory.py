"""Tests for MemoryLayer, DecayPolicy, MemoryRecord in opencontext_core.models.agent_memory."""

from datetime import UTC, datetime

import pytest

from opencontext_core.models.agent_memory import DecayPolicy, MemoryLayer, MemoryRecord
from opencontext_core.models.evidence import EvidenceRef


def test_failure_layer_exists():
    assert MemoryLayer.FAILURE == "failure"
    layers = list(MemoryLayer)
    assert len(layers) == 5
    assert MemoryLayer.SEMANTIC in layers
    assert MemoryLayer.EPISODIC in layers
    assert MemoryLayer.PROCEDURAL in layers
    assert MemoryLayer.WORKING in layers
    assert MemoryLayer.FAILURE in layers


def test_decay_policy_defaults():
    policy = DecayPolicy(enabled=True)
    assert policy.half_life_days == 90


def test_memory_record_defaults():
    now = datetime.now(UTC)
    record = MemoryRecord(
        id="rec-1",
        layer=MemoryLayer.EPISODIC,
        key="auth:login_failure",
        content="Login failed due to missing token.",
        source_refs=[EvidenceRef(source="auth.py", source_type="code", confidence=0.9)],
        decay_policy=DecayPolicy(enabled=False),
        created_at=now,
        updated_at=now,
    )
    assert record.confidence == 1.0
    assert record.supersedes == []
    assert record.contradicted_by == []
    assert record.tags == []
    assert record.linked_nodes == []


def test_confidence_bounds():
    now = datetime.now(UTC)
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        MemoryRecord(
            id="bad",
            layer=MemoryLayer.WORKING,
            key="k",
            content="c",
            confidence=2.0,
            source_refs=[],
            decay_policy=DecayPolicy(enabled=False),
            created_at=now,
            updated_at=now,
        )
