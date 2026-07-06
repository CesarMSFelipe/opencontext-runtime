"""EXE-POLICIES (plan doc 1 §14) — the v2 ``policies:`` yaml section drives real decisions.

The section used to be accepted-but-inert: ``OpenContextConfig.policies`` was an
open mapping with zero consumers, so a user writing the plan's exact yaml got
silently no effect. These tests pin the wiring: each documented key now lands on
the typed setting its enforcement mechanism actually reads (harness approval
gate, executors shell gate, PolicyEngine posture/preset).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from opencontext_core.config import OpenContextConfig, default_config_data, load_config
from opencontext_core.harness.gates import ApprovalRequiredForWritesGate
from opencontext_core.harness.models import GateStatus
from opencontext_core.policy.engine import PolicyEngine, PolicyOperation
from opencontext_core.policy.presets import PolicyPreset

_SECRET = "sk-ant-api03-" + "A" * 80


def _config_with_policies(policies: dict[str, Any]) -> OpenContextConfig:
    data = default_config_data()
    data["policies"] = policies
    return OpenContextConfig.model_validate(data)


def test_doc_policies_yaml_is_not_inert(tmp_path: Path) -> None:
    """EXE-POLICIES: the plan's exact ``policies:`` yaml block takes effect — every
    key resolves onto the setting its enforcing mechanism reads."""
    (tmp_path / "opencontext.yaml").write_text(
        "project:\n  name: demo\n"
        "policies:\n"
        "  writes:\n    require_approval: true\n"
        "  shell:\n    allow: false\n"
        "  network:\n    allow: false\n"
        "  secrets:\n    redact: true\n"
        "  destructive_actions:\n    require_explicit_confirmation: true\n",
        encoding="utf-8",
    )
    config = load_config(tmp_path / "opencontext.yaml")
    # writes.require_approval -> the field the ApplyPhase pre-gate consumes.
    assert config.harness.approval_required_for_writes is True
    # shell.allow -> the executors shell gate.
    assert config.executors.allow_shell is False

    engine = PolicyEngine(config=config, ci_mode=False)
    # shell disabled: every command is refused, even a safe one.
    command = engine.evaluate(PolicyOperation(kind="command", command="ls"))
    assert command.decision == "deny"
    assert command.reason == "shell_disabled"
    # network disabled: the network branch names the policy switch.
    network = engine.evaluate(PolicyOperation(kind="network"))
    assert network.decision == "deny"
    assert network.reason == "network_disabled_by_policy"


def test_writes_require_approval_key_blocks_apply_gate() -> None:
    """EXE-POLICIES: ``policies.writes.require_approval: true`` flips the harness
    approval setting, and the ApplyPhase pre-gate then blocks unapproved writes.

    Deviation note: the global default stays ``False`` (opt-in) — flipping the
    default would break every existing zero-config run; the documented yaml key
    is the supported way to opt in.
    """
    config = _config_with_policies({"writes": {"require_approval": True}})
    assert config.harness.approval_required_for_writes is True
    gate = ApprovalRequiredForWritesGate().evaluate(
        approval_required=config.harness.approval_required_for_writes, approved=False
    )
    assert gate.status == GateStatus.FAILED

    untouched = OpenContextConfig.model_validate(default_config_data())
    assert untouched.harness.approval_required_for_writes is False


def test_shell_allow_key_is_the_shell_switch() -> None:
    """EXE-POLICIES: ``policies.shell.allow`` overlays ``executors.allow_shell``
    and, when false, disables the engine command path entirely."""
    enabled = _config_with_policies({"shell": {"allow": True}})
    assert enabled.executors.allow_shell is True

    disabled = _config_with_policies({"shell": {"allow": False}})
    assert disabled.executors.allow_shell is False
    decision = PolicyEngine(config=disabled, ci_mode=False).evaluate(
        PolicyOperation(kind="command", command="pytest -q")
    )
    assert decision.decision == "deny"
    assert decision.reason == "shell_disabled"
    assert decision.remediation  # actionable


def test_network_allow_false_denies_network_category_command() -> None:
    """EXE-POLICIES: ``policies.network.allow: false`` denies network-category
    commands even under the permissive preset (which would otherwise ask)."""
    data = default_config_data()
    data["policy"] = {"preset": "permissive"}
    baseline = PolicyEngine(config=OpenContextConfig.model_validate(data), ci_mode=False)
    asked = baseline.evaluate(PolicyOperation(kind="command", command="curl https://example.com"))
    assert asked.decision == "ask"

    data["policies"] = {"network": {"allow": False}}
    engine = PolicyEngine(config=OpenContextConfig.model_validate(data), ci_mode=False)
    denied = engine.evaluate(PolicyOperation(kind="command", command="curl https://example.com"))
    assert denied.decision == "deny"


def test_secrets_redact_key_drives_secret_branch() -> None:
    """EXE-POLICIES: ``policies.secrets.redact`` selects redact-and-warn versus
    hard deny for a raw secret at the secret sink."""
    redacting = _config_with_policies({"secrets": {"redact": True}})
    warn = PolicyEngine(config=redacting, ci_mode=False).evaluate(
        PolicyOperation(kind="secret", text=f"key = '{_SECRET}'")
    )
    assert warn.decision == "warn"
    assert warn.reason == "secret_redacted"

    strict = _config_with_policies({"secrets": {"redact": False}})
    deny = PolicyEngine(config=strict, ci_mode=False).evaluate(
        PolicyOperation(kind="secret", text=f"key = '{_SECRET}'")
    )
    assert deny.decision == "deny"
    assert deny.reason == "raw_secret_detected"


def test_destructive_confirmation_key_changes_decision() -> None:
    """EXE-POLICIES: ``policies.destructive_actions.require_explicit_confirmation``
    toggles ask/allow for destructive-but-not-forbidden commands; a deny preset is
    never weakened by the overlay."""
    required = _config_with_policies(
        {"destructive_actions": {"require_explicit_confirmation": True}}
    )
    ask = PolicyEngine(config=required, ci_mode=False).evaluate(
        PolicyOperation(kind="command", command="git reset --hard HEAD~3")
    )
    assert ask.decision == "ask"
    assert ask.required_approval is True

    waived = _config_with_policies(
        {"destructive_actions": {"require_explicit_confirmation": False}}
    )
    allow = PolicyEngine(config=waived, ci_mode=False).evaluate(
        PolicyOperation(kind="command", command="git reset --hard HEAD~3")
    )
    assert allow.decision == "allow"
    assert allow.required_approval is False

    restricted = _config_with_policies(
        {"preset": "restricted", "destructive_actions": {"require_explicit_confirmation": False}}
    )
    still_denied = PolicyEngine(config=restricted, ci_mode=False).evaluate(
        PolicyOperation(kind="command", command="git reset --hard HEAD~3")
    )
    assert still_denied.decision == "deny"


def test_policies_preset_overlay_reaches_engine() -> None:
    """EXE-POLICIES: ``policies.preset`` (the v2 overlay over ``policy``) resolves
    the engine preset instead of being ignored."""
    config = _config_with_policies({"preset": "restricted"})
    engine = PolicyEngine(config=config, ci_mode=False)
    assert engine.preset is PolicyPreset.RESTRICTED
    decision = engine.evaluate(PolicyOperation(kind="command", command="frobnicate --xyz"))
    assert decision.decision == "deny"  # restricted denies unknown commands


def test_absent_policies_section_changes_nothing() -> None:
    """EXE-POLICIES: an absent/empty ``policies:`` section leaves every default
    untouched (the overlay is strictly additive)."""
    config = OpenContextConfig.model_validate(default_config_data())
    assert config.harness.approval_required_for_writes is False
    assert config.executors.allow_shell is False
    engine = PolicyEngine(config=config, ci_mode=False)
    assert engine.preset is PolicyPreset.BALANCED
    decision = engine.evaluate(PolicyOperation(kind="command", command="ls"))
    assert decision.decision == "allow"
