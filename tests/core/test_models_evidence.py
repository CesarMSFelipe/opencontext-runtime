"""Tests for opencontext_core.models.evidence."""

import pytest
from pydantic import ValidationError

from opencontext_core.models.evidence import EvidenceRef


def test_evidence_ref_defaults():
    ref = EvidenceRef(source="file.py", source_type="code", confidence=0.9)
    assert ref.verified is False
    assert ref.confidence == 0.9


def test_evidence_ref_confidence_range():
    with pytest.raises((ValidationError, ValueError)):
        EvidenceRef(source="x", source_type="code", confidence=1.5)
    with pytest.raises((ValidationError, ValueError)):
        EvidenceRef(source="x", source_type="code", confidence=-0.1)


def test_evidence_ref_to_dict():
    ref = EvidenceRef(source="auth.py", source_type="file", confidence=0.8, verified=True)
    d = ref.model_dump()
    assert d["source"] == "auth.py"
    assert d["verified"] is True
