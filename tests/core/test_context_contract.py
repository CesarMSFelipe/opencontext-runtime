"""Tests for ContextContract and VerificationGate."""

import pytest
import yaml

from opencontext_core.models.context_contract import ContextContract, VerificationGate


def _make_contract(**overrides) -> ContextContract:
    defaults = dict(
        task="fix login crash",
        task_type="bugfix",
        risk_level="high",
        risk_tier="critical",
        language="python",
        framework=None,
        known=[],
        unknown=[],
        assumptions=[],
        required_symbols=["auth.validate_token"],
        required_files=["auth.py"],
        required_memories=[],
        must_verify=[VerificationGate(id="run-tests"), VerificationGate(id="security-scan")],
        forbidden_sources=[],
        token_budget=28000,
    )
    defaults.update(overrides)
    return ContextContract(**defaults)


def test_is_complete_true():
    c = _make_contract()
    assert c.is_complete() is True


def test_is_complete_false_when_symbols_and_files_empty():
    c = _make_contract(required_symbols=[], required_files=[])
    assert c.is_complete() is False


def test_is_complete_false_when_must_verify_empty():
    c = _make_contract(must_verify=[])
    assert c.is_complete() is False


def test_to_yaml_contains_task_type():
    c = _make_contract()
    out = c.to_yaml()
    parsed = yaml.safe_load(out)
    assert parsed["task_type"] == "bugfix"


def test_risk_tier_validation():
    with pytest.raises((ValueError, KeyError)):
        _make_contract(risk_tier="ultra")  # invalid value


def test_verification_gate_defaults():
    gate = VerificationGate(id="run-tests")
    assert gate.required is True
    assert gate.passed is None
