"""Task classifier for OpenContext Runtime v2.

Deterministic keyword-based classification. Never calls an LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class TaskClassification:
    """Result of classifying a task query."""

    # Task types: bugfix|feature|refactor|test|documentation|architecture
    #             |security|performance|migration|configuration
    task_type: str
    risk_level: str  # low|medium|high|critical
    language: str | None
    framework: str | None
    requires_tests: bool
    requires_mutation: bool
    confidence: float  # 0.0-1.0
    matched_rules: list[str] = field(default_factory=list)


@runtime_checkable
class TaskClassifierProtocol(Protocol):
    def classify(self, query: str, manifest=None) -> TaskClassification: ...


@dataclass(frozen=True)
class ClassificationRule:
    """A single keyword-matching classification rule."""

    id: str
    keywords: tuple[str, ...]
    task_type: str | None  # None = risk-only rule
    risk_boost: str | None = None  # escalates risk_level
    requires_mutation: bool = False


DEFAULT_RULES: tuple[ClassificationRule, ...] = (
    ClassificationRule(
        "bugfix",
        ("fix", "bug", "error", "broken", "crash", "regression", "fault"),
        "bugfix",
    ),
    ClassificationRule(
        "feature",
        ("add", "implement", "create", "new", "build", "introduce"),
        "feature",
    ),
    ClassificationRule(
        "refactor",
        ("refactor", "cleanup", "rename", "move", "extract", "reorganize"),
        "refactor",
    ),
    ClassificationRule(
        "test",
        ("test", "spec", "coverage", "tdd", "failing test"),
        "test",
    ),
    ClassificationRule(
        "docs",
        ("doc", "readme", "comment", "explain", "document"),
        "documentation",
    ),
    ClassificationRule(
        "security",
        (
            "security",
            "permission",
            "injection",
            "xss",
            "csrf",
            "vulnerability",
        ),
        "security",
        risk_boost="high",
        requires_mutation=True,
    ),
    ClassificationRule(
        "perf",
        ("performance", "slow", "optimize", "latency", "cache", "throughput"),
        "performance",
    ),
    ClassificationRule(
        "migration",
        ("migrate", "migration", "upgrade", "deprecat", "replace"),
        "migration",
    ),
    ClassificationRule(
        "config",
        ("config", "configuration", "setting", "env", "environment"),
        "configuration",
    ),
    ClassificationRule(
        "arch",
        ("architecture", "design", "pattern"),
        "architecture",
    ),
    # Risk escalators (task_type=None)
    ClassificationRule(
        "critical_risk",
        ("critical", "production", "hotfix", "urgent", "outage", "data loss"),
        None,
        risk_boost="critical",
    ),
    ClassificationRule(
        "high_risk",
        ("important", "regression", "breaking", "incident"),
        None,
        risk_boost="high",
    ),
)

_RISK_ORDER = ("low", "medium", "high", "critical")

# Task types inherently low-risk — default to "low", only boosted by explicit escalators
_LOW_RISK_TASK_TYPES: frozenset[str] = frozenset({
    "refactor", "documentation", "test", "configuration",
})

# Keywords that always force risk to "low" regardless of task type
_TRIVIAL_KEYWORDS: frozenset[str] = frozenset({
    "typo", "rename", "whitespace", "comment", "unused", "cleanup",
    "format", "trivial", "minor", "cosmetic",
})


class TaskClassifier:
    """Deterministic. O(n) over keyword rules. Never calls LLM."""

    def __init__(self, rules: tuple[ClassificationRule, ...] | None = None) -> None:
        self._rules = rules or DEFAULT_RULES

    def classify(self, query: str, manifest=None) -> TaskClassification:
        normalized = query.lower()
        task_type = "feature"
        risk_level = "medium"
        requires_mutation = False
        matched: list[str] = []
        confidence = 0.3

        for rule in self._rules:
            if any(kw in normalized for kw in rule.keywords):
                matched.append(rule.id)
                if rule.task_type is not None:
                    task_type = rule.task_type
                    confidence = min(0.5 + 0.1 * len(matched), 0.95)
                if rule.risk_boost:
                    current_idx = _RISK_ORDER.index(risk_level)
                    boost_idx = _RISK_ORDER.index(rule.risk_boost)
                    risk_level = _RISK_ORDER[max(current_idx, boost_idx)]
                if rule.requires_mutation:
                    requires_mutation = True

        # Low-risk task types start at "low" unless a boost already raised them
        if task_type in _LOW_RISK_TASK_TYPES and risk_level == "medium":
            risk_level = "low"

        # Trivial keywords force risk to "low" regardless of task type or prior boosts
        if any(kw in normalized for kw in _TRIVIAL_KEYWORDS):
            risk_level = "low"

        language = None
        framework = None
        if manifest is not None:
            language = getattr(manifest, "primary_language", None)
            frameworks = getattr(manifest, "detected_frameworks", [])
            framework = frameworks[0] if frameworks else None
            if getattr(manifest, "file_count", 0) > 10_000 and risk_level == "low":
                risk_level = "medium"

        return TaskClassification(
            task_type=task_type,
            risk_level=risk_level,
            language=language,
            framework=framework,
            requires_tests=task_type not in ("documentation", "configuration"),
            requires_mutation=requires_mutation or risk_level == "critical",
            confidence=confidence,
            matched_rules=matched,
        )
