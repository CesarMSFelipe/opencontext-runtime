"""CLI-FLAGS: pinning matrix for the stable-command shared flag layer.

CLI_CONTRACT.md "Global flags": every stable command supports the documented
subset of the global flags with uniform names and semantics. This file freezes
that per-command subset (silently dropping e.g. ``--json`` from ``index`` must
break a test), pins the new ``--quiet`` / ``--no-color`` layer, and pins the
``pack --format json`` -> ``pack --json`` migration.
"""

from __future__ import annotations

import io
import os

import pytest

import opencontext_cli.main as cli_main

# The frozen CLI_CONTRACT global-flag vocabulary.
GLOBAL_FLAGS = frozenset(
    {
        "--json",
        "--quiet",
        "--verbose",
        "--root",
        "--config",
        "--profile",
        "--dry-run",
        "--verify",
        "--no-color",
    }
)

# Frozen per-stable-command flag subsets (top-level parse position).
# Semver-protected: removing a flag from a command here is a breaking change.
EXPECTED_MATRIX: dict[str, frozenset[str]] = {
    "clean": frozenset({"--json", "--dry-run", "--quiet", "--no-color"}),
    "config": frozenset({"--quiet", "--no-color"}),
    "doctor": frozenset({"--json", "--quiet", "--no-color"}),
    "harness": frozenset({"--quiet", "--no-color"}),
    "index": frozenset({"--json", "--quiet", "--no-color"}),
    "init": frozenset({"--json", "--profile", "--quiet", "--no-color"}),
    "install": frozenset({"--json", "--dry-run", "--quiet", "--no-color"}),
    "knowledge-graph": frozenset({"--quiet", "--no-color"}),
    "memory": frozenset({"--quiet", "--no-color"}),
    "pack": frozenset({"--json", "--quiet", "--no-color"}),
    "run": frozenset({"--json", "--root", "--config", "--profile", "--quiet", "--no-color"}),
    "runs": frozenset({"--quiet", "--no-color"}),
    "sdd": frozenset({"--quiet", "--no-color"}),
    "status": frozenset({"--json", "--quiet", "--no-color"}),
    "tui": frozenset({"--quiet", "--no-color"}),
    "uninstall": frozenset({"--json", "--dry-run", "--root", "--verify", "--quiet", "--no-color"}),
    "version": frozenset({"--json", "--quiet", "--no-color"}),
}

# argv fragments and expected parsed values per flag.
_FLAG_ARGV: dict[str, list[str]] = {
    "--json": ["--json"],
    "--quiet": ["--quiet"],
    "--no-color": ["--no-color"],
    "--dry-run": ["--dry-run"],
    "--verify": ["--verify"],
    "--root": ["--root", "."],
    "--config": ["--config", "opencontext.yaml"],
    "--profile": ["--profile", "default"],
}
_FLAG_EXPECTED: dict[str, object] = {
    "--json": True,
    "--quiet": True,
    "--no-color": True,
    "--dry-run": True,
    "--verify": True,
    "--root": ".",
    "--config": "opencontext.yaml",
    "--profile": "default",
}

# Tree-style stable commands with a required subcommand: minimal suffix.
_SUBCOMMAND_SUFFIX: dict[str, list[str]] = {
    "harness": ["list"],
    "knowledge-graph": ["status"],
    "memory": ["list"],
    "sdd": ["status"],
}


def _dest(flag: str) -> str:
    return flag.lstrip("-").replace("-", "_")


def test_flag_matrix_module_is_pinned() -> None:
    """CLI-FLAGS: contracts/flags.py freezes the exact per-stable-command flag matrix."""
    from opencontext_cli.contracts.flags import STABLE_COMMAND_FLAGS

    assert dict(STABLE_COMMAND_FLAGS) == EXPECTED_MATRIX


def test_flag_matrix_covers_exactly_the_stable_commands() -> None:
    """CLI-FLAGS: the flag matrix covers exactly the registry's stable command set."""
    from opencontext_cli.contracts.command_registry import COMMAND_MATURITY
    from opencontext_cli.contracts.flags import STABLE_COMMAND_FLAGS

    stable = {cmd for cmd, level in COMMAND_MATURITY.items() if level == "stable"}
    assert set(STABLE_COMMAND_FLAGS) == stable


def test_matrix_flags_are_from_the_documented_global_vocabulary() -> None:
    """CLI-FLAGS: every matrix entry uses only documented CLI_CONTRACT global flags."""
    from opencontext_cli.contracts.flags import GLOBAL_FLAGS as MODULE_GLOBAL_FLAGS
    from opencontext_cli.contracts.flags import STABLE_COMMAND_FLAGS

    assert MODULE_GLOBAL_FLAGS == GLOBAL_FLAGS
    for command, flags in STABLE_COMMAND_FLAGS.items():
        unknown = flags - GLOBAL_FLAGS
        assert not unknown, f"{command} documents non-global flags: {sorted(unknown)}"


@pytest.mark.parametrize("command", sorted(EXPECTED_MATRIX))
def test_stable_command_parses_documented_flag_subset(command: str) -> None:
    """CLI-FLAGS: each stable command parses every flag in its documented subset."""
    argv: list[str] = [command]
    for flag in sorted(EXPECTED_MATRIX[command]):
        argv.extend(_FLAG_ARGV[flag])
    argv.extend(_SUBCOMMAND_SUFFIX.get(command, []))

    args = cli_main._build_parser().parse_args(argv)

    for flag in EXPECTED_MATRIX[command]:
        got = getattr(args, _dest(flag), None)
        assert got == _FLAG_EXPECTED[flag], (
            f"{command} {flag}: expected {_FLAG_EXPECTED[flag]!r}, parsed {got!r}"
        )


def test_top_level_quiet_and_no_color_are_global() -> None:
    """CLI-FLAGS: --quiet/--no-color parse at top level ahead of any command."""
    args = cli_main._build_parser().parse_args(["--quiet", "--no-color", "status"])
    assert args.quiet is True
    assert args.no_color is True


def test_quiet_and_no_color_default_off() -> None:
    """CLI-FLAGS: --quiet/--no-color default to off (no behavior change unasked)."""
    args = cli_main._build_parser().parse_args(["status"])
    assert args.quiet is False
    assert args.no_color is False


def test_pack_json_flag_normalizes_to_json_format() -> None:
    """CLI-FLAGS: `pack --json` is the documented spelling of `--format json`."""
    args = cli_main._build_parser().parse_args(["pack", ".", "--query", "x", "--json"])
    assert args.json is True
    cli_main._normalize_pack_args(args)
    assert args.format == "json"


def test_pack_format_json_still_parses_for_back_compat() -> None:
    """CLI-FLAGS: `pack --format json` keeps working (additive migration only)."""
    args = cli_main._build_parser().parse_args(["pack", ".", "--format", "json"])
    assert args.format == "json"
    cli_main._normalize_pack_args(args)
    assert args.format == "json"


def test_quiet_env_suppresses_stdout_brand_console(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLI-FLAGS: --quiet suppresses human-facing stdout chrome from BrandConsole."""
    from rich.console import Console

    from opencontext_core.dx.console_styles import BrandConsole

    monkeypatch.setenv("OPENCONTEXT_QUIET", "1")
    buf = io.StringIO()
    bc = BrandConsole()
    bc._console = Console(file=buf, force_terminal=False, width=100)

    bc.print("progress line")
    bc.header("Title")
    bc.section("Section")
    bc.success("done")
    with bc.status("Working..."):
        pass

    assert buf.getvalue() == "", f"quiet mode leaked stdout chrome: {buf.getvalue()!r}"


def test_quiet_env_keeps_stderr_consoles_working(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """CLI-FLAGS: --quiet never silences stderr-bound consoles (errors still show)."""
    from rich.console import Console

    from opencontext_core.dx.console_styles import BrandConsole

    monkeypatch.setenv("OPENCONTEXT_QUIET", "1")
    bc = BrandConsole()
    bc._console = Console(stderr=True, force_terminal=False, width=100)

    bc.warning("still visible")

    assert "still visible" in capsys.readouterr().err


def test_no_color_disables_ansi_styling(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI-FLAGS: --no-color sets NO_COLOR and de-colors the shared consoles."""
    from opencontext_core.dx import console_styles

    monkeypatch.setenv("NO_COLOR", "")
    fresh_stdout = console_styles.BrandConsole()
    fresh_stderr = cli_main._stderr_console()
    monkeypatch.setattr(console_styles, "console", fresh_stdout)
    monkeypatch.setattr(cli_main, "err_console", fresh_stderr)

    cli_main._disable_color()

    assert os.environ.get("NO_COLOR") == "1"
    assert fresh_stdout._console is None or fresh_stdout._console.no_color is True
    assert fresh_stderr._console is None or fresh_stderr._console.no_color is True
