"""Tests for the ``opencontext quality check`` / ``quality gate`` CLI surface.

Every test is tmp-isolated: the project root, its ``.storage`` knowledge graph,
and any quality baseline live under ``tmp_path``. The real ``~/.opencontext`` and
the repo's own ``.opencontext`` are never read or written (asserted explicitly in
:func:`test_isolation_never_touches_real_opencontext`).

The CLI wiring is what is under test here (exit codes, JSON shape, the ``--diff``
scope hand-off, the ``gate --save`` baseline write, and the main.py dispatch). The
evaluator internals are covered by ``test_evaluator.py``; where this file needs a
specific verdict it stubs ``QualityEvaluator.evaluate`` so the assertions stay
deterministic and free of external lint tools.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from opencontext_cli.commands import quality_cmd
from opencontext_cli.commands.quality_cmd import (
    add_quality_subcommands,
    handle_quality_check,
    handle_quality_gate,
)
from opencontext_core.harness.models import GateStatus
from opencontext_core.quality.ci_checks import CheckSeverity, CheckStatus
from opencontext_core.quality.models import (
    Finding,
    HealthScore,
    QualityMetrics,
    QualityReport,
    RuleVerdict,
)

# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #


def _make_project(root: Path) -> None:
    """Create a tiny, valid Python project (no knowledge graph built)."""
    src = root / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "a.py").write_text("def foo() -> int:\n    return 1\n", encoding="utf-8")


def _failed_report() -> QualityReport:
    """A deterministic FAILED report used to assert the violation exit path."""
    metrics = QualityMetrics(cycles=1, node_count=2, edge_count=2)
    health = HealthScore(score=9600, metrics=metrics, components={"cycles": 400})
    finding = Finding(
        rule="max_cycles",
        severity=CheckSeverity.ERROR,
        message="1 import cycle (src/a.py <-> src/b.py)",
        file="src/a.py",
        line=1,
        category="architecture",
        suggestion="Break the import cycle.",
    )
    verdict = RuleVerdict(
        rule="max_cycles",
        status=CheckStatus.FAILED,
        severity=CheckSeverity.ERROR,
        findings=(finding,),
        message="1 max_cycles finding(s)",
    )
    return QualityReport(
        status=GateStatus.FAILED,
        findings=(finding,),
        verdicts=(verdict,),
        health=health,
        summary="architecture 10000 -> 9600 (down)",
        skipped=("max_cc:tree-sitter-unavailable",),
    )


def _check_args(path: Path, *, json_output: bool = False, diff: bool = False) -> SimpleNamespace:
    return SimpleNamespace(path=str(path), json=json_output, diff=diff)


# --------------------------------------------------------------------------- #
# Parser registration
# --------------------------------------------------------------------------- #


def test_add_quality_subcommands_registers_check_and_gate() -> None:
    """check + gate attach to an existing quality group and parse their flags."""
    parser = argparse.ArgumentParser(prog="opencontext")
    sub = parser.add_subparsers(dest="command")
    quality = sub.add_parser("quality")
    quality_sub = quality.add_subparsers(dest="quality_command")

    add_quality_subcommands(quality_sub)

    args = parser.parse_args(["quality", "check", "myroot", "--json", "--diff"])
    assert args.quality_command == "check"
    assert args.path == "myroot"
    assert args.json is True
    assert args.diff is True

    gate_args = parser.parse_args(["quality", "gate", "--save"])
    assert gate_args.quality_command == "gate"
    assert gate_args.save is True


def test_check_path_defaults_to_cwd_marker() -> None:
    """``check`` with no positional path defaults to '.'."""
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    quality = sub.add_parser("quality")
    quality_sub = quality.add_subparsers(dest="quality_command")
    add_quality_subcommands(quality_sub)

    args = parser.parse_args(["quality", "check"])
    assert args.path == "."
    assert args.json is False
    assert args.diff is False


# --------------------------------------------------------------------------- #
# check — exit codes
# --------------------------------------------------------------------------- #


def test_check_clean_project_exits_zero(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """An unindexed project has no findings -> clean PASS -> exit 0."""
    _make_project(tmp_path)
    with pytest.raises(SystemExit) as exc:
        handle_quality_check(_check_args(tmp_path))
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "Quality Report" in out


def test_check_violation_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """A FAILED report -> exit 1, and the finding surfaces in the table."""
    _make_project(tmp_path)
    monkeypatch.setattr(
        "opencontext_core.quality.evaluator.QualityEvaluator.evaluate",
        lambda self, changed, **kw: _failed_report(),
    )
    with pytest.raises(SystemExit) as exc:
        handle_quality_check(_check_args(tmp_path))
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "max_cycles" in out
    assert "src/a.py" in out  # finding file surfaces
    assert "tree-sitter-unavailable" in out  # skipped section is honest


# --------------------------------------------------------------------------- #
# check — --json
# --------------------------------------------------------------------------- #


def test_check_json_emits_ci_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """``--json`` prints the ci-check-compatible report dict and only JSON."""
    _make_project(tmp_path)
    monkeypatch.setattr(
        "opencontext_core.quality.evaluator.QualityEvaluator.evaluate",
        lambda self, changed, **kw: _failed_report(),
    )
    with pytest.raises(SystemExit) as exc:
        handle_quality_check(_check_args(tmp_path, json_output=True))
    assert exc.value.code == 1

    out = capsys.readouterr().out
    payload = json.loads(out)  # must be a single, parseable JSON document
    assert set(payload["summary"]) >= {
        "total_checks",
        "passed",
        "failed",
        "warnings",
        "errors",
        "success",
    }
    assert payload["summary"]["success"] is False
    assert payload["summary"]["errors"] == 1
    assert payload["health"]["score"] == 9600
    assert payload["results"][0]["check"] == "max_cycles"
    assert payload["results"][0]["file"] == "src/a.py"


def test_check_clean_json_is_success(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """A clean project's JSON report reports success=True with exit 0."""
    _make_project(tmp_path)
    with pytest.raises(SystemExit) as exc:
        handle_quality_check(_check_args(tmp_path, json_output=True))
    assert exc.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["success"] is True


# --------------------------------------------------------------------------- #
# check — --diff scope hand-off
# --------------------------------------------------------------------------- #


def test_check_diff_passes_changed_files_to_evaluator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """``--diff`` derives changed files and forwards them to ``evaluate``."""
    _make_project(tmp_path)
    seen: dict[str, list[str]] = {}

    monkeypatch.setattr(quality_cmd, "_changed_files", lambda root: ["src/a.py", "src/b.py"])

    def _spy(self, changed, **kw):
        seen["changed"] = changed
        return _failed_report()

    monkeypatch.setattr("opencontext_core.quality.evaluator.QualityEvaluator.evaluate", _spy)

    with pytest.raises(SystemExit):
        handle_quality_check(_check_args(tmp_path, diff=True))
    assert seen["changed"] == ["src/a.py", "src/b.py"]


def test_check_without_diff_scopes_whole_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Without ``--diff`` the evaluator gets an empty changed-file list (whole repo)."""
    _make_project(tmp_path)
    seen: dict[str, list[str]] = {}

    def _spy(self, changed, **kw):
        seen["changed"] = changed
        return _failed_report()

    monkeypatch.setattr("opencontext_core.quality.evaluator.QualityEvaluator.evaluate", _spy)
    # _changed_files must NOT be consulted when --diff is absent.
    monkeypatch.setattr(
        quality_cmd,
        "_changed_files",
        lambda root: pytest.fail("_changed_files called without --diff"),
    )

    with pytest.raises(SystemExit):
        handle_quality_check(_check_args(tmp_path, diff=False))
    assert seen["changed"] == []


def test_changed_files_helper_is_resilient(tmp_path: Path) -> None:
    """The git helper returns a list and never raises on a non-git dir."""
    result = quality_cmd._changed_files(tmp_path)
    assert isinstance(result, list)


# --------------------------------------------------------------------------- #
# gate --save
# --------------------------------------------------------------------------- #


def test_gate_save_writes_baseline_under_tmp(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """``gate --save`` persists the baseline beneath the project root, exit 0."""
    _make_project(tmp_path)
    args = SimpleNamespace(path=str(tmp_path), save=True)
    with pytest.raises(SystemExit) as exc:
        handle_quality_gate(args)
    assert exc.value.code == 0

    baseline = tmp_path / ".opencontext" / "quality-baseline.json"
    assert baseline.exists()
    data = json.loads(baseline.read_text())
    assert "score" in data
    assert "findings" in data
    assert "metrics" in data
    out = capsys.readouterr().out
    assert "baseline" in out.lower()


def test_gate_without_save_is_noop(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """A bare ``gate`` (no --save) writes nothing and exits 0."""
    _make_project(tmp_path)
    args = SimpleNamespace(path=str(tmp_path), save=False)
    with pytest.raises(SystemExit) as exc:
        handle_quality_gate(args)
    assert exc.value.code == 0
    assert not (tmp_path / ".opencontext" / "quality-baseline.json").exists()


# --------------------------------------------------------------------------- #
# main.py dispatch (end-to-end wiring)
# --------------------------------------------------------------------------- #


def test_main_dispatch_routes_quality_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """`opencontext quality check <root>` routes through main() to the handler.

    Drives the real entry point (parser registration + the dispatch branch) via
    ``sys.argv``, exactly like the other end-to-end CLI tests.
    """
    import sys

    from opencontext_cli.main import main

    _make_project(tmp_path)
    monkeypatch.setattr(sys, "argv", ["opencontext", "quality", "check", str(tmp_path), "--json"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["success"] is True


def test_main_dispatch_routes_quality_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """`opencontext quality gate --save` routes through main() and writes a baseline.

    The ``gate`` parser has no path positional, so ``check``/``gate`` default the
    root to ``.``; we ``chdir`` into ``tmp_path`` so the baseline write stays
    tmp-isolated while still exercising the real dispatch branch.
    """
    import os
    import sys

    from opencontext_cli.main import main

    _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["opencontext", "quality", "gate", "--save"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    assert (tmp_path / ".opencontext" / "quality-baseline.json").exists()
    assert os.getcwd() == str(tmp_path)


def test_main_legacy_quality_preflight_still_works(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """The legacy context-quality `preflight` subcommand must keep working."""
    import sys

    from opencontext_cli.main import main

    monkeypatch.setattr(sys, "argv", ["opencontext", "quality", "preflight", "--query", "x"])
    main()
    out = capsys.readouterr().out
    assert out.strip()  # emits the preflight gate report JSON


# --------------------------------------------------------------------------- #
# Isolation guard
# --------------------------------------------------------------------------- #


def test_isolation_never_touches_real_opencontext(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """check + gate must not read/write ~/.opencontext or the repo .opencontext.

    We forbid ``open()`` on any path that escapes ``tmp_path`` while resolving an
    ``.opencontext`` / ``.storage`` segment, catching an accidental real-config
    or real-graph access.
    """
    _make_project(tmp_path)

    real_builtin_open = open
    repo_root = Path(__file__).resolve().parents[2]
    forbidden_roots = (Path.home(), repo_root)

    def _guarded_open(file, *args, **kwargs):
        candidate = Path(file)
        try:
            resolved = candidate.resolve()
        except Exception:
            resolved = candidate
        text = str(resolved)
        if (".opencontext" in text or ".storage" in text) and not str(resolved).startswith(
            str(tmp_path.resolve())
        ):
            for forbidden in forbidden_roots:
                if str(resolved).startswith(str(forbidden.resolve())):
                    raise AssertionError(f"escaped isolation: opened {resolved}")
        return real_builtin_open(file, *args, **kwargs)

    monkeypatch.setattr("builtins.open", _guarded_open)

    # check (clean) — exit 0, no escaping I/O.
    with pytest.raises(SystemExit):
        handle_quality_check(_check_args(tmp_path))
    # gate --save — writes only under tmp_path.
    with pytest.raises(SystemExit):
        handle_quality_gate(SimpleNamespace(path=str(tmp_path), save=True))

    assert (tmp_path / ".opencontext" / "quality-baseline.json").exists()
