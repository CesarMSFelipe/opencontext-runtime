"""C14 (pre-condition for C15): source-scan for direct run_oc_flow_cli importers.

After the C15 spine flip, ``run_cmd.py`` routes through RuntimeApi and no longer
imports ``run_oc_flow_cli`` directly. This test documents that invariant and is
written in C14 (before the flip) so the RED → GREEN arc is visible in history.

Allowlist:
- ``oc_flow/cli.py``          — the definition file
- ``mcp/run_dispatcher.py``   — the designated shim (is the only legal caller)
- ``compat/``                 — ledger references

Any production file OUTSIDE the allowlist that imports ``run_oc_flow_cli``
directly is a contract violation: all calls must go through the shim.
"""

from __future__ import annotations

import ast
from pathlib import Path

# The repo root is four parents up from this file:
# tests/architecture/ -> tests/ -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]

# Package roots that count as production code (not tests/).
_PRODUCTION_ROOTS: tuple[Path, ...] = (
    _REPO_ROOT / "packages" / "opencontext_core" / "opencontext_core",
    _REPO_ROOT / "packages" / "opencontext_cli" / "opencontext_cli",
)

# Files that are allowed to import run_oc_flow_cli directly.
_ALLOWLIST: frozenset[str] = frozenset(
    {
        "oc_flow/cli.py",  # the definition
        "mcp/run_dispatcher.py",  # the designated shim (the only legal caller)
    }
)


def _collect_importers(roots: tuple[Path, ...]) -> list[str]:
    """Return all production files that import run_oc_flow_cli outside the allowlist."""
    importers: list[str] = []
    for root in roots:
        for py in sorted(root.rglob("*.py")):
            rel = py.relative_to(root).as_posix()
            if rel in _ALLOWLIST:
                continue
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
            except (SyntaxError, OSError):
                continue
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.ImportFrom)
                    and node.module
                    and "oc_flow" in (node.module or "")
                    and any(alias.name == "run_oc_flow_cli" for alias in node.names)
                ):
                    importers.append(str(py.relative_to(_REPO_ROOT)))
                    break
    return importers


def test_no_direct_run_oc_flow_cli_importers_outside_shim() -> None:
    """No production code outside the designated shim imports run_oc_flow_cli directly.

    C15: run_cmd.py now routes through RuntimeApi — the direct run_oc_flow_cli
    import has been removed from that file. The only legal production importer is
    mcp/run_dispatcher.py (the shim), which is in the allowlist.
    """
    violators = _collect_importers(_PRODUCTION_ROOTS)
    assert violators == [], (
        "The following production files import run_oc_flow_cli outside the shim "
        f"(allowlist: {sorted(_ALLOWLIST)}):\n"
        + "\n".join(f"  {v}" for v in violators)
    )
