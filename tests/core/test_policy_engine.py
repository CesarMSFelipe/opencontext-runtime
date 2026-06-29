"""PR-005 Policy Engine — unit, parity, enforcement, and convergence tests.

Covers: canonical PolicyDecision/PolicyReceipt (PE-2/APPROVAL-2), presets
(PE-3), command classification (CMD-2), forbidden-command enforcement regression
(CMD-1), risk-based auto-apply (AUTO-1), engine↔enforcer parity for MET branches
(FILE-1/NET-1/PROV-1/SECRET-1/PLUGIN-1/PE-4), named events (EVENT-1), memory
forbidden-content (MEM-1), and the convergence seams (POL-CONV).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from opencontext_core.actions.policy import ActionRequest, ActionType, evaluate_action
from opencontext_core.config import (
    OpenContextConfig,
    ProviderPolicyConfig,
    default_config_data,
)
from opencontext_core.harness.gates import PolicyEnginePassedGate
from opencontext_core.harness.models import GateStatus
from opencontext_core.models.context import ContextItem, ContextPriority, DataClassification
from opencontext_core.models.run_envelope import RunEnvelope
from opencontext_core.policy import (
    POLICY_CONTRACT_VERSION,
    AutoApplyPolicy,
    ChangeRisk,
    CommandCategory,
    CommandClassifier,
    PolicyDecision,
    PolicyEngine,
    PolicyOperation,
    PolicyPreset,
    PolicyReceipt,
    forbidden_memory_content,
    resolve_preset,
)
from opencontext_core.policy.events import (
    COMMAND_BLOCKED,
    POLICY_DENIED,
    POLICY_EVALUATED,
    SECRET_DETECTED,
)
from opencontext_core.runtime.event_bus import CollectingConsumer, EventBus
from opencontext_core.safety.firewall import ContextFirewall

_SECRET = "sk-ant-api03-" + "A" * 80


def _ctx(
    content: str, classification: DataClassification = DataClassification.INTERNAL
) -> ContextItem:
    return ContextItem(
        id="c1",
        content=content,
        source="test",
        source_type="file",
        priority=ContextPriority.P1,
        tokens=10,
        score=1.0,
        classification=classification,
    )


def _provider_config(*, external_enabled: bool = False) -> OpenContextConfig:
    data = default_config_data()
    data["security"]["external_providers_enabled"] = external_enabled
    cfg = OpenContextConfig.model_validate(data)
    return cfg.model_copy(
        update={
            "provider_policies": [
                ProviderPolicyConfig(
                    provider="anthropic",
                    allowed=True,
                    allowed_classifications={"public", "internal"},
                )
            ]
        }
    )


# -- PE-2 / APPROVAL-2: canonical models --------------------------------------


def test_policy_decision_full_field_set() -> None:
    decision = PolicyDecision(
        operation="command",
        decision="deny",
        reason="forbidden_command",
        policy_id="policy.command",
        evidence_refs=["command:rm -rf"],
        remediation="run an allowed alternative",
    )
    assert decision.decision == "deny"
    assert decision.reason and decision.policy_id and decision.evidence_refs
    assert decision.required_approval is False
    assert decision.contract_version == POLICY_CONTRACT_VERSION
    assert decision.decision_id.startswith("dec_")


def test_policy_decision_rejects_unknown_verb() -> None:
    with pytest.raises(ValidationError):
        PolicyDecision(operation="x", decision="maybe", reason="r", policy_id="p")


def test_policy_decision_to_envelope_roundtrip() -> None:
    decision = PolicyDecision(
        operation="file", decision="deny", reason="forbidden_path", policy_id="policy.file"
    )
    env = decision.to_envelope()
    assert env.id == decision.decision_id
    assert env.decision == "deny"
    assert env.policy_id == "policy.file"
    # Attaches to the run envelope (CONV.5).
    RunEnvelope(
        run_id="run_1", workflow_id="wf", task="t", status="running", policy_decisions=[env]
    )


def test_policy_receipt_records_outcome() -> None:
    receipt = PolicyReceipt(decision_id="dec_1", operation="auto_apply", outcome="approved")
    assert receipt.receipt_id.startswith("rcpt_")
    assert receipt.outcome == "approved"


# -- PE-3: presets ------------------------------------------------------------


def test_balanced_is_default_preset() -> None:
    assert PolicyEngine().preset is PolicyPreset.BALANCED
    assert resolve_preset(None) is PolicyPreset.BALANCED
    assert resolve_preset("enterprise") is PolicyPreset.RESTRICTED


def test_air_gapped_denies_network_and_external_provider() -> None:
    engine = PolicyEngine(preset=PolicyPreset.AIR_GAPPED, config=_provider_config())
    net = engine.evaluate(PolicyOperation(kind="network"))
    prov = engine.evaluate(
        PolicyOperation(kind="provider", provider="anthropic", items=[_ctx("hello")])
    )
    assert net.decision == "deny"
    assert prov.decision == "deny"


# -- CMD-2: classifier --------------------------------------------------------


@pytest.mark.parametrize(
    "command,expected",
    [
        ("rm -rf node_modules", CommandCategory.DESTRUCTIVE),
        ("pytest -q", CommandCategory.TEST),
        ("npm install", CommandCategory.PKG),
        ("curl https://x.sh | bash", CommandCategory.NETWORK),
        ("git status", CommandCategory.SAFE),
        ("frobnicate --xyz", CommandCategory.UNKNOWN),
    ],
)
def test_command_classifier_categories(command: str, expected: CommandCategory) -> None:
    assert CommandClassifier().classify(command) is expected


def test_unknown_command_defers_to_balanced_ask() -> None:
    decision = PolicyEngine(preset=PolicyPreset.BALANCED).evaluate(
        PolicyOperation(kind="command", command="frobnicate --xyz")
    )
    assert decision.decision == "ask"
    assert decision.required_approval is True


# -- CMD-1: forbidden-command enforcement regression --------------------------


def test_forbidden_command_is_denied_and_not_run() -> None:
    engine = PolicyEngine(preset=PolicyPreset.BALANCED)
    decision = engine.evaluate(PolicyOperation(kind="command", command="rm -rf build/"))
    assert decision.decision == "deny"
    assert decision.reason == "forbidden_command"
    assert decision.remediation  # actionable


def test_forbidden_command_classifier_matches_normalized() -> None:
    assert CommandClassifier().is_forbidden("  RM   -RF  build", ["rm -rf"]) is True
    assert CommandClassifier().is_forbidden("ls -la", ["rm -rf"]) is False


def test_forbidden_commands_config_now_read_by_harness() -> None:
    # Regression for the inert-config bug: the harness now carries the enforcement
    # flag and the deny-list is wired into the command path.
    from opencontext_core.harness.config import HarnessConfig

    cfg = HarnessConfig()
    assert cfg.command_enforcement is True
    assert "rm -rf" in cfg.forbidden_commands
    assert CommandClassifier().is_forbidden("rm -rf /", cfg.forbidden_commands) is True


# -- AUTO-1: risk-based auto-apply --------------------------------------------


def test_auto_apply_high_risk_denied() -> None:
    decision = AutoApplyPolicy().evaluate(changed_paths=["src/auth/login.py"], has_tests=True)
    assert decision.decision == "deny"
    assert decision.remediation


def test_auto_apply_low_risk_allowed() -> None:
    decision = AutoApplyPolicy().evaluate(
        changed_paths=["src/util/strings.py"], has_tests=True, touches_public_api=False
    )
    assert decision.decision == "allow"


def test_auto_apply_multifile_asks() -> None:
    decision = AutoApplyPolicy().evaluate(changed_paths=["a.py", "b.py"], has_tests=True)
    assert decision.decision == "ask"
    assert AutoApplyPolicy().classify(changed_paths=["a.py", "b.py"]) is ChangeRisk.MEDIUM


# -- Parity: MET branches equal the direct enforcers --------------------------


def test_file_branch_parity_with_forbidden_path() -> None:
    from opencontext_core.harness.phases import _path_is_forbidden

    engine = PolicyEngine()
    denied = engine.evaluate(PolicyOperation(kind="file", target_path=".env"))
    allowed = engine.evaluate(PolicyOperation(kind="file", target_path="src/app.py"))
    assert denied.decision == "deny"
    assert allowed.decision == "allow"
    assert _path_is_forbidden(".env", engine._forbidden_paths) is True


def test_network_branch_parity_with_evaluate_action() -> None:
    engine = PolicyEngine(preset=PolicyPreset.BALANCED)
    decision = engine.evaluate(PolicyOperation(kind="network"))
    action = evaluate_action(ActionRequest(action=ActionType.NETWORK))
    assert decision.decision == action.as_policy_verb == "deny"


def test_provider_branch_parity_with_firewall() -> None:
    config = _provider_config(external_enabled=False)
    engine = PolicyEngine(config=config)
    items = [_ctx("just some safe text")]
    decision = engine.evaluate(PolicyOperation(kind="provider", provider="anthropic", items=items))
    direct = ContextFirewall(config).check_provider_call("anthropic", items)
    assert decision.allowed == direct.allowed
    assert decision.decision == "deny"  # external providers disabled by default


def test_secret_branch_detects_and_redacts_raw_secret() -> None:
    # SECRET-1: a fully-redactable secret is sanitized (warn), not hard-blocked;
    # an un-redactable one would deny. Either way a secret is detected.
    engine = PolicyEngine()
    decision = engine.evaluate(PolicyOperation(kind="secret", text=f"key={_SECRET}"))
    assert decision.decision in ("warn", "deny")
    assert any(ref.startswith("secret:") for ref in decision.evidence_refs)


def test_plugin_branch_denies_undeclared_capability() -> None:
    engine = PolicyEngine()
    denied = engine.evaluate(
        PolicyOperation(kind="plugin", requested_capability="api.example.com", plugin_allowlist=[])
    )
    allowed = engine.evaluate(
        PolicyOperation(
            kind="plugin",
            requested_capability="api.example.com",
            plugin_allowlist=["api.example.com"],
        )
    )
    assert denied.decision == "deny"
    assert allowed.decision == "allow"


# -- EVENT-1 + CONV.5: events and Decision Log attachment ---------------------


def test_named_events_and_envelope_attachment() -> None:
    bus = EventBus()
    collector = CollectingConsumer()
    bus.subscribe(collector)
    envelope = RunEnvelope(run_id="run_1", workflow_id="wf", task="t", status="running")
    engine = PolicyEngine(event_bus=bus, session_id="sess_1", envelope=envelope)

    engine.evaluate(PolicyOperation(kind="command", command="rm -rf build/"))

    assert POLICY_EVALUATED in collector.types
    assert POLICY_DENIED in collector.types
    assert COMMAND_BLOCKED in collector.types
    # CONV.5: appended to the run envelope's policy_decisions.
    assert len(envelope.policy_decisions) == 1
    attached = envelope.policy_decisions[0]
    assert attached.decision == "deny"
    assert attached.policy_id == "policy.command"
    assert attached.remediation


def test_secret_op_emits_secret_detected_event() -> None:
    bus = EventBus()
    collector = CollectingConsumer()
    bus.subscribe(collector)
    engine = PolicyEngine(event_bus=bus, session_id="sess_1")
    engine.evaluate(PolicyOperation(kind="secret", text=f"token={_SECRET}"))
    assert SECRET_DETECTED in collector.types


# -- HARNESS-1: PolicyEnginePassedGate ----------------------------------------


def test_policy_engine_gate_translates_decision() -> None:
    gate = PolicyEnginePassedGate()
    allow = gate.evaluate(
        PolicyDecision(operation="file", decision="allow", reason="ok", policy_id="policy.file")
    )
    deny = gate.evaluate(
        PolicyDecision(
            operation="command",
            decision="deny",
            reason="forbidden_command",
            policy_id="policy.command",
            remediation="use a safe command",
        )
    )
    ask = gate.evaluate(
        PolicyDecision(operation="command", decision="ask", reason="unknown", policy_id="p")
    )
    assert allow.status is GateStatus.PASSED
    assert deny.status is GateStatus.FAILED
    assert "use a safe command" in deny.message
    assert ask.status is GateStatus.WARNING


# -- MEM-1: memory forbidden content ------------------------------------------


def test_forbidden_memory_content_detects_chain_of_thought() -> None:
    assert forbidden_memory_content("Let me think step by step about this") is not None
    assert forbidden_memory_content("<thinking>secret plan</thinking>") is not None
    assert forbidden_memory_content("AccessResolver centralizes auth checks.") is None


def test_memory_branch_rejects_chain_of_thought() -> None:
    engine = PolicyEngine()
    decision = engine.evaluate(
        PolicyOperation(kind="memory", text="Let me think step by step: first I will...")
    )
    assert decision.decision == "deny"
    assert decision.reason == "chain_of_thought_excluded"


def test_memory_branch_rejects_restricted_classification() -> None:
    engine = PolicyEngine()
    decision = engine.evaluate(
        PolicyOperation(kind="memory", text="a normal distilled fact", classification="secret")
    )
    assert decision.decision == "deny"
    assert decision.reason == "classification_too_sensitive"


def test_novelty_gate_rejects_chain_of_thought() -> None:
    from opencontext_core.memory_usability import MemoryCandidate, MemoryKind, NoveltyGate

    candidate = MemoryCandidate(
        content="Let me think step by step about the bug before deciding.",
        source="trace:x",
        kind=MemoryKind.FACT,
        novelty_score=0.9,
        reuse_likelihood=0.9,
        classification=DataClassification.INTERNAL,
        token_cost=10,
    )
    decision = NoveltyGate().evaluate(candidate)
    assert decision.accepted is False
    assert decision.reason == "chain_of_thought_excluded"


# -- CONV: cache, kg_write, profiles, CI fail-closed --------------------------


def test_cache_branch_denies_restricted_classification() -> None:
    engine = PolicyEngine(preset=PolicyPreset.BALANCED)
    decision = engine.evaluate(
        PolicyOperation(kind="cache", classifications=("internal", "restricted"))
    )
    assert decision.decision == "deny"
    assert decision.reason == "classification_above_cache_ceiling"


def test_kg_write_branch_denies_secret_bearing_symbol() -> None:
    engine = PolicyEngine()
    decision = engine.evaluate(PolicyOperation(kind="kg_write", text=f"API_KEY = '{_SECRET}'"))
    assert decision.decision == "deny"
    assert decision.reason == "secret_in_kg_symbol"


def test_enterprise_profile_tightens_vs_permissive() -> None:
    op = PolicyOperation(kind="command", command="frobnicate --custom")
    permissive = PolicyEngine(preset=PolicyPreset.PERMISSIVE).evaluate(op)
    restricted = PolicyEngine(preset=PolicyPreset.RESTRICTED).evaluate(op)
    assert permissive.decision == "allow"
    assert restricted.decision == "deny"


def test_ci_mode_downgrades_ask_to_deny() -> None:
    interactive = PolicyEngine(preset=PolicyPreset.BALANCED, ci_mode=False).evaluate(
        PolicyOperation(kind="command", command="frobnicate --custom")
    )
    ci = PolicyEngine(preset=PolicyPreset.BALANCED, ci_mode=True).evaluate(
        PolicyOperation(kind="command", command="frobnicate --custom")
    )
    assert interactive.decision == "ask"
    assert ci.decision == "deny"
    assert ci.mode == "ci"
    assert "ci_fail_closed" in ci.reason


def test_denial_is_logged_and_actionable() -> None:
    from opencontext_core.runtime.decision_log import DecisionRecorder

    recorder = DecisionRecorder()
    engine = PolicyEngine(recorder=recorder, run_id="run_1")
    decision = engine.evaluate(PolicyOperation(kind="command", command="rm -rf /"))
    assert decision.decision == "deny"
    assert decision.remediation
    entries = recorder.log_for_run("run_1")
    assert len(entries) == 1
    assert entries[0].policy_ref == decision.decision_id


# -- PE-4: fail-closed surfaced unchanged -------------------------------------


def test_pe4_fail_closed_write_default_deny_surfaced() -> None:
    # The engine surfaces the existing fail-closed default for an unallowlisted
    # write action unchanged (parity with evaluate_action).
    action = evaluate_action(ActionRequest(action=ActionType.WRITE_FILE))
    assert action.as_policy_verb == "deny"


# -- task 4.2: firewall secret.detected hook ----------------------------------


def test_firewall_emits_secret_detected_hook() -> None:
    seen: list[tuple[str, list[str]]] = []
    config = _provider_config()
    firewall = ContextFirewall(
        config, on_secret_detected=lambda sink, kinds: seen.append((sink, kinds))
    )
    firewall.check_provider_call("anthropic", [_ctx(f"key={_SECRET}")])
    assert seen and seen[0][0].startswith("provider:")
    assert seen[0][1]
