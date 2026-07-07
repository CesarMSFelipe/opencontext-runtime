"""Unified Policy Engine (PR-005, layer L3 — Governance).

One canonical :class:`PolicyDecision` and one :class:`PolicyEngine` seam that
delegates to the existing enforcers (firewall, provider policy, action policy,
secret scanner, plugin allowlist, forbidden paths) and adds the genuinely new
governance: presets, command classification + forbidden-command enforcement,
risk-based auto-apply, named policy events, approval receipts, memory
forbidden-content, and cache/KG/CI governance.
"""

from __future__ import annotations

from opencontext_core.policy.auto_apply import AutoApplyPolicy, ChangeRisk
from opencontext_core.policy.commands import CommandCategory, CommandClassifier
from opencontext_core.policy.engine import (
    PolicyEngine,
    PolicyOperation,
    detect_ci,
)
from opencontext_core.policy.events import (
    COMMAND_BLOCKED,
    NETWORK_BLOCKED,
    POLICY_ALLOWED,
    POLICY_APPROVED,
    POLICY_ASK,
    POLICY_DENIED,
    POLICY_EVALUATED,
    POLICY_VIOLATION,
    POLICY_WARNED,
    SECRET_DETECTED,
    emit_policy_events,
    event_types_for,
)
from opencontext_core.policy.memory_content import forbidden_memory_content
from opencontext_core.policy.models import (
    POLICY_CONTRACT_VERSION,
    POLICY_EVENT_FAMILY,
    PolicyDecision,
    PolicyReceipt,
)
from opencontext_core.policy.overlay import PoliciesOverlay
from opencontext_core.policy.presets import (
    DEFAULT_PRESET,
    PRESET_TABLE,
    PolicyPreset,
    PresetPosture,
    posture_for,
    resolve_preset,
)

__all__ = [
    "COMMAND_BLOCKED",
    "DEFAULT_PRESET",
    "NETWORK_BLOCKED",
    "POLICY_ALLOWED",
    "POLICY_APPROVED",
    "POLICY_ASK",
    "POLICY_CONTRACT_VERSION",
    "POLICY_DENIED",
    "POLICY_EVALUATED",
    "POLICY_EVENT_FAMILY",
    "POLICY_VIOLATION",
    "POLICY_WARNED",
    "PRESET_TABLE",
    "SECRET_DETECTED",
    "AutoApplyPolicy",
    "ChangeRisk",
    "CommandCategory",
    "CommandClassifier",
    "PoliciesOverlay",
    "PolicyDecision",
    "PolicyEngine",
    "PolicyOperation",
    "PolicyPreset",
    "PolicyReceipt",
    "PresetPosture",
    "detect_ci",
    "emit_policy_events",
    "event_types_for",
    "forbidden_memory_content",
    "posture_for",
    "resolve_preset",
]
