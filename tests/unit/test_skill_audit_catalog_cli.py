"""TDD — C8: skill audit + catalog generate --check wired in skill_cmd.py.

RED gate: both subcommands must exist and dispatch correctly before
implementation. The test will fail with SystemExit / AttributeError
(command not found) until skill_cmd.py is updated.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest


def _run_skill(args_list: list[str]) -> int:
    """Invoke the skill CLI, return exit code (0 if no SystemExit raised)."""
    from opencontext_cli.commands.skill_cmd import add_skill_parser, handle_skill

    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="command")
    add_skill_parser(subs)
    args = parser.parse_args(args_list)
    try:
        handle_skill(args)
    except SystemExit as exc:
        return int(exc.code if exc.code is not None else 0)
    return 0


# ---------------------------------------------------------------------------
# audit subcommand
# ---------------------------------------------------------------------------


def test_skill_audit_exits_zero(tmp_path: Path) -> None:
    """skill audit with an empty dir exits 0 (no ERROR findings in empty tree)."""
    code = _run_skill(["skill", "audit", "--root", str(tmp_path)])
    assert code == 0


def test_skill_audit_with_valid_yaml_exits_zero(tmp_path: Path) -> None:
    """skill audit with a well-formed skill yaml exits 0."""
    (tmp_path / "sample.yaml").write_text(
        "id: sample\n"
        "name: Sample Skill\n"
        "tier: 1\n"
        "required_capabilities: []\n"
        "persona_compat:\n  - senior-architect\n"
        "contract: sample-contract\n",
        encoding="utf-8",
    )
    code = _run_skill(["skill", "audit", "--root", str(tmp_path)])
    assert code == 0


def test_skill_audit_invalid_yaml_exits_one(tmp_path: Path) -> None:
    """skill audit with a missing-required-fields yaml exits 1 (ERROR finding)."""
    (tmp_path / "bad.yaml").write_text("id: bad\nname: Bad\n", encoding="utf-8")
    code = _run_skill(["skill", "audit", "--root", str(tmp_path)])
    assert code == 1


# ---------------------------------------------------------------------------
# catalog generate --check subcommand
# ---------------------------------------------------------------------------


def test_skill_catalog_generate_check_no_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """catalog generate --check surfaces a readable message (no Traceback)."""
    _run_skill(["skill", "catalog", "generate", "--check", "--root", str(tmp_path)])
    captured = capsys.readouterr()
    assert "Traceback" not in (captured.out + captured.err)


def test_skill_catalog_generate_check_exits_one_when_drifted(tmp_path: Path) -> None:
    """catalog generate --check exits 1 when catalog is missing (drifted state)."""
    # No catalog.json exists → dry_run_update reports drifted=True → exit 1
    code = _run_skill(["skill", "catalog", "generate", "--check", "--root", str(tmp_path)])
    assert code == 1


def test_skill_catalog_generate_check_exits_zero_when_synced(tmp_path: Path) -> None:
    """catalog generate --check exits 0 when committed catalog matches live tree."""
    import json

    # Empty tree + empty committed catalog → no drift
    (tmp_path / "catalog.json").write_text(
        json.dumps({"skills": []}), encoding="utf-8"
    )
    code = _run_skill(["skill", "catalog", "generate", "--check", "--root", str(tmp_path)])
    assert code == 0
