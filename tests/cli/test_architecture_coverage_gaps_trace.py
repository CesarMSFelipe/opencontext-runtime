"""TDD — C18: architecture coverage/gaps/trace subcommands.

RED gate: architecture_cmd.py currently only exposes 'diff'.
The tests assert that coverage, gaps, and trace <req-id> subcommands
exist and produce real data from docs/architecture/54-requirement-to-pr-
traceability-matrix.md, which fails until architecture_cmd.py is extended.
"""

from __future__ import annotations

import argparse
import json


def test_architecture_coverage_returns_zero(capsys) -> None:
    """architecture coverage must return 0 and emit totals from the matrix."""
    from opencontext_cli.commands.architecture_cmd import handle_architecture

    args = argparse.Namespace(
        architecture_command="coverage",
        json=False,
        root=None,
    )
    rc = handle_architecture(args)
    assert rc == 0, f"architecture coverage must return 0, got {rc}"
    out = capsys.readouterr().out
    # Must mention MET and DEFERRED counts
    assert "MET" in out or "met" in out.lower(), f"coverage output must mention MET, got: {out!r}"


def test_architecture_coverage_json(capsys) -> None:
    """architecture coverage --json must emit valid JSON with met/deferred keys."""
    from opencontext_cli.commands.architecture_cmd import handle_architecture

    args = argparse.Namespace(
        architecture_command="coverage",
        json=True,
        root=None,
    )
    rc = handle_architecture(args)
    assert rc == 0, f"architecture coverage --json must return 0, got {rc}"
    out = capsys.readouterr().out
    data = json.loads(out)
    assert "met" in data, f"JSON output must contain 'met' key, got: {list(data)}"
    assert "deferred" in data, f"JSON output must contain 'deferred' key, got: {list(data)}"
    assert data["met"] >= 0
    assert data["deferred"] >= 0
    assert data["total"] == data["met"] + data["deferred"] + data.get("rejected", 0)


def test_architecture_gaps_returns_zero(capsys) -> None:
    """architecture gaps must return 0 and list DEFERRED requirements."""
    from opencontext_cli.commands.architecture_cmd import handle_architecture

    args = argparse.Namespace(
        architecture_command="gaps",
        json=False,
        root=None,
        status="DEFERRED",
    )
    rc = handle_architecture(args)
    assert rc == 0, f"architecture gaps must return 0, got {rc}"
    out = capsys.readouterr().out
    assert "DEFERRED" in out or "deferred" in out.lower(), (
        f"gaps output must list DEFERRED requirements, got: {out!r}"
    )


def test_architecture_gaps_json(capsys) -> None:
    """architecture gaps --json must return a list of gap records."""
    from opencontext_cli.commands.architecture_cmd import handle_architecture

    args = argparse.Namespace(
        architecture_command="gaps",
        json=True,
        root=None,
        status="DEFERRED",
    )
    rc = handle_architecture(args)
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert isinstance(data, list), f"gaps --json must return a list, got: {type(data)}"
    assert len(data) > 0, "gaps list must be non-empty (there are DEFERRED requirements)"
    first = data[0]
    assert "id" in first, f"gap record must have 'id', got: {list(first)}"
    assert "status" in first, f"gap record must have 'status', got: {list(first)}"


def test_architecture_trace_known_req(capsys) -> None:
    """architecture trace MP-011 must return 0 and show the requirement row."""
    from opencontext_cli.commands.architecture_cmd import handle_architecture

    args = argparse.Namespace(
        architecture_command="trace",
        req_id="MP-011",
        json=False,
        root=None,
    )
    rc = handle_architecture(args)
    assert rc == 0, f"architecture trace MP-011 must return 0 for a known req, got {rc}"
    out = capsys.readouterr().out
    assert "MP-011" in out, f"trace output must include the req id MP-011, got: {out!r}"


def test_architecture_trace_unknown_req(capsys) -> None:
    """architecture trace NONEXISTENT-999 must return non-zero with honest message."""
    from opencontext_cli.commands.architecture_cmd import handle_architecture

    args = argparse.Namespace(
        architecture_command="trace",
        req_id="NONEXISTENT-999",
        json=False,
        root=None,
    )
    rc = handle_architecture(args)
    assert rc != 0, "architecture trace of an unknown req must return non-zero"
    # stderr or stdout should mention the unknown id
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "NONEXISTENT-999" in output or "not found" in output.lower(), (
        f"error output must mention the unknown id, got: {output!r}"
    )


def test_architecture_no_subcommand_returns_1(capsys) -> None:
    """handle_architecture with unknown subcommand returns 1 with usage hint."""
    from opencontext_cli.commands.architecture_cmd import handle_architecture

    args = argparse.Namespace(architecture_command="unknown_sub", json=False, root=None)
    rc = handle_architecture(args)
    assert rc == 1
