"""Tests for `opencontext tui` and the run/SDD/doctor/uninstall TUI screens.

Covers the plan's TUI acceptance contracts (TUI-AC-001..TUI-AC-008): smoke
boot, dashboard workspace, run detail, config provenance, SDD artifacts,
memory regression, small terminal, and the no-workspace error. Screens are
driven headless through Textual's ``run_test`` pilot (no TTY, no pexpect);
the pure loaders behind each screen are unit-tested directly.
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


def _write_fake_run(
    root: Path,
    run_id: str,
    *,
    sessions: bool = False,
    created_at: str = "2026-01-01T00:00:00+00:00",
) -> Path:
    """Write a minimal run dir (run.json + gates.json + verification.json)."""
    base = root / ".opencontext" / ("sessions/s1/runs" if sessions else "runs")
    run_dir = base / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "workflow": "oc-flow",
                "status": "completed",
                "task": "Fix the failing widget test",
                "created_at": created_at,
                "changed_files": ["src/widget.py"],
                "tdd": {"mode": "strict", "red": {"exit_code": 1}, "green": {"exit_code": 0}},
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "gates.json").write_text(
        json.dumps(
            {
                "gates": [
                    {
                        "id": "workspace_valid",
                        "phase": "oc-flow",
                        "status": "passed",
                        "message": "ok",
                    },
                    {
                        "id": "verification_executed",
                        "phase": "oc-flow",
                        "status": "passed",
                        "message": "ok",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "verification.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "commands": ["pytest -q"],
                "outcome": "passed",
                "exit_code": 0,
                "summary": "passed",
            }
        ),
        encoding="utf-8",
    )
    return run_dir


def _tui_args(root: Path | None = None, *, smoke: bool = False):
    from opencontext_cli.main import _build_parser

    argv = ["tui"]
    if smoke:
        argv.append("--smoke")
    if root is not None:
        argv.append(str(root))
    return _build_parser().parse_args(argv)


# ---------------------------------------------------------------------------
# Unit tests — pure loaders behind the screens
# ---------------------------------------------------------------------------


def test_list_run_rows_covers_both_layouts_newest_first(tmp_path) -> None:
    from opencontext_cli.tui.screens.runs import list_run_rows

    _write_fake_run(tmp_path, "run-old", created_at="2026-01-01T00:00:00+00:00")
    _write_fake_run(tmp_path, "run-new", sessions=True, created_at="2026-02-01T00:00:00+00:00")

    rows = list_run_rows(tmp_path)
    assert [r["run_id"] for r in rows] == ["run-new", "run-old"]
    assert rows[0]["workflow"] == "oc-flow"
    assert rows[0]["task"] == "Fix the failing widget test"


def test_list_run_rows_reports_canonical_status(tmp_path) -> None:
    from opencontext_cli.tui.screens.runs import list_run_rows

    _write_fake_run(tmp_path, "run-x")  # legacy status "completed"
    rows = list_run_rows(tmp_path)
    assert rows[0]["status"] == "passed"


def test_load_run_detail_collects_evidence(tmp_path) -> None:
    from opencontext_cli.tui.screens.runs import load_run_detail

    run_dir = _write_fake_run(tmp_path, "run-d")
    detail = load_run_detail(run_dir)
    assert detail["gates"][0] == {"name": "workspace_valid", "status": "passed"}
    assert detail["verification"]["outcome"] == "passed"
    assert detail["tdd"]["mode"] == "strict"
    assert detail["changed_files"] == ["src/widget.py"]


def test_doctor_badge_for_pass_warn_fail() -> None:
    from opencontext_cli.tui.screens.doctor import badge_for

    assert badge_for(True, "Indexing configured.") == "pass"
    assert badge_for(True, "Capability graph unavailable: boom.") == "warn"
    assert badge_for(True, "No LLM provider detected — analysis features work.") == "warn"
    assert badge_for(False, "Provider check failed: x") == "fail"


def test_doctor_group_checks_by_area() -> None:
    from opencontext_cli.tui.screens.doctor import group_checks
    from opencontext_core.doctor.checks import DoctorCheck

    checks = [
        DoctorCheck(name="security.mode", ok=True, details="d"),
        DoctorCheck(name="security.fail_closed", ok=True, details="d"),
        DoctorCheck(name="llm.provider", ok=True, details="d"),
    ]
    groups = group_checks(checks)
    assert list(groups) == ["security", "llm"]
    assert len(groups["security"]) == 2


def test_list_sdd_changes_reports_artifacts_and_next(tmp_path) -> None:
    from opencontext_cli.tui.screens.sdd import list_sdd_changes

    change = tmp_path / "openspec" / "changes" / "add-tui"
    change.mkdir(parents=True)
    (change / "proposal.md").write_text("# proposal\n", encoding="utf-8")

    entries = list_sdd_changes(tmp_path)
    assert entries[0]["change"] == "add-tui"
    assert entries[0]["artifacts"]["proposal"] == "done"
    assert entries[0]["artifacts"]["specs"] == "missing"
    assert entries[0]["next"] == "spec"


def test_build_uninstall_preview_lists_managed_paths(tmp_path) -> None:
    from opencontext_cli.tui.screens.uninstall_preview import build_uninstall_preview

    preview = build_uninstall_preview(tmp_path)
    assert "agents" in preview and "results" in preview
    managed = preview["managed_paths"]
    assert managed["source"] == "legacy"  # no install manifest in an empty root
    assert ".opencontext" in managed["created_paths"]


# ---------------------------------------------------------------------------
# TUI-AC-001 — `opencontext tui --smoke` boots headless and quits with q
# ---------------------------------------------------------------------------


def test_tui_smoke_boots_and_quits(workspace) -> None:
    from opencontext_cli.commands.tui_cmd import handle_tui

    assert handle_tui(_tui_args(workspace, smoke=True)) == 0


def test_tui_home_pilot_quits_with_q(workspace) -> None:
    from opencontext_cli.tui.app import OpenContextApp

    async def scenario() -> None:
        app = OpenContextApp(start="home")
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("q")

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# TUI-AC-002 — dashboard shows the detected workspace
# ---------------------------------------------------------------------------


def test_dashboard_shows_workspace(workspace) -> None:
    from opencontext_cli.tui.app import OpenContextApp
    from opencontext_cli.tui.brand import BrandBar

    seen: dict[str, str] = {}

    async def scenario() -> None:
        app = OpenContextApp(start="home")
        async with app.run_test() as pilot:
            await pilot.pause()
            seen["text"] = str(app.screen.query_one(BrandBar).content)
            await pilot.press("q")

    asyncio.run(scenario())
    assert "Project:" in seen["text"]
    assert workspace.name in seen["text"]


# ---------------------------------------------------------------------------
# TUI-AC-003 — run detail shows phases/gates and status
# ---------------------------------------------------------------------------


def test_run_detail_shows_gates_and_status(workspace) -> None:
    from textual.widgets import Static

    from opencontext_cli.tui.app import OpenContextApp
    from opencontext_cli.tui.screens.runs import RunDetailScreen, RunsScreen

    _write_fake_run(workspace, "run-tui-003")
    seen: dict[str, str] = {}

    async def scenario() -> None:
        app = OpenContextApp(start="home")
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_screen(RunsScreen())
            await pilot.pause()
            assert isinstance(app.screen, RunsScreen)
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, RunDetailScreen)
            seen["text"] = str(app.screen.query_one("#run-detail", Static).content)
            await pilot.press("j")  # raw JSON toggle stays crash-free
            await pilot.pause()
            seen["raw"] = str(app.screen.query_one("#run-detail", Static).content)

    asyncio.run(scenario())
    assert "run-tui-003" in seen["text"]
    assert "workspace_valid" in seen["text"]
    assert "passed" in seen["text"]
    assert "src/widget.py" in seen["text"]
    assert "workspace_valid" in seen["raw"]


# ---------------------------------------------------------------------------
# TUI-AC-004 — config screen shows per-key source/provenance
# ---------------------------------------------------------------------------


def test_config_screen_shows_provenance(workspace) -> None:
    from textual.widgets import Label, ListView

    from opencontext_cli.tui.app import OpenContextApp

    seen: dict[str, list[str]] = {}

    async def scenario() -> None:
        app = OpenContextApp(start="config")
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("down")  # category: Project setup → Runtime
            await pilot.pause()
            settings = app.screen.query_one("#settings", ListView)
            seen["labels"] = [str(label.content) for label in settings.query(Label)]
            await pilot.press("q")

    asyncio.run(scenario())
    # ui_language comes from opencontext.yaml; security.mode from the profile overlay.
    assert any("(project)" in label for label in seen["labels"])
    assert any("(profile)" in label for label in seen["labels"])


# ---------------------------------------------------------------------------
# TUI-AC-005 — SDD screen lists existing artifacts
# ---------------------------------------------------------------------------


def test_sdd_screen_lists_artifacts(workspace) -> None:
    from textual.widgets import Static

    from opencontext_cli.tui.app import OpenContextApp
    from opencontext_cli.tui.screens.sdd import SddScreen

    change = workspace / "openspec" / "changes" / "tui-change"
    (change / "specs" / "cap").mkdir(parents=True)
    (change / "proposal.md").write_text("# proposal\n", encoding="utf-8")
    (change / "specs" / "cap" / "spec.md").write_text("# spec\n", encoding="utf-8")
    seen: dict[str, str] = {}

    async def scenario() -> None:
        app = OpenContextApp(start="home")
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_screen(SddScreen())
            await pilot.pause()
            seen["text"] = str(app.screen.query_one("#sdd-content", Static).content)
            await pilot.press("q")
            await pilot.press("q")

    asyncio.run(scenario())
    assert "tui-change" in seen["text"]
    assert "proposal" in seen["text"]
    assert "design" in seen["text"]  # next step after proposal+specs


# ---------------------------------------------------------------------------
# TUI-AC-006 — memory screen regression
# ---------------------------------------------------------------------------


def test_memory_screen_still_works(workspace) -> None:
    from opencontext_cli.tui.app import OpenContextApp
    from opencontext_cli.tui.screens.memory import MemoryBrowserScreen

    async def scenario() -> None:
        app = OpenContextApp(start="cockpit")
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("m")
            await pilot.pause()
            assert isinstance(app.screen, MemoryBrowserScreen)
            await pilot.press("q")
            await pilot.pause()
            await pilot.press("q")

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# TUI-AC-007 — boots in a 20x60 terminal
# ---------------------------------------------------------------------------


def test_small_terminal_boot(workspace) -> None:
    from opencontext_cli.tui.app import OpenContextApp

    async def scenario() -> None:
        app = OpenContextApp(start="home")
        async with app.run_test(size=(60, 20)) as pilot:
            await pilot.pause()
            await pilot.press("q")

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# TUI-AC-008 — readable no-workspace error, never a traceback
# ---------------------------------------------------------------------------


def test_tui_no_workspace_exits_3_with_readable_error(tmp_path, monkeypatch, capsys) -> None:
    from opencontext_cli.commands.tui_cmd import handle_tui

    monkeypatch.chdir(tmp_path)
    rc = handle_tui(_tui_args(tmp_path))
    assert rc == 3
    err = capsys.readouterr().err
    assert "workspace" in err.lower()
    assert "opencontext init" in err


def test_tui_smoke_without_workspace_boots_error_screen(tmp_path, monkeypatch) -> None:
    from opencontext_cli.commands.tui_cmd import handle_tui

    monkeypatch.chdir(tmp_path)
    assert handle_tui(_tui_args(tmp_path, smoke=True)) == 0


def test_no_workspace_error_screen_is_readable(tmp_path, monkeypatch) -> None:
    from textual.widgets import Static

    from opencontext_cli.tui.app import OpenContextApp
    from opencontext_cli.tui.screens.workspace_error import WorkspaceErrorScreen

    monkeypatch.chdir(tmp_path)
    seen: dict[str, str] = {}

    async def scenario() -> None:
        app = OpenContextApp(start="error", root=tmp_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(app.screen, WorkspaceErrorScreen)
            seen["text"] = str(app.screen.query_one("#workspace-error", Static).content)
            await pilot.press("q")

    asyncio.run(scenario())
    assert "workspace" in seen["text"].lower()
    assert "opencontext init" in seen["text"]


# ---------------------------------------------------------------------------
# Doctor and uninstall-preview screens
# ---------------------------------------------------------------------------


def test_doctor_screen_renders_grouped_checks(workspace, monkeypatch) -> None:
    from textual.widgets import Static

    from opencontext_cli.tui.app import OpenContextApp
    from opencontext_cli.tui.screens import doctor as doctor_mod
    from opencontext_core.doctor.checks import DoctorCheck

    monkeypatch.setattr(
        doctor_mod,
        "run_checks",
        lambda root: [
            DoctorCheck(name="security.mode", ok=True, details="Security mode: x."),
            DoctorCheck(name="llm.provider", ok=False, details="Provider check failed."),
        ],
    )
    seen: dict[str, str] = {}

    async def scenario() -> None:
        app = OpenContextApp(start="home")
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_screen(doctor_mod.DoctorScreen())
            text = ""
            for _ in range(30):  # wait for the thread worker, bounded
                await pilot.pause(0.1)
                text = str(app.screen.query_one("#doctor-content", Static).content)
                if "Running" not in text and text.strip():
                    break
            seen["text"] = text
            await pilot.press("q")
            await pilot.press("q")

    asyncio.run(scenario())
    assert "security" in seen["text"]
    assert "fail" in seen["text"]


def test_uninstall_preview_screen_is_read_only_preview(workspace) -> None:
    from textual.widgets import Static

    from opencontext_cli.tui.app import OpenContextApp
    from opencontext_cli.tui.screens.uninstall_preview import UninstallPreviewScreen

    seen: dict[str, str] = {}

    async def scenario() -> None:
        app = OpenContextApp(start="home")
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_screen(UninstallPreviewScreen())
            await pilot.pause()
            seen["text"] = str(app.screen.query_one("#uninstall-preview-content", Static).content)
            await pilot.press("q")
            await pilot.press("q")

    asyncio.run(scenario())
    assert "opencontext.yaml" in seen["text"]
    # Nothing was deleted by opening the preview.
    assert (workspace / "opencontext.yaml").exists()


# ---------------------------------------------------------------------------
# Command registration
# ---------------------------------------------------------------------------


def test_tui_command_is_registered_in_parser() -> None:
    args = _tui_args(smoke=True)
    assert args.command == "tui"
    assert args.smoke is True
    assert args.root is None
