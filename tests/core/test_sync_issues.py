"""Tests for sync issues — task parsing and dry-run."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from opencontext_cli.commands.sync_cmd import parse_tasks_from_md

# ── parse_tasks_from_md ──────────────────────────────────────────────────────


def test_parse_open_tasks(tmp_path: Path) -> None:
    """Lines matching '- [ ] ...' are parsed as open tasks."""
    tasks_file = tmp_path / "tasks.md"
    tasks_file.write_text(
        "# Tasks\n\n- [ ] Task one\n- [ ] Task two\n- [x] Done task\n",
        encoding="utf-8",
    )
    tasks = parse_tasks_from_md(tasks_file)
    assert len(tasks) == 3
    open_tasks = [t for t in tasks if t["state"] == "open"]
    assert len(open_tasks) == 2
    assert open_tasks[0]["title"] == "Task one"
    assert open_tasks[1]["title"] == "Task two"


def test_parse_closed_tasks(tmp_path: Path) -> None:
    """Lines matching '- [x] ...' are parsed as closed tasks."""
    tasks_file = tmp_path / "tasks.md"
    tasks_file.write_text("- [x] Completed task\n- [X] Also done\n", encoding="utf-8")
    tasks = parse_tasks_from_md(tasks_file)
    closed = [t for t in tasks if t["state"] == "closed"]
    assert len(closed) == 2


def test_parse_empty_file(tmp_path: Path) -> None:
    """Empty file returns no tasks."""
    tasks_file = tmp_path / "tasks.md"
    tasks_file.write_text("# Tasks\n\nNo task lines here.\n", encoding="utf-8")
    assert parse_tasks_from_md(tasks_file) == []


def test_parse_ignores_non_task_lines(tmp_path: Path) -> None:
    """Non-task lines (headers, prose, code) are ignored."""
    tasks_file = tmp_path / "tasks.md"
    tasks_file.write_text(
        "## \n- Regular bullet\n- [ ] Real task\n```\ncode\n```\n",
        encoding="utf-8",
    )
    tasks = parse_tasks_from_md(tasks_file)
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Real task"


# ── _handle_sync_issues dry-run ──────────────────────────────────────────────


def test_dry_run_does_not_call_gh(tmp_path: Path) -> None:
    """In dry-run mode, no gh CLI subprocess is spawned."""
    from opencontext_cli.commands.sync_cmd import _handle_sync_issues

    tasks_file = tmp_path / "tasks.md"
    tasks_file.write_text("- [ ] Open issue one\n- [ ] Open issue two\n", encoding="utf-8")

    args = SimpleNamespace(
        tasks_file=str(tasks_file),
        change=None,
        dry_run=True,
        repo=None,
    )

    with patch("subprocess.run") as mock_run:
        _handle_sync_issues(args)
        mock_run.assert_not_called()


def test_missing_tasks_file_does_not_crash(tmp_path: Path) -> None:
    """Missing tasks file prints error but does not raise."""
    from opencontext_cli.commands.sync_cmd import _handle_sync_issues

    args = SimpleNamespace(
        tasks_file=str(tmp_path / "nonexistent.md"),
        change=None,
        dry_run=True,
        repo=None,
    )
    # Should not raise
    _handle_sync_issues(args)
