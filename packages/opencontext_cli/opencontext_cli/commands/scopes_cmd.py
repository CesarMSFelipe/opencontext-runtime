"""Scope hierarchy commands: product / workspace / agents.

INSTALL_UNINSTALL_CONTRACT maps three ownership scopes onto real commands.
These top-level commands make that mapping first-class while staying THIN:
each subcommand builds the delegate's namespace and calls the same handler the
flat command uses — no scope logic is duplicated here.

| Scope       | install            | status                 | uninstall                     |
|-------------|--------------------|------------------------|-------------------------------|
| `product`   | register HOME      | global manifest +      | `uninstall --scope global`    |
|             | manifest + guidance| version, report-only   |                               |
| `workspace` | `install <root>`   | `status <root>`        | `uninstall --scope workspace` |
| `agents`    | `setup [AGENT...]` | `capabilities`         | `uninstall [AGENT...]`        |
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from opencontext_core.dx.console_styles import console

# Package-manager commands that own the product install; the uninstall command
# manages agent config and state, never the distribution itself.
_PRODUCT_GUIDANCE = [
    "pipx install opencontext-cli",
    "pip install opencontext-cli",
    "pipx upgrade opencontext-cli  (or: opencontext upgrade)",
]


def _uninstall_namespace(args: Any, *, scope: str, purge: bool) -> argparse.Namespace:
    """The exact namespace ``handle_uninstall`` expects (uninstall parser shape)."""
    return argparse.Namespace(
        agents=list(getattr(args, "agents", []) or []),
        all_agents=getattr(args, "all_agents", False),
        scope=scope,
        yes=getattr(args, "yes", False),
        json=getattr(args, "json", False),
        dry_run=getattr(args, "dry_run", False),
        root=getattr(args, "root", "."),
        purge=purge,
        full=False,
        verify=getattr(args, "verify", False),
        global_state=False,
    )


# ---------------------------------------------------------------------------
# product — the OpenContext installation itself
# ---------------------------------------------------------------------------


def add_product_parser(subparsers: Any) -> None:
    """Add the ``product`` scope command parser."""
    parser = subparsers.add_parser(
        "product",
        help="Product scope: the OpenContext installation itself (preview).",
        description=(
            "Manage the product scope from INSTALL_UNINSTALL_CONTRACT: the OpenContext "
            "binary plus HOME state. install registers the product manifest under HOME "
            "(the package manager owns the distribution itself); status is report-only; "
            "uninstall delegates to `uninstall --scope global`."
        ),
    )
    sub = parser.add_subparsers(dest="product_command", required=True)
    install = sub.add_parser(
        "install", help="Register the product manifest + how to (re)install the package."
    )
    install.add_argument("--json", action="store_true", help="Emit JSON.")
    status = sub.add_parser("status", help="Product install status: global manifest + version.")
    status.add_argument("--json", action="store_true", help="Emit JSON.")
    _add_scope_uninstall_args(
        sub.add_parser("uninstall", help="Remove HOME-level state (uninstall --scope global).")
    )


def handle_product(args: Any) -> None:
    """Dispatch ``product`` subcommands."""
    verb = args.product_command
    if verb == "uninstall":
        from opencontext_cli.commands.uninstall_cmd import handle_uninstall

        handle_uninstall(
            _uninstall_namespace(args, scope="global", purge=getattr(args, "purge", False))
        )
        return

    from opencontext_cli.commands.uninstall_cmd import _detect_install_methods
    from opencontext_cli.main import __version__
    from opencontext_cli.output import envelope

    install_methods = _detect_install_methods()
    if verb == "install":
        # A machine running this code IS installed; installing or reinstalling
        # the distribution stays the package manager's job (guidance below).
        # What this command DOES own is registering the product-scope manifest
        # under HOME (INST-001) so status/uninstall are manifest-driven.
        manifest_path = Path.home() / ".opencontext" / "oc-manifest.json"
        manifest_registered = False
        manifest_error: str | None = None
        try:
            from opencontext_core.paths.install_manifest import write_product_manifest

            write_product_manifest(product_version=__version__)
            manifest_registered = True
        except Exception as exc:
            manifest_error = str(exc)
        payload = envelope(
            "product.install.v1",
            {
                "status": "passed",
                "installed": True,
                "version": __version__,
                "install_methods": install_methods,
                "guidance": list(_PRODUCT_GUIDANCE),
                "manifest_registered": manifest_registered,
                "manifest_path": str(manifest_path),
                "manifest_error": manifest_error,
            },
        )
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2))
            return
        console.header("Product Install")
        console.success(f"OpenContext {__version__} is installed.")
        for method in install_methods:
            console.dim(f"  {method['method']}: {method['location']}")
        if manifest_registered:
            console.print(f"Registered product manifest: {manifest_path}")
        else:
            console.dim(f"  product manifest not registered: {manifest_error}")
        console.print("To (re)install or upgrade, use the package manager:")
        for hint in _PRODUCT_GUIDANCE:
            console.dim(f"  {hint}")
        return

    if verb == "status":
        from opencontext_core.paths import read_manifest

        manifest = read_manifest(Path.home() / ".opencontext")
        payload = envelope(
            "product.status.v1",
            {
                "status": "passed",
                "version": __version__,
                "manifest_present": manifest is not None,
                "manifest": manifest,
                "install_methods": install_methods,
            },
        )
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2))
            return
        console.header("Product Status")
        console.print(f"  version: {__version__}")
        console.print(f"  global manifest: {'present' if manifest else 'absent'}")
        for method in install_methods:
            console.dim(f"  {method['method']}: {method['location']}")
        return

    _unreachable(verb)


# ---------------------------------------------------------------------------
# workspace — per-repo state
# ---------------------------------------------------------------------------


def add_workspace_parser(subparsers: Any) -> None:
    """Add the ``workspace`` scope command parser."""
    parser = subparsers.add_parser(
        "workspace",
        help="Workspace scope: this repo's OpenContext state (preview).",
        description=(
            "Manage the workspace scope from INSTALL_UNINSTALL_CONTRACT: per-repo state "
            "(.opencontext/, opencontext.yaml, indexes, runs, memory). init/install "
            "delegate to `install <root>`, status to `status <root>`, uninstall to "
            "`uninstall --scope workspace`."
        ),
    )
    sub = parser.add_subparsers(dest="workspace_command", required=True)
    for alias in ("init", "install"):
        p = sub.add_parser(alias, help="Set up this workspace (delegates to `install <root>`).")
        p.add_argument("root", nargs="?", default=".", help="Project root.")
        p.add_argument("--yes", "-y", action="store_true", help="Skip confirmations.")
        p.add_argument("--json", action="store_true", help="Emit JSON.")
        p.add_argument("--dry-run", action="store_true", help="Preview without changes.")
    status = sub.add_parser("status", help="Workspace status (delegates to `status <root>`).")
    status.add_argument("root", nargs="?", default=".", help="Project root.")
    status.add_argument("--json", action="store_true", help="Emit JSON.")
    uninstall = sub.add_parser(
        "uninstall", help="Remove workspace state (uninstall --scope workspace)."
    )
    _add_scope_uninstall_args(uninstall)


def handle_workspace(args: Any) -> None:
    """Dispatch ``workspace`` subcommands."""
    verb = args.workspace_command
    if verb in ("init", "install"):
        from opencontext_cli.main import _install

        _install(args)
        return
    if verb == "status":
        from opencontext_cli.main import _status

        sys.exit(_status(getattr(args, "root", "."), json_output=getattr(args, "json", False)))
    if verb == "uninstall":
        from opencontext_cli.commands.uninstall_cmd import handle_uninstall

        handle_uninstall(
            _uninstall_namespace(args, scope="workspace", purge=getattr(args, "purge", False))
        )
        return
    _unreachable(verb)


# ---------------------------------------------------------------------------
# agents — agent client config
# ---------------------------------------------------------------------------


def add_agents_parser(subparsers: Any) -> None:
    """Add the ``agents`` scope command parser."""
    parser = subparsers.add_parser(
        "agents",
        help="Agents scope: AI agent client config (preview).",
        description=(
            "Manage the agents scope from INSTALL_UNINSTALL_CONTRACT: MCP entries and "
            "managed instruction blocks in agent clients. install delegates to "
            "`setup [AGENT...]`, status to `capabilities`, uninstall to "
            "`uninstall [AGENT...]` (agent config only, no state purge)."
        ),
    )
    sub = parser.add_subparsers(dest="agents_command", required=True)
    install = sub.add_parser("install", help="Configure agent(s) (delegates to `setup`).")
    install.add_argument("agents", nargs="*", metavar="AGENT", help="Agent id(s) to configure.")
    install.add_argument("--all", dest="all_agents", action="store_true", help="Every known agent.")
    install.add_argument(
        "--scope",
        choices=["local", "global"],
        default="local",
        help="Where the agent config is written (default: local).",
    )
    install.add_argument("--yes", "-y", action="store_true", help="Skip confirmations.")
    install.add_argument("--json", action="store_true", help="Emit JSON.")
    install.add_argument("--dry-run", action="store_true", help="Preview without changes.")
    install.add_argument("--root", default=".", help="Project root.")
    status = sub.add_parser("status", help="Agent capability matrix (delegates to `capabilities`).")
    status.add_argument("agent_id", nargs="?", default=None, help="Optional: one client to show.")
    status.add_argument("--json", action="store_true", help="Emit JSON.")
    uninstall = sub.add_parser(
        "uninstall", help="Remove managed agent config (delegates to `uninstall`)."
    )
    uninstall.add_argument("agents", nargs="*", metavar="AGENT", help="Agent id(s) to remove from.")
    uninstall.add_argument(
        "--all", dest="all_agents", action="store_true", help="Every known agent."
    )
    uninstall.add_argument("--yes", "-y", action="store_true", help="Skip confirmation.")
    uninstall.add_argument("--json", action="store_true", help="Emit JSON.")
    uninstall.add_argument("--dry-run", action="store_true", help="Preview without changes.")
    uninstall.add_argument("--root", default=".", help="Project root.")


def handle_agents(args: Any) -> None:
    """Dispatch ``agents`` subcommands."""
    verb = args.agents_command
    if verb == "install":
        from opencontext_cli.commands.setup_cmd import handle_setup

        handle_setup(args)
        return
    if verb == "status":
        from opencontext_cli.commands.capabilities_cmd import handle_capabilities

        handle_capabilities(args)
        return
    if verb == "uninstall":
        from opencontext_cli.commands.uninstall_cmd import handle_uninstall

        # Agent-config removal only: never purge workspace/HOME state from here.
        handle_uninstall(_uninstall_namespace(args, scope="workspace", purge=False))
        return
    _unreachable(verb)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _add_scope_uninstall_args(parser: argparse.ArgumentParser) -> None:
    """Shared flags for the scoped uninstall delegations."""
    parser.add_argument("--purge", action="store_true", help="Also delete managed state paths.")
    parser.add_argument(
        "--verify", action="store_true", help="Rescan for managed residue after removal."
    )
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation.")
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes.")
    parser.add_argument("--root", default=".", help="Project root.")


def _unreachable(verb: Any) -> None:
    raise SystemExit(f"Unreachable: unknown scope verb '{verb}'")
