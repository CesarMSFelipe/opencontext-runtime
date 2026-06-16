"""Risk tier classifier for OpenContext Runtime v2."""

from __future__ import annotations

from typing import ClassVar


class RiskTier:
    CHEAP = "cheap"
    PRECISE = "precise"
    CRITICAL = "critical"


class RiskClassifier:
    """Maps task_type + risk_level to retrieval tier."""

    _MAP: ClassVar[dict[tuple[str, str], str]] = {
        ("bugfix", "low"): "cheap",
        ("bugfix", "medium"): "precise",
        ("bugfix", "high"): "critical",
        ("bugfix", "critical"): "critical",
        ("feature", "low"): "cheap",
        ("feature", "medium"): "precise",
        ("feature", "high"): "precise",
        ("feature", "critical"): "critical",
        ("security", "low"): "critical",
        ("security", "medium"): "critical",
        ("security", "high"): "critical",
        ("security", "critical"): "critical",
        ("refactor", "low"): "cheap",
        ("refactor", "medium"): "precise",
        ("test", "low"): "cheap",
        ("test", "medium"): "cheap",
        ("documentation", "low"): "cheap",
        ("migration", "low"): "critical",
        ("migration", "medium"): "critical",
        ("performance", "low"): "precise",
        ("performance", "high"): "critical",
        ("architecture", "any"): "precise",
        ("configuration", "any"): "cheap",
    }
    _DEFAULT = "precise"

    def classify(self, task_type: str, risk_level: str) -> str:
        return self._MAP.get(
            (task_type, risk_level),
            self._MAP.get((task_type, "any"), self._DEFAULT),
        )
