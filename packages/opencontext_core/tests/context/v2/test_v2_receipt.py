"""Tests for context.v2.receipt — ContextReceipt schema (CONV2 #10).

Commit-010 introduces the initial receipt (7 fields). Commit-019 extends to 13.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from opencontext_core.context.v2.receipt import ContextReceipt


def _sample_receipt() -> ContextReceipt:
    return ContextReceipt(
        receipt_id="rcpt-001",
        request_id="req-001",
        workflow="sdd",
        node="apply",
        task="implement auth middleware",
        envelope_hash="ehash",
        ranking_hash="rhash",
        budget_hash="bhash",
        included_refs=[],
        omitted_refs=[],
        used_tokens=1200,
        available_tokens=3000,
        confidence=0.85,
    )


def test_round_trip_json() -> None:
    receipt = _sample_receipt()
    blob = receipt.model_dump_json()
    restored = ContextReceipt.model_validate_json(blob)
    assert restored == receipt
    # also parse via raw json.loads to catch non-pydantic regressions
    raw = json.loads(blob)
    assert raw["receipt_id"] == "rcpt-001"
    assert raw["workflow"] == "sdd"


def test_validates_required_fields() -> None:
    # missing every required field → ValidationError
    with pytest.raises(ValidationError):
        ContextReceipt()  # type: ignore[call-arg]

    # missing only one required field (confidence) → ValidationError
    base = _sample_receipt().model_dump()
    base.pop("confidence")
    with pytest.raises(ValidationError):
        ContextReceipt.model_validate(base)


def test_confidence_in_unit_interval() -> None:
    base = _sample_receipt().model_dump()
    base["confidence"] = 1.5
    with pytest.raises(ValidationError):
        ContextReceipt.model_validate(base)
    base["confidence"] = -0.1
    with pytest.raises(ValidationError):
        ContextReceipt.model_validate(base)
    base["confidence"] = 0.0
    assert ContextReceipt.model_validate(base).confidence == 0.0
    base["confidence"] = 1.0
    assert ContextReceipt.model_validate(base).confidence == 1.0
