"""Adapter protocol + registry: the single Legacy <-> vNext boundary (CL-001..004).

Each ``LegacyAdapter`` wraps one legacy entrypoint and exposes two routes: ``adapt``
(legacy projected onto its vNext contract) and ``legacy`` (the untouched legacy
path). The registry resolves, per subsystem, which route a caller takes based on
the subsystem's ``runtime.*`` flag -- so callers never branch on legacy-vs-vNext.

A flag may only route to ``adapt`` once its parity check has passed (CL-012); the
registry rejects the flip otherwise.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from opencontext_core.compat.parity import ParityGateError


@runtime_checkable
class LegacyAdapter(Protocol):
    """A seam that wraps one legacy entrypoint behind its gating flag."""

    subsystem: str  # "runtime" | "workflow_registry" | "provider_gateway" | ...
    flag: str  # gating runtime.* flag, e.g. "runtime.registry_enabled"

    def adapt(self, *args: Any, **kwargs: Any) -> Any:
        """Route the call through the vNext contract."""
        ...

    def legacy(self, *args: Any, **kwargs: Any) -> Any:
        """Route the call through the untouched legacy path."""
        ...


class AdapterRegistry:
    """Maps each subsystem to its ``LegacyAdapter`` and resolves the active route."""

    def __init__(self) -> None:
        self._adapters: dict[str, LegacyAdapter] = {}

    def register(self, adapter: LegacyAdapter) -> None:
        """Register *adapter* under its subsystem (one adapter per subsystem)."""
        if adapter.subsystem in self._adapters:
            raise ValueError(f"adapter already registered for subsystem: {adapter.subsystem}")
        self._adapters[adapter.subsystem] = adapter

    def get(self, subsystem: str) -> LegacyAdapter | None:
        """Return the adapter registered for *subsystem*, if any."""
        return self._adapters.get(subsystem)

    def subsystems(self) -> list[str]:
        """List the registered subsystems."""
        return sorted(self._adapters)

    def resolve(
        self,
        subsystem: str,
        *,
        flag_enabled: bool,
        parity_passed: bool = True,
    ) -> Callable[..., Any] | None:
        """Return the bound route (``adapt`` or ``legacy``) for *subsystem*.

        With ``flag_enabled`` the vNext ``adapt`` route is returned -- but only if
        ``parity_passed``; otherwise the flip is rejected with ``ParityGateError``
        and the legacy path remains authoritative (CL-012). With the flag off the
        ``legacy`` route is returned. Returns ``None`` for an unregistered subsystem.
        """
        adapter = self._adapters.get(subsystem)
        if adapter is None:
            return None
        if flag_enabled:
            if not parity_passed:
                raise ParityGateError(
                    f"cannot route {subsystem} to vNext: parity not proven (flag {adapter.flag})"
                )
            return adapter.adapt
        return adapter.legacy
