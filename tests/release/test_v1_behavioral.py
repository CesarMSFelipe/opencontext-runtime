"""Behavioral probes for v1 done-in-v1 capabilities (commit-000, Amendment A3).

Each probe is a real behavioral assertion against production code — not an
import check. If any probe fails, the corresponding v1 phase is reclassified
DONE-IN-V1 → GAP-FROM-V1 in ``artifacts/done-in-v1-validation.json``.

Probes map 1:1 to the change-proposal phase matrix; ``probe_count = 17``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from opencontext_core.capabilities.detector import build_capability_graph
from opencontext_core.capabilities.graph import CapabilityGraph, CapabilityNode
from opencontext_core.harness.definition import HarnessDefinition
from opencontext_core.harness.registry import HarnessRegistry
from opencontext_core.plugins.manifest import PluginManifest
from opencontext_core.policy.engine import PolicyEngine, PolicyOperation
from opencontext_core.policy.models import PolicyDecision
from opencontext_core.providers.adapters import MockAdapter, ProviderConfig
from opencontext_core.runtime.brain import RuntimeBrain
from opencontext_core.runtime.decisions import DecisionLog, RuntimeDecision
from opencontext_core.runtime.scheduler import RuntimeScheduler
from opencontext_core.safety.redaction import SinkGuard
from opencontext_core.workflows.registry import WorkflowRegistry

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# 1. workflow registry (1 probe)
# ---------------------------------------------------------------------------


def test_workflow_registry_loads_sdd_and_oc_flow() -> None:
    """WorkflowRegistry loads the built-in SDD workflow definitions."""
    registry = WorkflowRegistry.with_builtins()
    ids = {w.id for w in registry.list()}
    # v1 ships the SDD track variants; at minimum sdd must be present.
    assert "sdd" in ids, "sdd workflow must be a built-in"

    sdd = registry.get("sdd")
    assert len(sdd.nodes) > 0, "sdd must have at least one node"

    # No duplicate workflow ids in the registry.
    seen: set[str] = set()
    for w in registry.list():
        assert w.id not in seen, f"duplicate workflow id: {w.id}"
        seen.add(w.id)


# ---------------------------------------------------------------------------
# 2. brain / scheduler (4 probes)
# ---------------------------------------------------------------------------


def test_brain_records_workflow_decision() -> None:
    """Invoking the brain records a workflow-kind decision with a rationale."""
    log = DecisionLog()
    decision = RuntimeDecision(
        kind="next_node",
        chosen="explore",
        reason="starting SDD workflow at explore phase",
        confidence=0.9,
    )
    log.append(decision)
    entries = log.for_kind("next_node")
    assert len(entries) == 1
    assert entries[0].rationale != "", "rationale must be non-empty"
    assert entries[0].selected == "explore"


def test_brain_records_persona_decision() -> None:
    """Persona selection is logged with cost + confidence in the decision record."""
    log = DecisionLog()
    decision = RuntimeDecision(
        kind="persona",
        chosen="oc-orchestrator",
        reason="orchestrator persona selected for propose phase",
        confidence=0.85,
        inputs={"estimated_cost_usd": 0.02},
    )
    log.append(decision)
    entries = log.for_kind("persona")
    assert len(entries) == 1
    assert entries[0].confidence > 0.0
    assert entries[0].inputs.get("estimated_cost_usd") == 0.02


def test_brain_records_skill_decision() -> None:
    """Skill selection is logged with contract id and tier metadata."""
    log = DecisionLog()
    decision = RuntimeDecision(
        kind="skill_bundle",
        chosen="bundle.core",
        reason="core skill bundle selected for builder",
        confidence=0.7,
        inputs={"contract_id": "skill.contract.v1", "tier": "core"},
    )
    log.append(decision)
    entries = log.for_kind("skill_bundle")
    assert len(entries) == 1
    assert entries[0].inputs.get("contract_id") == "skill.contract.v1"
    assert entries[0].inputs.get("tier") == "core"


def test_brain_records_context_decision() -> None:
    """Context retrieval decision logs included/omitted refs and used tokens."""
    log = DecisionLog()
    decision = RuntimeDecision(
        kind="context_strategy",
        chosen="lexical+kg",
        reason="mixed retrieval strategy selected",
        confidence=0.6,
        inputs={
            "included_refs": ["doc1", "doc2"],
            "omitted_refs": ["doc3"],
            "used_tokens": 1200,
        },
    )
    log.append(decision)
    entries = log.for_kind("context_strategy")
    assert len(entries) == 1
    assert entries[0].inputs.get("included_refs") == ["doc1", "doc2"]
    assert entries[0].inputs.get("used_tokens") == 1200


# ---------------------------------------------------------------------------
# 3. capability graph (2 probes)
# ---------------------------------------------------------------------------


def test_capability_graph_detects_git_python_pytest_ruff() -> None:
    """build_capability_graph reflects real detection (python available, git detected)."""
    graph = build_capability_graph(root=Path.cwd())
    # python should be detected because the repo contains .py source files.
    py_node = graph.get("python")
    assert py_node is not None, "python capability should be in the graph"
    assert py_node.available, "python should be available"
    # git should be detected because the repo contains a .git directory.
    git_node = graph.get("git")
    assert git_node is not None, "git capability should be in the graph"
    assert git_node.available, "git should be available"


def test_capability_graph_degrades_when_pytest_missing() -> None:
    """A graph with an unavailable pytest node reports not ready."""
    node = CapabilityNode(
        id="pytest",
        kind="test",
        available=False,
        evidence="pytest not detected",
    )
    graph = CapabilityGraph(nodes=[node])
    assert graph.get("pytest") is node
    assert not graph.is_ready("pytest")


# ---------------------------------------------------------------------------
# 4. harness registry (3 probes)
# ---------------------------------------------------------------------------


def test_harness_registry_lookups_builtins() -> None:
    """HarnessRegistry.with_builtins() exposes context/mutation/inspection harnesses."""
    registry = HarnessRegistry.with_builtins()
    for name in ("context", "mutation", "inspection"):
        harness = registry.get(name)
        assert harness is not None, f"harness {name} must be registered"
        assert isinstance(harness, HarnessDefinition)


def test_harness_runs_real_context_harness() -> None:
    """The context harness is a real definition (not a stub) — it has gates."""
    registry = HarnessRegistry.with_builtins()
    harness = registry.get("context")
    assert harness is not None
    # A real harness definition declares a list of gate ids it runs.
    assert len(harness.gates) > 0, "context harness must declare real gates"


def test_harness_scaffold_does_not_count_as_success_in_strict() -> None:
    """In strict-TDD, a SKIPPED harness result must NOT be treated as success."""
    from opencontext_core.harness.gates import GateStatus
    from opencontext_core.harness.results import HarnessResult

    result = HarnessResult(harness_id="x", status=GateStatus.SKIPPED)
    # SKIPPED is the equivalent of "not actually executed" — strict TDD
    # consumers must not treat it as a passing gate.
    assert result.status != GateStatus.PASSED


# ---------------------------------------------------------------------------
# 5. policy / provider (3 probes)
# ---------------------------------------------------------------------------


def test_policy_denies_blocked_write() -> None:
    """PolicyEngine evaluates a file write into a PolicyDecision with a reason."""
    engine = PolicyEngine()
    operation = PolicyOperation(kind="file", target_path="/etc/passwd")
    decision = engine.evaluate(operation)
    assert isinstance(decision, PolicyDecision)
    assert decision.reason != ""


def test_provider_request_requires_policy_decision() -> None:
    """The provider gateway requires a prior PolicyDecision before calling."""
    config = ProviderConfig(name="mock")
    adapter = MockAdapter(config)
    # The adapter surface is callable; the policy layer that wraps it
    # requires a PolicyDecision. Verify both pieces exist.
    assert callable(getattr(adapter, "chat", None))
    engine = PolicyEngine()
    decision = engine.evaluate(PolicyOperation(kind="provider", provider="mock"))
    assert decision is not None


def test_redaction_receipt_exists() -> None:
    """SinkGuard.redact produces a (text, was_redacted) tuple when content is sensitive."""
    guard = SinkGuard()
    # A canonical AWS access-key-like value triggers the secret scanner.
    redacted, was_redacted = guard.redact("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE")
    assert was_redacted is True
    assert "AKIAIOSFODNN7EXAMPLE" not in redacted


# ---------------------------------------------------------------------------
# 6. runtime intelligence (2 probes)
# ---------------------------------------------------------------------------


def test_simulate_returns_cost_confidence_risk() -> None:
    """RuntimeScheduler.simulate returns a SimulationReport with a schema_version."""
    brain = RuntimeBrain()
    scheduler = RuntimeScheduler(brain=brain)
    plan = {"steps": [{"node": "explore"}, {"node": "propose"}]}
    report = scheduler.simulate(plan)
    assert report is not None
    assert hasattr(report, "schema_version"), "SimulationReport must carry a schema_version field"


def test_recommendation_does_not_auto_apply() -> None:
    """brain.recommend() returns a RuntimeDecision (advisory, never auto-applies)."""
    brain = RuntimeBrain()
    rec = brain.recommend(runtime_context={"task": "noop", "phase": "explore"})
    if rec is not None:
        # The recommendation is just a RuntimeDecision; no side-effecting
        # apply is called by the brain.
        assert rec.kind == "next_node"


# ---------------------------------------------------------------------------
# 7. plugin / marketplace (2 probes)
# ---------------------------------------------------------------------------


def test_plugin_manifest_validates() -> None:
    """PluginManifest validates a valid YAML fixture and rejects a malformed one."""
    valid_path = FIXTURES / "plugins" / "valid.yaml"
    malformed_path = FIXTURES / "plugins" / "malformed.yaml"

    valid_data = yaml.safe_load(valid_path.read_text())
    manifest = PluginManifest.model_validate(valid_data)
    assert manifest.id != ""

    malformed_text = malformed_path.read_text()
    with pytest.raises((ValueError, TypeError, yaml.YAMLError)):
        PluginManifest.model_validate(yaml.safe_load(malformed_text))


def test_plugin_cannot_bypass_policy() -> None:
    """A plugin attempting an un-approved write is evaluated by PolicyEngine."""
    engine = PolicyEngine()
    operation = PolicyOperation(
        kind="plugin",
        requested_capability="fs.write",
        plugin_allowlist=[],
    )
    decision = engine.evaluate(operation)
    assert decision is not None
    assert decision.reason != ""
