"""SDD guardrails: rationalization catalogue and runtime evaluator.

Provides guardrail entries that detect common anti-patterns in SDD phase
output, helping agents avoid shallow or premature work.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GuardrailEntry:
    """A single guardrail entry in the catalogue."""

    name: str
    phases: list[str]
    rationalization: str
    counter_argument: str
    severity: str  # "warning" | "block"


@dataclass
class GuardrailHit:
    """A guardrail that was triggered during evaluation."""

    name: str
    counter_argument: str
    severity: str


# Catalogue of guardrail entries, one per SDD phase plus extras
CATALOGUE: list[GuardrailEntry] = [
    GuardrailEntry(
        name="explore-too-broad",
        phases=["explore"],
        rationalization="too broad",
        counter_argument="Exploration should focus on a specific area, not the entire codebase.",
        severity="warning",
    ),
    GuardrailEntry(
        name="no-specific-approach",
        phases=["propose"],
        rationalization="no specific approach",
        counter_argument="Proposals must recommend a concrete technical approach, not just describe the problem.",
        severity="warning",
    ),
    GuardrailEntry(
        name="too-simple-for-spec",
        phases=["spec"],
        rationalization="too simple for a spec",
        counter_argument="Even simple changes benefit from a spec — it defines success criteria.",
        severity="warning",
    ),
    GuardrailEntry(
        name="design-without-alternatives",
        phases=["design"],
        rationalization="without considering alternatives",
        counter_argument="Design documents should discuss at least one alternative before choosing an approach.",
        severity="warning",
    ),
    GuardrailEntry(
        name="tasks-too-vague",
        phases=["tasks"],
        rationalization="task is too vague",
        counter_argument="Each task must be specific and actionable — 'implement feature' is not enough.",
        severity="warning",
    ),
    GuardrailEntry(
        name="apply-without-test",
        phases=["apply"],
        rationalization="without writing tests",
        counter_argument="Apply phase must include or reference tests for the changes made.",
        severity="block",
    ),
    GuardrailEntry(
        name="verify-no-evidence",
        phases=["verify"],
        rationalization="no evidence provided",
        counter_argument="Verification must include concrete evidence: test output, screenshots, or logs.",
        severity="warning",
    ),
    GuardrailEntry(
        name="archive-skip-delta",
        phases=["archive"],
        rationalization="skip the delta",
        counter_argument="Archiving must include a delta summary — what changed and why.",
        severity="warning",
    ),
    GuardrailEntry(
        name="propose-no-rollback",
        phases=["propose"],
        rationalization="no rollback plan",
        counter_argument="Proposals should include a rollback strategy for risky changes.",
        severity="warning",
    ),
    GuardrailEntry(
        name="spec-missing-scenarios",
        phases=["spec"],
        rationalization="missing test scenarios",
        counter_argument="Specs should define concrete scenarios to validate correct behavior.",
        severity="warning",
    ),
]


def get_catalogue() -> list[GuardrailEntry]:
    """Return the full guardrail catalogue."""
    return list(CATALOGUE)


def get_guardrails_for_phase(phase: str) -> list[GuardrailEntry]:
    """Get all guardrail entries that apply to the given phase.

    Args:
        phase: Phase name.

    Returns:
        List of guardrail entries for the phase.
    """

    return [entry for entry in CATALOGUE if phase in entry.phases]


def evaluate_guardrails(phase: str, context: str) -> list[GuardrailHit]:
    """Evaluate guardrails for a given phase against the provided context text.

    Uses case-insensitive substring matching against rationalization strings.

    Args:
        phase: Phase name.
        context: Phase content to evaluate.

    Returns:
        List of guardrail hits. Empty list means no guardrails triggered.
    """

    if not context:
        return []

    hits: list[GuardrailHit] = []
    context_lower = context.lower()

    for entry in CATALOGUE:
        if phase not in entry.phases:
            continue
        if entry.rationalization.lower() in context_lower:
            hits.append(
                GuardrailHit(
                    name=entry.name,
                    counter_argument=entry.counter_argument,
                    severity=entry.severity,
                )
            )

    return hits
