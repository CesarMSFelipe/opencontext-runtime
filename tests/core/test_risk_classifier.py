"""Tests for RiskClassifier — 8 cases."""

from __future__ import annotations

from opencontext_core.context.planning.risk import RiskClassifier


def test_security_always_critical() -> None:
    rc = RiskClassifier()
    assert rc.classify("security", "low") == "critical"
    assert rc.classify("security", "high") == "critical"


def test_bugfix_low_cheap() -> None:
    # low-risk bugfixes (typos, trivial fixes) use cheap tier
    assert RiskClassifier().classify("bugfix", "low") == "cheap"


def test_bugfix_high_critical() -> None:
    assert RiskClassifier().classify("bugfix", "high") == "critical"


def test_feature_low_cheap() -> None:
    assert RiskClassifier().classify("feature", "low") == "cheap"


def test_migration_critical() -> None:
    assert RiskClassifier().classify("migration", "low") == "critical"
    assert RiskClassifier().classify("migration", "medium") == "critical"


def test_unknown_returns_precise_default() -> None:
    assert RiskClassifier().classify("unknown_type", "medium") == "precise"


def test_configuration_cheap() -> None:
    assert RiskClassifier().classify("configuration", "any") == "cheap"
    assert RiskClassifier().classify("configuration", "medium") == "cheap"


def test_test_cheap() -> None:
    assert RiskClassifier().classify("test", "low") == "cheap"
    assert RiskClassifier().classify("test", "medium") == "cheap"
