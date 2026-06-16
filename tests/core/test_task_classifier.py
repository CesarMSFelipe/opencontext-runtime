"""Tests for TaskClassifier — 12 cases."""

from __future__ import annotations

import pytest

from opencontext_core.context.planning.classifier import (
    TaskClassifier,
    TaskClassifierProtocol,
)


@pytest.fixture()
def clf() -> TaskClassifier:
    return TaskClassifier()


def test_bugfix_classification(clf: TaskClassifier) -> None:
    result = clf.classify("fix crash in auth")
    assert result.task_type == "bugfix"


def test_feature_classification(clf: TaskClassifier) -> None:
    result = clf.classify("add user profile endpoint")
    assert result.task_type == "feature"


def test_refactor_classification(clf: TaskClassifier) -> None:
    result = clf.classify("refactor service layer")
    assert result.task_type == "refactor"


def test_test_classification(clf: TaskClassifier) -> None:
    result = clf.classify("write tests for UserController")
    assert result.task_type == "test"


def test_security_classification(clf: TaskClassifier) -> None:
    result = clf.classify("fix security vulnerability in login")
    assert result.task_type == "security"
    assert result.risk_level == "high"
    assert result.requires_mutation is True


def test_critical_risk_escalation(clf: TaskClassifier) -> None:
    result = clf.classify("critical production outage in payment")
    assert result.risk_level == "critical"
    assert result.requires_mutation is True


def test_unknown_query_default_confidence(clf: TaskClassifier) -> None:
    result = clf.classify("xyz abc totally unknown query with no keywords")
    assert result.confidence == pytest.approx(0.3)


def test_performance_classification(clf: TaskClassifier) -> None:
    result = clf.classify("optimize database query performance")
    assert result.task_type == "performance"


def test_migration_classification(clf: TaskClassifier) -> None:
    result = clf.classify("migrate from v1 to v2 API")
    assert result.task_type == "migration"


def test_matched_rules_audit_trail(clf: TaskClassifier) -> None:
    result = clf.classify("fix security vulnerability in login")
    assert "bugfix" in result.matched_rules
    assert "security" in result.matched_rules


def test_requires_mutation_when_risk_critical(clf: TaskClassifier) -> None:
    result = clf.classify("critical production outage in payment")
    assert result.requires_mutation is True


def test_satisfies_protocol(clf: TaskClassifier) -> None:
    assert isinstance(clf, TaskClassifierProtocol)
