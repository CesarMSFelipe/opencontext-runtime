"""ContextContractBuilder for OpenContext Runtime v2."""

from __future__ import annotations

from opencontext_core.context.planning.classifier import (
    TaskClassification,
    TaskClassifierProtocol,
)
from opencontext_core.context.planning.risk import RiskClassifier
from opencontext_core.models.context_contract import ContextContract, VerificationGate
from opencontext_core.models.evidence import EvidenceRef

TIER_BUDGET: dict[str, int] = {
    "cheap": 8_000,
    "precise": 16_000,
    "critical": 28_000,
}

TIER_GATES: dict[str, list[str]] = {
    "cheap": ["run-tests", "lint"],
    "precise": ["run-tests", "lint", "type-check"],
    "critical": ["run-tests", "lint", "type-check", "security-scan"],
}


def _extract_known_facts(manifest) -> list[EvidenceRef]:
    """Extract known facts from a project manifest."""
    facts: list[EvidenceRef] = []
    if manifest is None:
        return facts
    project_name = getattr(manifest, "project_name", None)
    if project_name:
        facts.append(
            EvidenceRef(
                source=f"manifest:project_name={project_name}",
                source_type="code",
                confidence=1.0,
                verified=True,
            )
        )
    language = getattr(manifest, "primary_language", None)
    if language:
        facts.append(
            EvidenceRef(
                source=f"manifest:language={language}",
                source_type="code",
                confidence=1.0,
                verified=True,
            )
        )
    file_count = getattr(manifest, "file_count", None)
    if file_count is not None:
        facts.append(
            EvidenceRef(
                source=f"manifest:file_count={file_count}",
                source_type="code",
                confidence=1.0,
                verified=True,
            )
        )
    return facts


def _gates_for_tier(
    risk_tier: str, task_type: str, requires_mutation: bool
) -> list[VerificationGate]:
    gate_ids = list(TIER_GATES.get(risk_tier, TIER_GATES["precise"]))
    if requires_mutation and "mutation-scan" not in gate_ids:
        gate_ids.append("mutation-scan")
    return [VerificationGate(id=gid) for gid in gate_ids]


def _extract_key_terms(query: str) -> list[str]:
    """Extract potential symbol patterns from query."""
    stop_words = {
        "fix",
        "add",
        "create",
        "the",
        "a",
        "an",
        "in",
        "for",
        "to",
        "of",
        "and",
        "or",
        "with",
        "from",
        "on",
        "at",
        "by",
        "is",
        "are",
        "was",
        "write",
        "refactor",
        "implement",
        "build",
        "migrate",
        "optimize",
    }
    words = query.lower().split()
    terms = [w for w in words if len(w) > 3 and w not in stop_words]
    return [f"*{t}*" for t in terms[:5]] if terms else []


class ContextContractBuilder:
    """Builds a ContextContract from query + manifest + memory context.

    SRP: only builds contracts, never retrieves.
    """

    def __init__(
        self,
        classifier: TaskClassifierProtocol,
        risk_classifier: RiskClassifier | None = None,
        memory=None,
    ) -> None:
        self._classifier = classifier
        self._risk_classifier = risk_classifier or RiskClassifier()
        self._memory = memory

    def build(
        self,
        query: str,
        manifest=None,
        memory_context=None,
    ) -> ContextContract:
        classification: TaskClassification = self._classifier.classify(query, manifest)
        risk_tier = self._risk_classifier.classify(
            classification.task_type, classification.risk_level
        )
        known = _extract_known_facts(manifest)
        unknown: list[str] = []
        required_symbols = _extract_key_terms(query)
        must_verify = _gates_for_tier(
            risk_tier, classification.task_type, classification.requires_mutation
        )
        required_memories: list[str] = []
        if memory_context:
            required_memories = [m.key for m in memory_context if hasattr(m, "key")]

        return ContextContract(
            task=query,
            task_type=classification.task_type,
            risk_level=classification.risk_level,
            risk_tier=risk_tier,  # type: ignore[arg-type]
            language=classification.language,
            framework=classification.framework,
            known=known,
            unknown=unknown,
            assumptions=[],
            required_symbols=required_symbols,
            required_files=[],
            required_memories=required_memories,
            must_verify=must_verify,
            forbidden_sources=[],
            token_budget=TIER_BUDGET[risk_tier],
        )
