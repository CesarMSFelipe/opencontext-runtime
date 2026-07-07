"""SDD contract items — CLI verbs do the real work they promise.

Pins DOC1 §8 items SDD-001 / SDD-007 / SDD-009 / SDD-010 / SDD-ARTIFACTS against
docs/product-contract/SDD_CONTRACT.md (real layout: openspec/changes/<change>/ +
project context under .opencontext/sdd/).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def _args(**kw):
    base = dict(cwd=".", change=None, topic=None, task=None, verbose=False)
    base.update(kw)
    return SimpleNamespace(**base)


def _seed_change(
    root: Path,
    change: str,
    *,
    tasks: str = "- [ ] one\n",
    verify: str | None = None,
) -> Path:
    """Author a connected change dir the way an agent would."""
    change_root = root / "openspec" / "changes" / change
    (change_root / "specs" / "cap").mkdir(parents=True, exist_ok=True)
    (change_root / "proposal.md").write_text("# proposal\n", encoding="utf-8")
    (change_root / "specs" / "cap" / "spec.md").write_text("# spec\n", encoding="utf-8")
    (change_root / "design.md").write_text("# design\n", encoding="utf-8")
    (change_root / "tasks.md").write_text(tasks, encoding="utf-8")
    if verify is not None:
        (change_root / "verify-report.md").write_text(verify, encoding="utf-8")
    return change_root


# ---------------------------------------------------------------------------
# SDD-001 — `sdd init` creates the SDD structure (project context included)
# ---------------------------------------------------------------------------


def test_sdd_init_writes_project_sdd_context_without_install(tmp_path: Path, capsys) -> None:
    """SDD-001: `sdd init` creates the SDD structure — including the project SDD
    context (.opencontext/sdd/context.json + testing.md) — without a prior install."""
    from opencontext_cli.commands.sdd_cmd import handle_sdd

    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    handle_sdd(_args(sdd_command="init", cwd=str(tmp_path)))

    context_path = tmp_path / ".opencontext" / "sdd" / "context.json"
    assert context_path.is_file(), (
        "SDD_CONTRACT: sdd init must persist .opencontext/sdd/context.json"
    )
    context = json.loads(context_path.read_text(encoding="utf-8"))
    assert context["phases"], "SDD context must record the lifecycle phases"
    assert (tmp_path / ".opencontext" / "sdd" / "testing.md").is_file()
    assert (tmp_path / ".opencontext" / "sdd" / "registry.json").is_file()
    assert (tmp_path / "openspec" / "changes").is_dir()

    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "initialized"
    assert report["sdd_context_created"] is True


def test_sdd_init_does_not_stomp_existing_sdd_context(tmp_path: Path, capsys) -> None:
    """SDD-001: re-running `sdd init` preserves an existing project SDD context
    (install/wizard settings must never be overwritten with defaults)."""
    from opencontext_cli.commands.sdd_cmd import handle_sdd

    context_path = tmp_path / ".opencontext" / "sdd" / "context.json"
    context_path.parent.mkdir(parents=True, exist_ok=True)
    context_path.write_text(json.dumps({"tdd_mode": "strict", "sentinel": True}), encoding="utf-8")

    handle_sdd(_args(sdd_command="init", cwd=str(tmp_path)))

    preserved = json.loads(context_path.read_text(encoding="utf-8"))
    assert preserved.get("sentinel") is True, "sdd init must not overwrite an existing context"
    report = json.loads(capsys.readouterr().out)
    assert report["sdd_context_created"] is False


# ---------------------------------------------------------------------------
# SDD-009 — `sdd continue` resumes from the last incomplete phase
# ---------------------------------------------------------------------------


def test_sdd_continue_resolves_next_dependency_ready_phase(tmp_path: Path, capsys) -> None:
    """SDD-009: `sdd continue` resolves the disk status and dispatches the next
    dependency-ready phase (proposal-only change resumes at spec)."""
    from opencontext_cli.commands.sdd_cmd import handle_sdd

    change_root = tmp_path / "openspec" / "changes" / "demo"
    change_root.mkdir(parents=True)
    (change_root / "proposal.md").write_text("# proposal\n", encoding="utf-8")

    handle_sdd(_args(sdd_command="continue", change="demo", cwd=str(tmp_path)))
    out = capsys.readouterr().out
    assert "Next: spec" in out, f"continue must surface nextRecommended, got:\n{out}"
    assert "phase=spec" in out, f"continue must dispatch the resolved phase prompt, got:\n{out}"


def test_sdd_continue_resumes_pending_tasks_at_apply(tmp_path: Path, capsys) -> None:
    """SDD-009: `sdd continue` on a change with unchecked tasks resumes at apply,
    never at a static phase-less prompt."""
    from opencontext_cli.commands.sdd_cmd import handle_sdd

    _seed_change(tmp_path, "demo", tasks="- [x] one\n- [ ] two\n")
    handle_sdd(_args(sdd_command="continue", change="demo", cwd=str(tmp_path)))
    out = capsys.readouterr().out
    assert "Next: apply" in out
    assert "phase=apply" in out
    assert "phase=continue" not in out, "continue must not emit the old static prompt"


# ---------------------------------------------------------------------------
# SDD-010 — `sdd archive` closes the change and preserves evidence
# ---------------------------------------------------------------------------


def test_sdd_archive_closes_change_and_preserves_evidence(tmp_path: Path, capsys) -> None:
    """SDD-010: `sdd archive` on a verified change closes it under
    openspec/changes/archive/ preserving every evidence artifact."""
    from opencontext_cli.commands.sdd_cmd import handle_sdd

    _seed_change(tmp_path, "demo", tasks="- [x] one\n", verify="verdict: PASS\n")
    handle_sdd(_args(sdd_command="archive", change="demo", cwd=str(tmp_path)))

    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "archived"
    archived_root = tmp_path / report["archived_to"]
    assert archived_root.is_dir()
    for name in ("proposal.md", "design.md", "tasks.md", "verify-report.md"):
        assert (archived_root / name).is_file(), f"archive lost evidence artifact {name}"
    assert (archived_root / "specs" / "cap" / "spec.md").is_file()
    archive_report = json.loads((archived_root / "archive-report.json").read_text(encoding="utf-8"))
    assert archive_report["state"] == "archived"
    assert "verify-report.md" in archive_report["evidence"]
    # The change is closed: it no longer lives among the active changes.
    assert not (tmp_path / "openspec" / "changes" / "demo").exists()


def test_sdd_archive_blocked_without_passing_verify_exits_7(tmp_path: Path, capsys) -> None:
    """SDD-010: `sdd archive` without a passing verify-report blocks with exit
    code 7 (SDD_ARTIFACTS_MISSING) and archives nothing."""
    from opencontext_cli.commands.sdd_cmd import handle_sdd

    _seed_change(tmp_path, "demo", tasks="- [x] one\n", verify="verdict: FAIL\n- test_one\n")
    with pytest.raises(SystemExit) as exc:
        handle_sdd(_args(sdd_command="archive", change="demo", cwd=str(tmp_path)))
    assert exc.value.code == 7
    assert (tmp_path / "openspec" / "changes" / "demo").is_dir(), (
        "blocked archive must not move the change"
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "blocked"
    assert payload["blocked_reasons"]


def test_sdd_list_excludes_the_archive_folder(tmp_path: Path, capsys) -> None:
    """SDD-010: archived changes are closed — `sdd list` does not report the
    archive/ folder as an active change."""
    from opencontext_cli.commands.sdd_cmd import handle_sdd

    _seed_change(tmp_path, "demo", tasks="- [x] one\n", verify="verdict: PASS\n")
    handle_sdd(_args(sdd_command="archive", change="demo", cwd=str(tmp_path)))
    capsys.readouterr()
    handle_sdd(_args(sdd_command="list", cwd=str(tmp_path)))
    out = capsys.readouterr().out
    assert "archive" not in out.replace("(no active changes)", "")
    assert "no active changes" in out


# ---------------------------------------------------------------------------
# SDD-ARTIFACTS — registry.json + per-change manifest.json
# ---------------------------------------------------------------------------


def test_sdd_new_writes_registry_and_change_manifest(tmp_path: Path, capsys) -> None:
    """SDD-ARTIFACTS: `sdd new` registers the change in
    .opencontext/sdd/registry.json and writes a per-change manifest.json carrying
    the state-machine position (SDD_CONTRACT Current→Target addition)."""
    from opencontext_cli.commands.sdd_cmd import handle_sdd

    handle_sdd(_args(sdd_command="new", change="demo", cwd=str(tmp_path)))

    registry = json.loads(
        (tmp_path / ".opencontext" / "sdd" / "registry.json").read_text(encoding="utf-8")
    )
    assert registry["changes"]["demo"]["state"] == "proposed"

    manifest = json.loads(
        (tmp_path / "openspec" / "changes" / "demo" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["change"] == "demo"
    assert manifest["state"] == "proposed"
    assert manifest["nextRecommended"] == "spec"


def test_sdd_archive_records_archived_state_in_registry(tmp_path: Path, capsys) -> None:
    """SDD-ARTIFACTS: archiving a change records state 'archived' (with the new
    path) in registry.json and in the preserved per-change manifest."""
    from opencontext_cli.commands.sdd_cmd import handle_sdd

    _seed_change(tmp_path, "demo", tasks="- [x] one\n", verify="verdict: PASS\n")
    handle_sdd(_args(sdd_command="archive", change="demo", cwd=str(tmp_path)))
    report = json.loads(capsys.readouterr().out)

    registry = json.loads(
        (tmp_path / ".opencontext" / "sdd" / "registry.json").read_text(encoding="utf-8")
    )
    assert registry["changes"]["demo"]["state"] == "archived"
    assert registry["changes"]["demo"]["path"] == report["archived_to"]

    manifest = json.loads(
        (tmp_path / report["archived_to"] / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["state"] == "archived"


# ---------------------------------------------------------------------------
# SDD-007 — `sdd apply --execute` runs the shared harness
# ---------------------------------------------------------------------------


def test_sdd_apply_execute_flag_accepted() -> None:
    """SDD-007: argparse accepts `sdd apply --execute` (the harness execution entry)."""
    import argparse

    from opencontext_cli.commands.sdd_cmd import add_sdd_parser

    parser = argparse.ArgumentParser(prog="opencontext")
    sub = parser.add_subparsers(dest="command", required=True)
    add_sdd_parser(sub)
    args = parser.parse_args(["sdd", "apply", "--change", "demo", "--execute"])
    assert args.execute is True


def test_sdd_apply_execute_launches_harness_run(tmp_path: Path, monkeypatch, capsys) -> None:
    """SDD-007: `sdd apply --execute` launches the shared OC Flow harness run
    (`run --workflow sdd`) for the change instead of only dispatching."""
    import opencontext_cli.commands.run_cmd as run_cmd
    from opencontext_cli.commands.sdd_cmd import handle_sdd

    _seed_change(tmp_path, "demo")  # unchecked tasks => nextRecommended: apply
    calls: dict[str, object] = {}

    def fake_run_exec(run_args) -> int:
        calls["workflow"] = run_args.workflow
        calls["root"] = run_args.root
        calls["task"] = run_args.task
        return 0

    monkeypatch.setattr(run_cmd, "handle_run_exec", fake_run_exec)
    with pytest.raises(SystemExit) as exc:
        handle_sdd(_args(sdd_command="apply", change="demo", cwd=str(tmp_path), execute=True))
    assert exc.value.code == 0
    assert calls["workflow"] == "sdd", "apply --execute must use the SDD harness workflow"
    assert Path(str(calls["root"])).resolve() == tmp_path.resolve()
    assert "demo" in str(calls["task"])


def test_sdd_apply_execute_blocked_when_change_not_ready(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """SDD-007: `sdd apply --execute` refuses to launch the harness when the
    change is not apply-ready (exit 7, no run started)."""
    import opencontext_cli.commands.run_cmd as run_cmd
    from opencontext_cli.commands.sdd_cmd import handle_sdd

    change_root = tmp_path / "openspec" / "changes" / "demo"
    change_root.mkdir(parents=True)  # empty change: nextRecommended is propose

    def fail_if_called(run_args) -> int:  # pragma: no cover - guard
        raise AssertionError("harness must not launch for a non-ready change")

    monkeypatch.setattr(run_cmd, "handle_run_exec", fail_if_called)
    with pytest.raises(SystemExit) as exc:
        handle_sdd(_args(sdd_command="apply", change="demo", cwd=str(tmp_path), execute=True))
    assert exc.value.code == 7
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "blocked"
    assert payload["next_recommended"] == "propose"
