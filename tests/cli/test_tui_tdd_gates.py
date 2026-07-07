"""Tests for TddGatesScreen — latest runs' gates with TDD evidence focus.

The screen reuses the run-bundle readers behind RunsScreen/RunDetailScreen
to show, per recent run, the gates.json name/status table and the run.json
``tdd`` block (red/green classification, commands, exit codes). An honest
empty state renders when no runs are persisted.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

textual = pytest.importorskip("textual", reason="textual not installed")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    """An isolated OpenContext workspace: opencontext.yaml + private HOME/prefs."""
    from opencontext_core.user_prefs import UserConfigStore

    (tmp_path / "opencontext.yaml").write_text(
        "ui_language: en\nmemory:\n  provider: local\n", encoding="utf-8"
    )
    cfg_dir = tmp_path / ".config" / "opencontext"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(UserConfigStore, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(UserConfigStore, "CONFIG_FILE", cfg_dir / "user-config.json")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _write_tdd_run(root: Path, run_id: str, *, created_at: str = "2026-01-01T00:00:00+00:00"):
    """Write a minimal run dir with gates.json and a full run.json tdd block."""
    run_dir = root / ".opencontext" / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "workflow": "oc-flow",
                "status": "completed",
                "task": "Fix the failing widget test",
                "created_at": created_at,
                "tdd": {
                    "mode": "strict",
                    "red": {
                        "command": "pytest -q tests/test_widget.py",
                        "exit_code": 1,
                        "failure_summary": "1 failed",
                        "captured_at": created_at,
                        "classification": "test_failure",
                    },
                    "green": {
                        "command": "pytest -q",
                        "exit_code": 0,
                        "failure_summary": "",
                        "captured_at": created_at,
                        "classification": "already_passing",
                    },
                    "regression": None,
                    "red_proven": True,
                    "green_proven": True,
                },
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "gates.json").write_text(
        json.dumps(
            {
                "gates": [
                    {"id": "workspace_valid", "status": "passed", "message": "ok"},
                    {"id": "tdd_red_proven", "status": "failed", "message": "no"},
                ]
            }
        ),
        encoding="utf-8",
    )
    return run_dir


# ---------------------------------------------------------------------------
# Unit tests — pure loader behind the screen
# ---------------------------------------------------------------------------


def test_latest_tdd_rows_reads_gates_and_tdd(tmp_path) -> None:
    from opencontext_cli.tui.screens.tdd_gates import latest_tdd_rows

    _write_tdd_run(tmp_path, "run-1")
    rows = latest_tdd_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["run_id"] == "run-1"
    assert {g["name"] for g in rows[0]["gates"]} == {"workspace_valid", "tdd_red_proven"}
    assert rows[0]["tdd"]["red"]["classification"] == "test_failure"
    assert rows[0]["tdd"]["green"]["exit_code"] == 0


def test_latest_tdd_rows_empty_without_runs(tmp_path) -> None:
    from opencontext_cli.tui.screens.tdd_gates import latest_tdd_rows

    assert latest_tdd_rows(tmp_path) == []


# ---------------------------------------------------------------------------
# Pilot tests — screen rendering
# ---------------------------------------------------------------------------


def test_tdd_gates_screen_renders_gates_and_tdd(workspace) -> None:
    from textual.widgets import Static

    from opencontext_cli.tui.app import OpenContextApp
    from opencontext_cli.tui.screens.tdd_gates import TddGatesScreen

    _write_tdd_run(workspace, "run-1")
    seen: dict[str, str] = {}

    async def scenario() -> None:
        app = OpenContextApp(start="home")
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_screen(TddGatesScreen(root=workspace))
            await pilot.pause()
            seen["text"] = str(app.screen.query_one("#tdd-gates-content", Static).content)
            await pilot.press("q")
            await pilot.press("q")

    asyncio.run(scenario())
    text = seen["text"]
    assert "run-1" in text
    assert "workspace_valid" in text
    assert "tdd_red_proven" in text
    assert "failed" in text
    assert "test_failure" in text
    assert "pytest -q tests/test_widget.py" in text
    assert "exit 1" in text
    assert "exit 0" in text


def test_tdd_gates_screen_empty_state(workspace) -> None:
    from textual.widgets import Static

    from opencontext_cli.tui.app import OpenContextApp
    from opencontext_cli.tui.screens.tdd_gates import TddGatesScreen

    seen: dict[str, str] = {}

    async def scenario() -> None:
        app = OpenContextApp(start="home")
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_screen(TddGatesScreen(root=workspace))
            await pilot.pause()
            seen["text"] = str(app.screen.query_one("#tdd-gates-content", Static).content)
            await pilot.press("q")
            await pilot.press("q")

    asyncio.run(scenario())
    assert "No persisted runs" in seen["text"]


def test_home_screen_lists_tdd_gates_entry() -> None:
    from opencontext_cli.tui.app import HomeScreen

    keys = [key for key, _label in HomeScreen._ACTIONS]
    labels = [label for _key, label in HomeScreen._ACTIONS]
    assert "tdd_gates" in keys
    assert any("TDD Gates" in label for label in labels)
