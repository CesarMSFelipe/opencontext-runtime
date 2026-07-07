"""v2 ``policies:`` overlay — typed reader for the documented policies section.

The plan (doc 1 §14) documents a ``policies:`` yaml section (writes/shell/
network/secrets/destructive_actions). ``OpenContextConfig.policies`` accepted it
as an open mapping, but no enforcement path consumed it — a user writing the
documented yaml got silently no effect. This module is the single typed reader
that wires each key to its real enforcing mechanism:

- ``writes.require_approval``  -> ``harness.approval_required_for_writes``
  (applied by config resolution; consumed by the ApplyPhase approval pre-gate)
- ``shell.allow``              -> ``executors.allow_shell`` (config resolution)
  and a total command gate in the PolicyEngine + harness test-runner (EXE-002)
- ``network.allow``            -> the engine's network posture/branch
- ``secrets.redact``           -> the engine's secret-branch redaction posture
- ``destructive_actions.require_explicit_confirmation``
                               -> the engine's destructive-command verb (EXE-005)
- ``preset``                   -> the engine preset (overlay over ``policy.preset``)

Every field is ``None`` when its key is absent, and an absent key changes
nothing — the overlay is strictly additive over preset/config defaults.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict

from opencontext_core.policy.presets import PresetPosture


def _read_bool(section: Any, key: str) -> bool | None:
    """Return ``section[key]`` when it is a real boolean, else ``None``."""
    if isinstance(section, Mapping):
        value = section.get(key)
        if isinstance(value, bool):
            return value
    return None


class PoliciesOverlay(BaseModel):
    """Typed view of the v2 ``policies:`` section (``None`` = key absent)."""

    model_config = ConfigDict(extra="forbid")

    preset: str | None = None
    writes_require_approval: bool | None = None
    shell_allow: bool | None = None
    network_allow: bool | None = None
    secrets_redact: bool | None = None
    destructive_require_confirmation: bool | None = None

    @classmethod
    def from_mapping(cls, policies: Mapping[str, Any] | None) -> PoliciesOverlay:
        """Parse the raw ``policies:`` mapping; unknown/invalid keys are ignored."""
        if not isinstance(policies, Mapping):
            return cls()
        raw_preset = policies.get("preset")
        preset = raw_preset if isinstance(raw_preset, str) and raw_preset.strip() else None
        return cls(
            preset=preset,
            writes_require_approval=_read_bool(policies.get("writes"), "require_approval"),
            shell_allow=_read_bool(policies.get("shell"), "allow"),
            network_allow=_read_bool(policies.get("network"), "allow"),
            secrets_redact=_read_bool(policies.get("secrets"), "redact"),
            destructive_require_confirmation=_read_bool(
                policies.get("destructive_actions"), "require_explicit_confirmation"
            ),
        )

    def apply_to_posture(self, posture: PresetPosture) -> PresetPosture:
        """Return *posture* with the posture-mapped overlay keys applied.

        A preset ``deny`` verb is never weakened: the overlay can tighten a
        category (``ask``/``allow`` -> ``deny``, ``allow`` -> ``ask``) or relax
        an ``ask`` it explicitly owns, but a fail-closed preset stays closed.
        """
        updates: dict[str, Any] = {}
        if self.network_allow is False:
            updates["network"] = "deny"
        elif self.network_allow is True and posture.network == "ask":
            updates["network"] = "allow"
        if self.secrets_redact is not None:
            updates["redact_secrets"] = self.secrets_redact
        if self.destructive_require_confirmation is True:
            if posture.destructive_command == "allow":
                updates["destructive_command"] = "ask"
        elif self.destructive_require_confirmation is False:
            if posture.destructive_command == "ask":
                updates["destructive_command"] = "allow"
        if not updates:
            return posture
        return posture.model_copy(update=updates)
