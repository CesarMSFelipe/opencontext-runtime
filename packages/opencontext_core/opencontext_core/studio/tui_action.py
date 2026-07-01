"""commit-009: TUI start action stub.

A minimal routing helper used by the TUI to decide whether a session
should go through ``RuntimeApi`` (when ``rt-spine`` is on) or through
the legacy harness (default). The full 12-screen TUI ships in
commit-013; this module exists to plumb the flag early so the TUI and
the CLI agree on their routing identity.

Returns the routing label as a string so the rest of the TUI can pick
its path without importing the real implementation. The kwargs are
accepted (and ignored) so call sites match the eventual
``RuntimeApi.start_session`` signature.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core import compat


def start_session(
    *,
    task: str,  # signature parity with RuntimeApi.start_session
    root: Path | str | None = None,  # signature parity
    profile: str = "balanced",  # signature parity
) -> str:
    """Return ``"spine"`` when ``rt-spine`` is on, ``"legacy"`` otherwise.

    The thin wrapper exists so the TUI can flip its routing without a
    structural change once commit-013 wires the real action handler.

    The flag lookup is routed through the ``compat`` module attribute so
    tests can monkey-patch :func:`opencontext_core.compat.is_migrated_flag`
    without touching this module's local imports.
    """
    del task, root, profile  # accepted for signature parity; routing ignores them
    return "spine" if compat.is_migrated_flag("rt-spine") else "legacy"


__all__ = ["start_session"]
