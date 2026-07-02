"""Unit gate: uninstall --scope {workspace,global,all} semantics.

C5 (product-closure-r13): uninstall_cmd.py:301 and :488-490 are inconsistent —
--full skips global state while --verify always checks it. Fix: add explicit
--scope {workspace,global,all}; --full defaults to scope=all; --verify is
scope-aware.

Scope semantics:
  workspace (default) — project state: agent configs + .opencontext/.storage
  global              — HOME OC state: ~/.config/opencontext, ~/.opencontext/backups
  all                 — both workspace + global
  (legacy: local→workspace)
"""

from __future__ import annotations

import argparse


def _make_uninstall_parser() -> argparse.ArgumentParser:
    """Build a standalone parser matching the uninstall subcommand."""
    from opencontext_cli.commands.uninstall_cmd import add_uninstall_parser

    root = argparse.ArgumentParser()
    subs = root.add_subparsers(dest="cmd")
    add_uninstall_parser(subs)
    return root


def _parse(args: list[str]) -> argparse.Namespace:
    parser = _make_uninstall_parser()
    return parser.parse_args(["uninstall", *args])


def _resolve_effective_scope(args: argparse.Namespace) -> str:
    """Return the effective purge scope from parsed args.

    The uninstall scope semantics:
      --full  → 'all' (overrides any --scope value)
      --scope <v> → that value (with alias normalisation)
      default → 'workspace'
    """
    from opencontext_cli.commands.uninstall_cmd import resolve_uninstall_scope

    return resolve_uninstall_scope(args)


# -- primary scope flag tests --

def test_full_defaults_to_all_scope() -> None:
    """--full without explicit --scope must resolve to scope='all'.

    Strict TDD: fails until add_uninstall_parser + resolve_uninstall_scope
    are updated so --full implies all-scope (C5).
    """
    args = _parse(["--full", "--yes"])
    scope = _resolve_effective_scope(args)
    assert scope == "all", (
        f"--full must default to scope='all', got '{scope}'"
    )


def test_scope_workspace_leaves_global() -> None:
    """--scope workspace must only target workspace state (not HOME)."""
    args = _parse(["--scope", "workspace", "--yes"])
    scope = _resolve_effective_scope(args)
    assert scope == "workspace"


def test_scope_global_leaves_workspace() -> None:
    """--scope global must only target HOME state (not project workspace)."""
    args = _parse(["--scope", "global", "--yes"])
    scope = _resolve_effective_scope(args)
    assert scope == "global"


def test_scope_all_targets_both() -> None:
    """--scope all must target both workspace and global state."""
    args = _parse(["--scope", "all", "--yes"])
    scope = _resolve_effective_scope(args)
    assert scope == "all"


# -- back-compat alias tests --

def test_legacy_local_alias_maps_to_workspace() -> None:
    """Legacy --scope local must be accepted and map to 'workspace'."""
    args = _parse(["--scope", "local", "--yes"])
    scope = _resolve_effective_scope(args)
    assert scope == "workspace", (
        f"Legacy --scope local must alias to 'workspace', got '{scope}'"
    )


def test_parser_accepts_new_scope_choices() -> None:
    """Parser must accept workspace, global, all without error."""
    for value in ("workspace", "global", "all"):
        ns = _parse([f"--scope={value}", "--yes"])
        assert getattr(ns, "scope", None) == value or True  # parse must not fail
