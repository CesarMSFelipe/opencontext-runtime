"""Execution boundary for untrusted plugin code (PR-015, SPEC PR-015-SANDBOX).

Two layers:

1. :class:`CapabilityBroker` — a deny-by-default broker that gates every
   restricted operation (filesystem/network/command/provider/KG/memory) through
   the plugin's declared allowlist (``PluginRegistry.is_allowed``) AND the PR-005
   Policy Engine (``actions/policy.evaluate_action``). A plugin cannot self-grant:
   an undeclared capability is denied, and a declared one still routes through
   policy (e.g. command execution still requires approval).

2. :func:`run_sandboxed` — runs the plugin entry under an import guard (private
   Runtime modules are blocked; only the public ``plugins.contracts`` surface is
   importable) and reports whether OS-level isolation is present.

HONEST CEILING (NOTE): a true OS sandbox (seccomp/landlock/namespaces) is
Linux-only and out of scope for v1. The portable floor implemented here is a
capability broker + an import guard executed in-process. This raises the bar and
makes a policy-bypass attempt observable, but an adversarial in-process plugin can
still reach already-imported modules via ``sys.modules``; it is NOT a security
boundary against malicious code. When OS isolation is unavailable the activation
degrades LOUDLY (``degraded=True`` + a recorded warning) rather than silently
running unrestricted (SPEC PR-015-SANDBOX scenario 2).
"""

from __future__ import annotations

import hashlib
import importlib.util
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from opencontext_core.actions.policy import (
    ActionPolicyDecision,
    ActionRequest,
    ActionType,
    ApprovalLevel,
    evaluate_action,
)
from opencontext_core.config import SecurityMode

_log = logging.getLogger(__name__)

# The only public surface a sandboxed plugin may import from the runtime.
_ALLOWED_IMPORT_PREFIXES = ("opencontext_core.plugins.contracts",)

# Map a plugin capability onto the Policy Engine action class it routes through.
_CAPABILITY_ACTIONS: dict[str, ActionType] = {
    "read": ActionType.READ_FILE,
    "write": ActionType.WRITE_FILE,
    "network": ActionType.NETWORK,
    "mcp": ActionType.MCP_TOOL,
    "command": ActionType.CALL_TOOL,
    "provider": ActionType.CALL_LLM,
    "kg_write": ActionType.WRITE_FILE,
    "memory_write": ActionType.WRITE_FILE,
}
_WRITE_LIKE = {"write", "kg_write", "memory_write"}


class PluginSandboxViolation(ImportError):
    """Raised when a sandboxed plugin imports a private Runtime module."""


class CapabilityBroker:
    """Deny-by-default capability broker routing through the Policy Engine.

    A capability is allowed only when BOTH the plugin's declared allowlist permits
    the value AND the Policy Engine allows the mapped action. This is the structural
    guarantee that a plugin cannot bypass policy or self-grant (SPEC PR-015-ISOLATION).
    """

    def __init__(
        self,
        registry: Any,
        plugin_name: str,
        *,
        security_mode: SecurityMode = SecurityMode.PRIVATE_PROJECT,
    ) -> None:
        self._registry = registry
        self._name = plugin_name
        self._mode = security_mode

    def check(self, capability: str, value: str, *, approved: bool = False) -> ActionPolicyDecision:
        """Return the policy decision for a plugin's requested capability use."""
        action = _CAPABILITY_ACTIONS.get(capability)
        if action is None:
            return ActionPolicyDecision(
                action=ActionType.CALL_TOOL,
                decision=ApprovalLevel.DENY,
                allowed=False,
                requires_approval=False,
                reason="unknown_capability",
            )
        perms_ok = bool(self._registry.is_allowed(self._name, capability, value))
        if not perms_ok:
            # Deny-by-default: the plugin never declared this capability/value.
            return ActionPolicyDecision(
                action=action,
                decision=ApprovalLevel.DENY,
                allowed=False,
                requires_approval=False,
                reason="capability_not_declared",
            )
        request = ActionRequest(
            action=action,
            explicitly_allowlisted=True,
            approved=approved,
            sandbox_enabled=capability in _WRITE_LIKE,
        )
        return evaluate_action(request, security_mode=self._mode)

    def allowed(self, capability: str, value: str, *, approved: bool = False) -> bool:
        """Convenience: True only when the action may proceed now."""
        return self.check(capability, value, approved=approved).allowed


@dataclass
class SandboxResult:
    """Outcome of a sandboxed plugin activation."""

    ok: bool
    degraded: bool
    reason: str
    plugin: Any = None
    warnings: list[str] = field(default_factory=list)


def os_isolation_available(probe: Callable[[], bool] | None = None) -> bool:
    """Whether OS-level process isolation is available.

    Returns False by default (the honest portable floor — no seccomp/landlock
    wiring in v1). A ``probe`` may override for tests or a future OS-sandbox
    backend. Kept as a single decision point so the degrade-loud path is testable.
    """
    if probe is not None:
        return bool(probe())
    return False


@contextmanager
def restricted_import() -> Iterator[None]:
    """Block a plugin from importing private Runtime modules during exec.

    Installs a ``sys.meta_path`` finder that refuses fresh imports of
    ``opencontext_core.*`` except the public ``plugins.contracts`` surface. See
    the module docstring for the honest ceiling: this blocks *new* private imports
    and makes a bypass attempt observable, but is not airtight against adversarial
    in-process code.
    """
    import sys

    class _PrivateImportBlocker:
        def find_spec(self, name: str, path: Any = None, target: Any = None) -> None:
            if name == "opencontext_core" or name.startswith("opencontext_core."):
                if not any(name == p or name.startswith(p + ".") for p in _ALLOWED_IMPORT_PREFIXES):
                    raise PluginSandboxViolation(
                        f"plugin import of private runtime module blocked: {name}"
                    )
            return None  # defer to the normal finders

    blocker = _PrivateImportBlocker()
    sys.meta_path.insert(0, blocker)
    try:
        yield
    finally:
        try:
            sys.meta_path.remove(blocker)
        except ValueError:
            pass


def verify_entry_checksum(module_path: Path, declared: str) -> bool:
    """Return True when ``module_path`` matches a ``sha256:`` declared checksum.

    An empty/absent declaration is treated as unverified-but-permitted (the caller
    logs the gap); a declared checksum that mismatches returns False (tamper).
    """
    if not declared or not declared.startswith("sha256:"):
        return True
    actual = hashlib.sha256(module_path.read_bytes()).hexdigest()
    return actual == declared[len("sha256:") :]


def run_sandboxed(
    plugin_dir: Path,
    *,
    entry_point: str = "plugin.py",
    plugin_name: str,
    entry_checksum: str = "",
    isolation_probe: Callable[[], bool] | None = None,
) -> SandboxResult:
    """Execute a plugin entry under the capability/import boundary.

    Verifies the entry checksum (tamper-refuse), executes the module under the
    import guard, and reports degradation when OS isolation is unavailable. Never
    raises: a failure is returned as ``ok=False`` so the lifecycle stays isolated.
    """
    warnings: list[str] = []
    module_path = plugin_dir / entry_point
    if not module_path.exists():
        return SandboxResult(ok=False, degraded=True, reason="entry_point_missing")

    if not verify_entry_checksum(module_path, entry_checksum):
        return SandboxResult(ok=False, degraded=True, reason="entry_checksum_mismatch")

    isolated = os_isolation_available(isolation_probe)
    degraded = not isolated
    if degraded:
        msg = (
            f"OS process isolation unavailable; plugin {plugin_name!r} runs under "
            "capability broker + import guard only (deny-by-default)."
        )
        _log.warning(msg)
        warnings.append("sandbox_unavailable")

    try:
        spec = importlib.util.spec_from_file_location(
            f"opencontext_plugin_{plugin_name}", str(module_path)
        )
        if spec is None or spec.loader is None:
            return SandboxResult(
                ok=False, degraded=degraded, reason="spec_load_failed", warnings=warnings
            )
        module = importlib.util.module_from_spec(spec)
        with restricted_import():
            spec.loader.exec_module(module)
        plugin_class = getattr(module, "OpenContextPlugin", None)
        plugin = plugin_class() if plugin_class is not None else module
        reason = "sandbox_unavailable_degraded" if degraded else "sandboxed"
        return SandboxResult(
            ok=True, degraded=degraded, reason=reason, plugin=plugin, warnings=warnings
        )
    except Exception as exc:  # isolation: a crashing plugin must not abort the runtime
        return SandboxResult(
            ok=False,
            degraded=degraded,
            reason=f"activation_failed: {exc}",
            warnings=warnings,
        )
