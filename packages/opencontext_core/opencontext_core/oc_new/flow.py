"""Canonical 10-phase oc-new flow definition."""

from __future__ import annotations

from opencontext_core.oc_new.models import PhaseDefinition

OC_NEW_FLOW: tuple[PhaseDefinition, ...] = (
    PhaseDefinition(
        name="explore",
        persona="oc-explorer",
        skill="oc-explore",
        expected_artifacts=["explore.artifact.json", "context-pack.json"],
        required_harnesses=["context", "kg", "memory"],
        required_tools=[
            "opencontext_memory_context",
            "opencontext_context",
            "opencontext_impact",
            "opencontext_memory_save",
        ],
    ),
    PhaseDefinition(
        name="propose",
        persona="oc-orchestrator",
        skill="oc-propose",
        required_artifacts=["explore.artifact.json"],
        expected_artifacts=["proposal.md", "proposal.json", "propose.artifact.json"],
        required_harnesses=["planning"],
        required_tools=["opencontext_memory_context", "opencontext_memory_save"],
    ),
    PhaseDefinition(
        name="spec",
        persona="oc-requirements",
        skill="oc-spec",
        required_artifacts=["proposal.md"],
        expected_artifacts=["spec.md", "spec.json", "spec.artifact.json"],
        required_harnesses=["planning"],
        required_tools=["opencontext_memory_context", "opencontext_memory_save"],
    ),
    PhaseDefinition(
        name="design",
        persona="oc-architect",
        skill="oc-design",
        required_artifacts=["spec.md"],
        expected_artifacts=["design.md", "design.json", "design.artifact.json"],
        required_harnesses=["planning"],
        required_tools=[
            "opencontext_memory_context",
            "opencontext_context",
            "opencontext_impact",
            "opencontext_memory_save",
        ],
    ),
    PhaseDefinition(
        name="tasks",
        persona="oc-planner",
        skill="oc-tasks",
        required_artifacts=["spec.md", "design.md"],
        expected_artifacts=["tasks.md", "tasks.json", "tasks.artifact.json"],
        required_harnesses=["planning"],
        required_tools=["opencontext_memory_context", "opencontext_memory_save"],
    ),
    PhaseDefinition(
        name="approval",
        persona=None,
        skill=None,
        required_artifacts=["spec.md", "design.md", "tasks.md"],
        expected_artifacts=["approval.json"],
    ),
    PhaseDefinition(
        name="apply",
        persona="oc-builder",
        skill="oc-apply",
        writes_code=True,
        requires_approval=True,
        required_artifacts=["approval.json", "tasks.md"],
        expected_artifacts=["apply-manifest.json", "apply.artifact.json"],
        required_harnesses=["mutation", "protocol"],
        required_tools=[
            "opencontext_memory_context",
            "opencontext_context",
            "opencontext_impact",
            "opencontext_memory_save",
        ],
    ),
    PhaseDefinition(
        name="verify",
        persona="oc-harness-verifier",
        skill="oc-verify",
        required_artifacts=["apply-manifest.json"],
        expected_artifacts=[
            "verify-report.json",
            "verify.artifact.json",
            "compliance-matrix.json",
            "harness-report.json",
            # NOTE: tdd-evidence.json and quality-gate.json are SHOULD (warn-only)
            # pending DoD #18 confirmation — not yet hard-required.
            "tdd-evidence.json",
            "quality-gate.json",
        ],
        required_harnesses=["inspection", "evaluation", "security", "review"],
        required_tools=[
            "opencontext_memory_context",
            "opencontext_context",
            "opencontext_impact",
            "opencontext_quality",
            "opencontext_memory_save",
        ],
    ),
    PhaseDefinition(
        name="review",
        persona="oc-reviewer",
        skill="oc-review",
        required_artifacts=["verify-report.json"],
        expected_artifacts=["review-report.json", "review.artifact.json"],
        required_harnesses=["review"],
        required_tools=[
            "opencontext_memory_context",
            "opencontext_context",
            "opencontext_impact",
            "opencontext_quality",
            "opencontext_memory_save",
        ],
    ),
    PhaseDefinition(
        name="archive",
        persona="oc-archivist",
        skill="oc-archive",
        required_artifacts=[
            "review-report.json",
            "compliance-matrix.json",
            "harness-report.json",
        ],
        expected_artifacts=["archive-report.json", "archive.artifact.json", "receipt.json"],
        required_harnesses=["consolidation", "memory", "kg"],
        required_tools=["opencontext_memory_context", "opencontext_memory_save"],
    ),
)

PHASE_NAMES: tuple[str, ...] = tuple(p.name for p in OC_NEW_FLOW)
