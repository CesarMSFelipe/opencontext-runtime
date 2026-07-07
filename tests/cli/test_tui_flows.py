"""Pinning tests for the DOC1 §5 mandatory TUI flows (TUI-002/004/006/007).

Each flow is exercised the way the plan requires: run detail must surface the
per-phase breakdown and the run log (TUI-AC-003, TUI-FLOW-002), the SDD
workspace must be able to execute the next phase when it needs no approval
(TUI-FLOW-004), the config inspector must surface validation and cross-layer
conflicts (TUI-FLOW-006), and the uninstall surface must show possible residue
and confirm before removing anything (TUI-FLOW-007). Screens run headless
through Textual's pilot; the pure loaders are unit-tested directly.
"""

from __future__ import annotations

import asyncio
import contextlib
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
    # Path.home() reads USERPROFILE (not HOME) on Windows, so the global-config
    # layer would resolve to the real profile and miss the test's global config.
    # Redirect the Windows home var too so _global_config_path() lands in tmp_path.
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _write_phased_run(root: Path, run_id: str, *, jsonl: bool = False) -> Path:
    """A run whose gates span two phases and whose events form the run log."""
    run_dir = root / ".opencontext" / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "workflow": "oc-flow",
                "status": "completed",
                "task": "Fix the failing widget test",
                "created_at": "2026-01-01T00:00:00+00:00",
                "changed_files": ["src/widget.py"],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "gates.json").write_text(
        json.dumps(
            {
                "gates": [
                    {"id": "context_pack_created", "phase": "explore", "status": "passed"},
                    {"id": "workspace_valid", "phase": "explore", "status": "passed"},
                    {"id": "verification_passed", "phase": "verify", "status": "failed"},
                ]
            }
        ),
        encoding="utf-8",
    )
    events = [
        {
            "index": 0,
            "phase": "explore",
            "action": "run_phase",
            "status": "passed",
            "observation": "phase 'explore' -> passed; 2 gate(s)",
            "timestamp": "2026-01-01T00:00:01Z",
        },
        {
            "index": 1,
            "phase": "verify",
            "action": "run_phase",
            "status": "failed",
            "observation": "verification command exited 1",
            "timestamp": "2026-01-01T00:00:02Z",
        },
    ]
    if jsonl:
        (run_dir / "events.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
        )
    else:
        (run_dir / "events.json").write_text(json.dumps({"events": events}), encoding="utf-8")
    return run_dir


# ---------------------------------------------------------------------------
# TUI-AC-003 — run detail shows the per-phase breakdown with statuses
# ---------------------------------------------------------------------------


def test_run_detail_loader_derives_phase_breakdown(tmp_path) -> None:
    """TUI-AC-003: load_run_detail keeps each gate's phase and derives a
    per-phase breakdown (phase name + rolled-up status) from the gates."""
    from opencontext_cli.tui.screens.runs import load_run_detail

    run_dir = _write_phased_run(tmp_path, "run-phases")
    detail = load_run_detail(run_dir)

    assert detail["gates"][0]["phase"] == "explore"
    assert detail["phases"] == [
        {"phase": "explore", "status": "passed"},
        {"phase": "verify", "status": "failed"},
    ]


def test_run_detail_screen_renders_phases_and_status(workspace) -> None:
    """TUI-AC-003: the run detail screen renders the phase breakdown (each
    phase with its status) alongside the run status."""
    from textual.widgets import Static

    from opencontext_cli.tui.app import OpenContextApp
    from opencontext_cli.tui.screens.runs import RunDetailScreen, RunsScreen

    _write_phased_run(workspace, "run-ac-003")
    seen: dict[str, str] = {}

    async def scenario() -> None:
        app = OpenContextApp(start="home")
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_screen(RunsScreen())
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, RunDetailScreen)
            seen["text"] = str(app.screen.query_one("#run-detail", Static).content)

    asyncio.run(scenario())
    assert "Phases" in seen["text"]
    assert "explore" in seen["text"]
    assert "verify" in seen["text"]
    assert "failed" in seen["text"]  # verify phase rolled up as failed
    assert "passed" in seen["text"]  # explore phase rolled up as passed


# ---------------------------------------------------------------------------
# TUI-FLOW-002 — runs → select → phases → gates → evidence → logs → files
# ---------------------------------------------------------------------------


def test_run_detail_loader_collects_log_events_both_layouts(tmp_path) -> None:
    """TUI-FLOW-002: load_run_detail collects the run log from events.json
    (harness layout) and events.jsonl (session layout) alike."""
    from opencontext_cli.tui.screens.runs import load_run_detail

    detail = load_run_detail(_write_phased_run(tmp_path, "run-log-json"))
    assert [e["action"] for e in detail["log"]] == ["run_phase", "run_phase"]
    assert detail["log"][1]["observation"] == "verification command exited 1"

    detail_jsonl = load_run_detail(_write_phased_run(tmp_path, "run-log-jsonl", jsonl=True))
    assert len(detail_jsonl["log"]) == 2
    assert detail_jsonl["log"][0]["phase"] == "explore"


def test_run_detail_flow_shows_logs_after_selection(workspace) -> None:
    """TUI-FLOW-002: Runs → select run → the detail shows the run log lines
    (event action + observation) together with gates and changed files."""
    from textual.widgets import Static

    from opencontext_cli.tui.app import OpenContextApp
    from opencontext_cli.tui.screens.runs import RunDetailScreen, RunsScreen

    _write_phased_run(workspace, "run-flow-002")
    seen: dict[str, str] = {}

    async def scenario() -> None:
        app = OpenContextApp(start="home")
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_screen(RunsScreen())
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, RunDetailScreen)
            seen["text"] = str(app.screen.query_one("#run-detail", Static).content)

    asyncio.run(scenario())
    assert "Log" in seen["text"]
    assert "verification command exited 1" in seen["text"]
    assert "workspace_valid" in seen["text"]  # gates still there
    assert "src/widget.py" in seen["text"]  # changed files still there


# ---------------------------------------------------------------------------
# TUI-FLOW-004 — SDD workspace can execute the next phase (no approval)
# ---------------------------------------------------------------------------


def _seed_change(root: Path, name: str, *, with_design: bool = False) -> Path:
    change = root / "openspec" / "changes" / name
    (change / "specs" / "cap").mkdir(parents=True)
    (change / "proposal.md").write_text("# proposal\n", encoding="utf-8")
    (change / "specs" / "cap" / "spec.md").write_text("# spec\n", encoding="utf-8")
    if with_design:
        (change / "design.md").write_text("# design\n", encoding="utf-8")
    return change


def test_next_phase_action_classifies_phases() -> None:
    """TUI-FLOW-004: next_phase_action distinguishes runnable planning phases
    from approval-required steps (apply/archive) and non-runnable states."""
    from opencontext_cli.tui.screens.sdd import next_phase_action

    for phase in ("explore", "propose", "spec", "design", "tasks", "verify"):
        assert next_phase_action(phase) == "run"
    for phase in ("apply", "archive"):
        assert next_phase_action(phase) == "approval"
    for phase in ("review", "resolve-blockers", "select-change", "unknown"):
        assert next_phase_action(phase) == "blocked"


def test_sdd_screen_runs_next_phase_without_approval(workspace, monkeypatch) -> None:
    """TUI-FLOW-004: pressing r in the SDD workspace executes the next
    dependency-ready phase through the SDD runner when it needs no approval,
    and surfaces the phase result envelope."""
    import opencontext_sdd.runner as runner_mod
    from textual.widgets import Static

    from opencontext_cli.tui.app import OpenContextApp
    from opencontext_cli.tui.screens.sdd import SddScreen

    _seed_change(workspace, "tui-run-next")  # proposal + specs → next: design
    recorded: dict[str, str] = {}

    def fake_run_phase(phase, *, change=None, cwd=None, **kwargs):
        recorded["phase"] = phase
        recorded["change"] = str(change)
        return runner_mod.PhaseResultEnvelope(
            status="ok",
            executive_summary="design drafted",
            next_recommended="tasks",
            phase=phase,
        )

    monkeypatch.setattr(runner_mod, "run_phase", fake_run_phase)
    seen: dict[str, str] = {}

    async def scenario() -> None:
        app = OpenContextApp(start="home")
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_screen(SddScreen())
            await pilot.pause()
            await pilot.press("r")
            await pilot.pause()
            seen["status"] = str(app.screen.query_one("#sdd-status", Static).content)

    asyncio.run(scenario())
    assert recorded == {"phase": "design", "change": "tui-run-next"}
    assert "design" in seen["status"]
    assert "ok" in seen["status"]


def test_sdd_screen_refuses_approval_required_phase(workspace, monkeypatch) -> None:
    """TUI-FLOW-004: when the next recommended step requires approval (apply),
    r refuses and points at the CLI instead of executing the phase."""
    import opencontext_sdd.runner as runner_mod
    from textual.widgets import Static

    from opencontext_cli.tui.app import OpenContextApp
    from opencontext_cli.tui.screens.sdd import SddScreen

    _seed_change(workspace, "tui-apply-gate", with_design=True)  # next: apply
    recorded: dict[str, str] = {}
    monkeypatch.setattr(
        runner_mod, "run_phase", lambda *a, **k: recorded.setdefault("called", "yes")
    )
    seen: dict[str, str] = {}

    async def scenario() -> None:
        app = OpenContextApp(start="home")
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_screen(SddScreen())
            await pilot.pause()
            await pilot.press("r")
            await pilot.pause()
            seen["status"] = str(app.screen.query_one("#sdd-status", Static).content)

    asyncio.run(scenario())
    assert recorded == {}, "approval-required phase must not execute from the TUI"
    assert "approval" in seen["status"]


# ---------------------------------------------------------------------------
# TUI-FLOW-006 — config inspector: validation, conflicts, active overrides
# ---------------------------------------------------------------------------


def _write_global_config(home: Path, content: str) -> Path:
    from opencontext_core.paths import StorageMode, resolve_workspace_path

    path = resolve_workspace_path(home, StorageMode.local) / "config.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_build_config_validation_reports_diags_conflicts_overrides(workspace) -> None:
    """TUI-FLOW-006: build_config_validation returns schema validation
    diagnostics, cross-layer conflicts (same key set by 2+ non-default layers,
    with the winner), and the active overrides above defaults."""
    from opencontext_cli.tui.app import build_config_validation

    # global layer also sets ui_language → real conflict with the project layer
    _write_global_config(workspace, "ui_language: es\n")

    info = build_config_validation(".")

    assert any(d["name"] == "config.file" and d["status"] == "passed" for d in info["diagnostics"])
    assert "ui_language" in info["conflicts"]
    conflict = info["conflicts"]["ui_language"]
    assert "global" in conflict["layers"] and "project" in conflict["layers"]
    assert conflict["winner"] == "project"
    assert info["overrides"]["ui_language"] == "project"


def test_config_screen_shows_validation_and_conflicts_panel(workspace) -> None:
    """TUI-FLOW-006: pressing v in the config inspector surfaces the
    validation results and the cross-layer conflict list on screen."""
    from textual.widgets import Static

    from opencontext_cli.tui.app import OpenContextApp

    _write_global_config(workspace, "ui_language: es\n")
    seen: dict[str, str] = {}

    async def scenario() -> None:
        app = OpenContextApp(start="config")
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("v")
            await pilot.pause()
            seen["info"] = str(app.screen.query_one("#info", Static).content)
            await pilot.press("q")

    asyncio.run(scenario())
    assert "Validation" in seen["info"]
    assert "Conflicts" in seen["info"]
    assert "ui_language" in seen["info"]
    assert "project" in seen["info"]  # the winning layer is named


# ---------------------------------------------------------------------------
# TUI-FLOW-007 — uninstall: managed paths, possible residue, confirmation
# ---------------------------------------------------------------------------


def test_uninstall_preview_reports_possible_residue(workspace) -> None:
    """TUI-FLOW-007: build_uninstall_preview includes the possible-residue
    report (same detector as 'opencontext uninstall verify') without deleting
    anything."""
    from opencontext_cli.tui.screens.uninstall_preview import build_uninstall_preview

    preview = build_uninstall_preview(workspace)

    residue = preview["possible_residue"]
    assert any("opencontext.yaml" in path for path in residue)
    assert (workspace / "opencontext.yaml").exists()  # report-only


def test_uninstall_preview_screen_renders_residue_section(workspace) -> None:
    """TUI-FLOW-007: the uninstall preview screen renders the possible-residue
    section next to the managed paths (dry-run stays read-only)."""
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
    assert "residue" in seen["text"].lower()
    assert "opencontext.yaml" in seen["text"]
    assert (workspace / "opencontext.yaml").exists()


def test_home_uninstall_entry_confirms_and_decline_is_safe(workspace, monkeypatch) -> None:
    """TUI-FLOW-007: the home-menu Uninstall entry invokes the managed
    uninstall handler, which asks for confirmation first — declining removes
    nothing from the workspace."""
    from textual.widgets import ListView

    from opencontext_cli.tui.app import HomeScreen, OpenContextApp
    from opencontext_core import prompts

    asked: dict[str, str] = {}

    def fake_confirm(message: str, default: bool = False, **kwargs) -> bool:
        asked["message"] = str(message)
        return False  # decline

    monkeypatch.setattr(prompts, "confirm", fake_confirm)
    monkeypatch.setattr(prompts, "pause", lambda *a, **k: None)
    # The pilot's headless driver cannot really suspend; the wiring under test
    # is entry → handler → confirmation, not terminal suspension itself.
    monkeypatch.setattr(
        OpenContextApp, "suspend", lambda self: contextlib.nullcontext(), raising=False
    )

    idx = [key for key, _label in HomeScreen._ACTIONS].index("uninstall")

    async def scenario() -> None:
        app = OpenContextApp(start="home")
        async with app.run_test() as pilot:
            await pilot.pause()
            app.screen.query_one("#home", ListView).index = idx
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("q")

    asyncio.run(scenario())
    assert asked, "the uninstall entry never asked for confirmation"
    assert "remove" in asked["message"].lower()
    assert (workspace / "opencontext.yaml").exists()  # decline removed nothing
