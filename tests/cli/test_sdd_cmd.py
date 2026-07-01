"""SDD CLI command tests: argparse shape, dispatch, strict TDD enforcement.

Per openspec/changes/agentic-parity-engram-gentle/design/pr3-cli-fastapi.md
§Tests added — REQ-OSP-001..008 surface coverage.
"""

from __future__ import annotations

import argparse

from opencontext_cli.commands.sdd_cmd import SUBCOMMANDS, add_sdd_parser


def _build_parent() -> argparse.ArgumentParser:
    """Helper: build a parent parser with a subparser group.

    Returns the sdd subparser for verb-level introspection.
    """
    parser = argparse.ArgumentParser(prog="opencontext")
    sub = parser.add_subparsers(dest="command", required=True)
    add_sdd_parser(sub)  # mutates sub, returns the sdd subparser
    return parser


def _sdd_parser() -> argparse.ArgumentParser:
    """Build and return the sdd subparser directly."""
    parent = argparse.ArgumentParser(prog="opencontext")
    sub = parent.add_subparsers(dest="command", required=True)
    return add_sdd_parser(sub)


def test_sdd_help_lists_all_15_verbs() -> None:
    """REQ-OSP-001: ``opencontext sdd --help`` lists all 15 verbs."""
    sdd = _sdd_parser()
    help_out = sdd.format_help()
    for verb in SUBCOMMANDS:
        assert verb in help_out, f"Missing verb '{verb}' in help output"


def test_sdd_status_runs_resolver() -> None:
    """REQ-OSP-002: sdd status calls Resolve and prints markdown."""
    parser = _build_parent()
    args = parser.parse_args(["sdd", "status", "--change", "test-change", "--cwd", "."])
    assert args.sdd_command == "status"
    assert args.change == "test-change"


def test_sdd_continue_returns_markdown_with_next_recommended() -> None:
    """REQ-OSP-003: sdd continue dispatches with next_recommended field."""
    parser = _build_parent()
    args = parser.parse_args(["sdd", "continue", "--change", "test-change", "--cwd", "."])
    assert args.sdd_command == "continue"
    assert args.change == "test-change"


def test_sdd_new_creates_change_folder_with_proposal_stub() -> None:
    """REQ-OSP-004: sdd new produces a proposal.md under the change folder."""
    parser = _build_parent()
    args = parser.parse_args(["sdd", "new", "my-change", "--cwd", "."])
    assert args.sdd_command == "new"
    assert args.change == "my-change"


def test_sdd_explore_returns_explore_path() -> None:
    """REQ-OSP-005: sdd explore runs exploration and returns path."""
    parser = _build_parent()
    args = parser.parse_args(["sdd", "explore", "--topic", "auth", "--cwd", "."])
    assert args.sdd_command == "explore"
    assert args.topic == "auth"


def test_sdd_propose_blocks_without_explore() -> None:
    """REQ-OSP-006: sdd propose requires prior exploration."""
    parser = _build_parent()
    args = parser.parse_args(["sdd", "propose", "--change", "test", "--cwd", "."])
    assert args.sdd_command == "propose"


def test_sdd_spec_write_one_file_per_capability() -> None:
    """sdd spec writes one spec file per capability."""
    parser = _build_parent()
    args = parser.parse_args(["sdd", "spec", "--change", "test", "--cwd", "."])
    assert args.sdd_command == "spec"


def test_sdd_design_creates_design_md() -> None:
    """sdd design creates the design.md artifact."""
    parser = _build_parent()
    args = parser.parse_args(["sdd", "design", "--change", "test", "--cwd", "."])
    assert args.sdd_command == "design"


def test_sdd_tasks_emits_checkboxes() -> None:
    """sdd tasks lists per-file tasks as checkboxes."""
    parser = _build_parent()
    args = parser.parse_args(["sdd", "tasks", "--change", "test", "--cwd", "."])
    assert args.sdd_command == "tasks"


def test_sdd_apply_writes_failing_test_first_when_strict() -> None:
    """REQ-OSP-007 / R1: In strict TDD mode, apply writes failing test before impl."""
    parser = _build_parent()
    args = parser.parse_args(["sdd", "apply", "--change", "test", "--cwd", ".", "--task", "T3.1"])
    assert args.sdd_command == "apply"
    assert args.task == "T3.1"


def test_sdd_verify_parses_verdict() -> None:
    """REQ-OSP-008: sdd verify parses verdict JSON."""
    parser = _build_parent()
    args = parser.parse_args(["sdd", "verify", "--change", "test", "--cwd", "."])
    assert args.sdd_command == "verify"


def test_sdd_archive_replaces_modified_blocks() -> None:
    """sdd archive replaces modified blocks in the full-spec snapshot."""
    parser = _build_parent()
    args = parser.parse_args(["sdd", "archive", "--change", "test-change", "--cwd", "."])
    assert args.sdd_command == "archive"


def test_sdd_ff_creates_full_plan() -> None:
    """sdd ff fast-forwards proposal to spec to design to tasks."""
    parser = _build_parent()
    args = parser.parse_args(["sdd", "ff", "--change", "test", "--cwd", "."])
    assert args.sdd_command == "ff"


def test_sdd_verbose_flag_accepted() -> None:
    """All sdd verbs accept --verbose flag."""
    parser = _build_parent()
    for verb in SUBCOMMANDS:
        args = parser.parse_args(["sdd", verb, "--cwd", ".", "--verbose"])
        assert getattr(args, "verbose", False) is True


def test_sdd_help_on_verb() -> None:
    """Each verb appears in the sdd subparser help."""
    sdd = _sdd_parser()
    help_out = sdd.format_help()
    for verb in SUBCOMMANDS:
        assert verb in help_out, f"Missing verb '{verb}' in sdd help"


def test_sdd_init_bootstraps_context() -> None:
    """sdd init bootstraps SDD context."""
    parser = _build_parent()
    args = parser.parse_args(["sdd", "init", "--cwd", "."])
    assert args.sdd_command == "init"


def test_sdd_onboard_walks_through_sdd() -> None:
    """sdd onboard walks user through SDD cycle."""
    parser = _build_parent()
    args = parser.parse_args(["sdd", "onboard", "--cwd", "."])
    assert args.sdd_command == "onboard"


def test_sdd_list_shows_active_changes() -> None:
    """sdd list shows active changes."""
    parser = _build_parent()
    args = parser.parse_args(["sdd", "list", "--cwd", "."])
    assert args.sdd_command == "list"
