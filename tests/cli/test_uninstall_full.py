"""Tests for uninstall --full, --verify, and verify_no_traces."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from opencontext_cli.commands.uninstall_cmd import (
    _purge_project_artifacts,
    verify_no_global_traces,
    verify_no_traces,
)


def _isolate_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    """Redirect ``Path.home()``/``expanduser`` to *home* on every OS.

    POSIX ``expanduser`` consults ``HOME``; Windows consults ``USERPROFILE``
    first, so setting ``HOME`` alone leaks the real home (and the real
    ``~/.config/opencontext``) into the verify/uninstall scans on Windows.
    """
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))


# ---------------------------------------------------------------------------
# verify_no_traces unit tests
# ---------------------------------------------------------------------------


def test_verify_no_traces_clean(tmp_path):
    assert verify_no_traces(tmp_path) == []


def test_verify_no_traces_detects_oc_agent_file(tmp_path):
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "oc-orchestrator.md").write_text("hello", encoding="utf-8")
    residue = verify_no_traces(tmp_path)
    assert any("oc-orchestrator.md" in r for r in residue)


def test_verify_no_traces_clean_after_removal(tmp_path):
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    f = agents_dir / "oc-orchestrator.md"
    f.write_text("hello", encoding="utf-8")
    assert verify_no_traces(tmp_path) != []
    f.unlink()
    assert verify_no_traces(tmp_path) == []


def test_verify_no_traces_detects_opencontext_dir(tmp_path):
    oc_dir = tmp_path / ".opencontext"
    oc_dir.mkdir()
    residue = verify_no_traces(tmp_path)
    assert any(".opencontext" in r for r in residue)


def test_verify_no_traces_detects_mcp_json(tmp_path):
    (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
    residue = verify_no_traces(tmp_path)
    assert any(".mcp.json" in r for r in residue)


# ---------------------------------------------------------------------------
# --full without --yes in non-TTY aborts
# ---------------------------------------------------------------------------


def test_full_without_yes_non_tty_exits(tmp_path, monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    # Patch _resolve_flag in opencontext_cli.main so the import inside handle_uninstall
    # returns the value as-is (no env-var override).
    import opencontext_cli.main as main_mod

    monkeypatch.setattr(main_mod, "_resolve_flag", lambda v, _: v)
    args = SimpleNamespace(
        full=True,
        verify=False,
        yes=False,
        dry_run=False,
        json=False,
        scope="local",
        root=str(tmp_path),
        all_agents=False,
        agents=[],
        purge=False,
    )
    from opencontext_cli.commands.uninstall_cmd import handle_uninstall

    with pytest.raises(SystemExit) as exc_info:
        handle_uninstall(args)
    assert exc_info.value.code != 0


# ---------------------------------------------------------------------------
# --verify exits 0 when clean, 1 when traces remain
# ---------------------------------------------------------------------------


def test_verify_flag_exits_0_when_clean(tmp_path, monkeypatch):
    import opencontext_cli.main as main_mod

    # Isolate HOME so verify's global-trace scan sees a clean machine, not the
    # developer's real ~/.config/opencontext or installed global personas.
    home = tmp_path / "home"
    home.mkdir()
    _isolate_home(monkeypatch, home)
    monkeypatch.setattr(main_mod, "_resolve_flag", lambda v, _: v)
    args = SimpleNamespace(
        verify=True,
        full=False,
        yes=False,
        dry_run=False,
        json=False,
        scope="local",
        root=str(tmp_path),
        all_agents=False,
        agents=[],
        purge=False,
    )
    from opencontext_cli.commands.uninstall_cmd import handle_uninstall

    with pytest.raises(SystemExit) as exc_info:
        handle_uninstall(args)
    assert exc_info.value.code == 0


def test_verify_flag_exits_1_when_traces(tmp_path, monkeypatch):
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "oc-orchestrator.md").write_text("hi", encoding="utf-8")
    import opencontext_cli.main as main_mod

    monkeypatch.setattr(main_mod, "_resolve_flag", lambda v, _: v)
    args = SimpleNamespace(
        verify=True,
        full=False,
        yes=False,
        dry_run=False,
        json=False,
        scope="local",
        root=str(tmp_path),
        all_agents=False,
        agents=[],
        purge=False,
    )
    from opencontext_cli.commands.uninstall_cmd import handle_uninstall

    with pytest.raises(SystemExit) as exc_info:
        handle_uninstall(args)
    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# --full does not delete untracked files
# ---------------------------------------------------------------------------


def test_purge_removes_oc_storage_leaves_sibling(tmp_path):
    """--purge removes .storage/opencontext but leaves .storage/other-tool."""
    oc_storage = tmp_path / ".storage" / "opencontext"
    oc_storage.mkdir(parents=True)
    sibling = tmp_path / ".storage" / "other-tool"
    sibling.mkdir()

    _purge_project_artifacts(tmp_path)

    assert not oc_storage.exists()
    assert sibling.exists()
    assert (tmp_path / ".storage").exists()  # non-empty, so not removed


def test_purge_removes_empty_storage_parent(tmp_path):
    """When .storage/opencontext is the only child, .storage itself is removed."""
    oc_storage = tmp_path / ".storage" / "opencontext"
    oc_storage.mkdir(parents=True)

    _purge_project_artifacts(tmp_path)

    assert not oc_storage.exists()
    assert not (tmp_path / ".storage").exists()


def test_full_does_not_delete_untracked(tmp_path, monkeypatch):
    """A user file not tracked in the ledger survives --full --yes."""
    user_file = tmp_path / "my_custom_file.txt"
    user_file.write_text("keep me", encoding="utf-8")

    import opencontext_cli.main as main_mod

    monkeypatch.setattr(main_mod, "_resolve_flag", lambda v, _: v)
    args = SimpleNamespace(
        full=True,
        verify=False,
        yes=True,
        dry_run=False,
        json=True,
        scope="local",
        root=str(tmp_path),
        all_agents=False,
        agents=[],
        purge=False,
    )
    from opencontext_cli.commands.uninstall_cmd import handle_uninstall

    handle_uninstall(args)

    assert user_file.exists()
    assert user_file.read_text(encoding="utf-8") == "keep me"


# ---------------------------------------------------------------------------
# REQ-02: --full --dry-run must NOT require --yes
# ---------------------------------------------------------------------------


def test_full_dry_run_no_yes_required(tmp_path, monkeypatch, capsys):
    """--full --dry-run exits 0 without --yes and must not delete any files."""
    monkeypatch.chdir(tmp_path)
    mcp = tmp_path / ".mcp.json"
    mcp.write_text("{}", encoding="utf-8")

    import opencontext_cli.main as main_mod

    monkeypatch.setattr(main_mod, "_resolve_flag", lambda v, _: v)
    args = SimpleNamespace(
        full=True,
        verify=False,
        yes=False,  # no --yes
        dry_run=True,  # --dry-run
        json=False,
        scope="local",
        root=str(tmp_path),
        all_agents=False,
        agents=[],
        purge=False,
    )
    from opencontext_cli.commands.uninstall_cmd import handle_uninstall

    # Must not raise SystemExit with a non-zero code.
    try:
        handle_uninstall(args)
    except SystemExit as exc:
        assert exc.code in (None, 0), f"--dry-run exited with non-zero code: {exc.code}"

    # The file must NOT have been deleted.
    assert mcp.exists(), ".mcp.json was deleted despite --dry-run"

    out = capsys.readouterr().out
    assert "dry" in out.lower() or "Dry" in out, "output must indicate dry-run mode"


# ---------------------------------------------------------------------------
# REQ-03: --full --yes must purge .mcp.json
# ---------------------------------------------------------------------------


def test_mcp_json_purged_on_full_uninstall(tmp_path, monkeypatch):
    """--full --yes deletes .mcp.json when present."""
    from unittest.mock import patch

    monkeypatch.chdir(tmp_path)
    mcp = tmp_path / ".mcp.json"
    mcp.write_text('{"mcpServers":{}}', encoding="utf-8")

    import opencontext_cli.main as main_mod

    monkeypatch.setattr(main_mod, "_resolve_flag", lambda v, _: v)
    args = SimpleNamespace(
        full=True,
        verify=False,
        yes=True,
        dry_run=False,
        json=True,  # JSON suppresses Rich output
        scope="local",
        root=str(tmp_path),
        all_agents=False,
        agents=[],
        purge=False,
    )

    with (
        patch("opencontext_cli.commands.uninstall_cmd.Configurator") as mock_cfg,
        patch("opencontext_core.install_manager.InstallationManager") as mock_im,
    ):
        mock_cfg.return_value.detect_installed.return_value = []
        mock_cfg.return_value.deconfigure.return_value = {"results": []}
        mock_im.return_value._load_state.return_value = None
        mock_im.return_value.clear_state.return_value = True

        from opencontext_cli.commands.uninstall_cmd import handle_uninstall

        try:
            handle_uninstall(args)
        except SystemExit as exc:
            assert exc.code in (None, 0), f"full uninstall exited non-zero: {exc.code}"

    assert not mcp.exists(), ".mcp.json was NOT deleted by --full --yes"


def test_mcp_json_absent_no_error_on_full_uninstall(tmp_path, monkeypatch):
    """--full --yes succeeds without error when .mcp.json is absent."""
    from unittest.mock import patch

    monkeypatch.chdir(tmp_path)
    assert not (tmp_path / ".mcp.json").exists()

    import opencontext_cli.main as main_mod

    monkeypatch.setattr(main_mod, "_resolve_flag", lambda v, _: v)
    args = SimpleNamespace(
        full=True,
        verify=False,
        yes=True,
        dry_run=False,
        json=True,
        scope="local",
        root=str(tmp_path),
        all_agents=False,
        agents=[],
        purge=False,
    )

    with (
        patch("opencontext_cli.commands.uninstall_cmd.Configurator") as mock_cfg,
        patch("opencontext_core.install_manager.InstallationManager") as mock_im,
    ):
        mock_cfg.return_value.detect_installed.return_value = []
        mock_cfg.return_value.deconfigure.return_value = {"results": []}
        mock_im.return_value._load_state.return_value = None
        mock_im.return_value.clear_state.return_value = True

        from opencontext_cli.commands.uninstall_cmd import handle_uninstall

        try:
            handle_uninstall(args)
        except SystemExit as exc:
            assert exc.code in (None, 0), f"full uninstall exited non-zero: {exc.code}"


def test_full_uninstall_leaves_no_opencontext_dir(tmp_path, monkeypatch):
    """Regression: --full must not leave .opencontext behind.

    InstallationManager.__init__ eagerly recreates .opencontext/{agent-configs,
    backups}; if the purge runs before the last InstallationManager() call, the
    constructor resurrects .opencontext and verify fails. Uses the REAL manager
    (HOME redirected) so the recreation side-effect is exercised.
    """
    home = tmp_path / "home"
    home.mkdir()
    _isolate_home(monkeypatch, home)
    project = tmp_path / "project"
    project.mkdir()
    # Simulate an installed project.
    (project / ".opencontext" / "agent-configs").mkdir(parents=True)
    (project / ".opencontext" / "backups").mkdir(parents=True)
    (project / ".opencontext" / "harness.yaml").write_text("x", encoding="utf-8")
    (project / "opencontext.yaml").write_text("version: 1\n", encoding="utf-8")
    (project / ".mcp.json").write_text('{"mcpServers":{}}', encoding="utf-8")

    from opencontext_cli.commands.uninstall_cmd import _run_full_uninstall, verify_no_traces

    _run_full_uninstall(str(project), "workspace", json_output=True)

    assert not (project / ".opencontext").exists(), (
        ".opencontext must be gone after --full uninstall (InstallationManager "
        "recreation must not survive the purge)."
    )
    assert verify_no_traces(str(project)) == []


# ---------------------------------------------------------------------------
# T4 (REQ-4): empty .claude parent is removed; non-empty .claude stays
# ---------------------------------------------------------------------------


def test_empty_claude_parent_removed_after_full_uninstall(tmp_path, monkeypatch):
    """After sweeping oc-* files, the empty .claude/ dir must be removed."""
    home = tmp_path / "home"
    home.mkdir()
    _isolate_home(monkeypatch, home)
    project = tmp_path / "project"
    project.mkdir()

    # Simulate OC-managed dirs with only the oc-* files we'll sweep.
    agents_dir = project / ".claude" / "agents"
    commands_dir = project / ".claude" / "commands"
    agents_dir.mkdir(parents=True)
    commands_dir.mkdir(parents=True)
    (agents_dir / "oc-orchestrator.md").write_text("# OC agent", encoding="utf-8")
    (commands_dir / "oc-run.md").write_text("# OC cmd", encoding="utf-8")

    from opencontext_cli.commands.uninstall_cmd import _run_full_uninstall

    _run_full_uninstall(str(project), "local", json_output=True)

    assert not (project / ".claude").exists(), (
        ".claude/ must be removed when empty after full uninstall"
    )


def test_nonempty_claude_parent_left_intact_after_full_uninstall(tmp_path, monkeypatch):
    """When .claude/ still has user content after sweep, it must stay."""
    home = tmp_path / "home"
    home.mkdir()
    _isolate_home(monkeypatch, home)
    project = tmp_path / "project"
    project.mkdir()

    # OC subdirs + user file in .claude/ root that the sweep won't touch.
    agents_dir = project / ".claude" / "agents"
    commands_dir = project / ".claude" / "commands"
    agents_dir.mkdir(parents=True)
    commands_dir.mkdir(parents=True)
    (agents_dir / "oc-orchestrator.md").write_text("# OC agent", encoding="utf-8")
    user_file = project / ".claude" / "settings.json"
    user_file.write_text('{"key": "value"}', encoding="utf-8")

    from opencontext_cli.commands.uninstall_cmd import _run_full_uninstall

    _run_full_uninstall(str(project), "local", json_output=True)

    assert (project / ".claude").exists(), ".claude/ must remain when it contains user content"
    assert user_file.exists(), "user's settings.json must not be deleted"


# ---------------------------------------------------------------------------
# verify_no_global_traces: detect home MCP entry, global personas, HOME state
# ---------------------------------------------------------------------------


def test_verify_no_global_traces_clean(tmp_path, monkeypatch):
    """An isolated, empty HOME has no global residue."""
    home = tmp_path / "home"
    home.mkdir()
    _isolate_home(monkeypatch, home)
    assert verify_no_global_traces([]) == []


def test_verify_no_global_traces_detects_home_mcp_entry(tmp_path, monkeypatch):
    """The home mcp.json opencontext server is detected by parsing (regex misses it)."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    _isolate_home(monkeypatch, home)
    mcp = home / ".claude" / "mcp.json"
    mcp.write_text(
        json.dumps({"mcpServers": {"opencontext": {"command": "opencontext"}}}),
        encoding="utf-8",
    )
    residue = verify_no_global_traces([])
    assert any(str(mcp) == r for r in residue)


def test_verify_no_global_traces_ignores_clean_home_mcp(tmp_path, monkeypatch):
    """A home mcp.json without our server is not flagged."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    _isolate_home(monkeypatch, home)
    (home / ".claude" / "mcp.json").write_text(
        json.dumps({"mcpServers": {"mine": {"command": "x"}}}), encoding="utf-8"
    )
    assert verify_no_global_traces([]) == []


def test_verify_no_global_traces_detects_global_personas(tmp_path, monkeypatch):
    """oc-*.md persona files in opencode's home agents dir are detected."""
    home = tmp_path / "home"
    agents = home / ".config" / "opencode" / "agents"
    agents.mkdir(parents=True)
    _isolate_home(monkeypatch, home)
    persona = agents / "oc-orchestrator.md"
    persona.write_text("# persona", encoding="utf-8")
    residue = verify_no_global_traces([])
    assert any(str(persona) == r for r in residue)


def test_verify_no_global_traces_detects_state_dirs(tmp_path, monkeypatch):
    """~/.config/opencontext and ~/.opencontext/backups are detected as residue."""
    home = tmp_path / "home"
    home.mkdir()
    _isolate_home(monkeypatch, home)
    (home / ".config" / "opencontext").mkdir(parents=True)
    (home / ".opencontext" / "backups").mkdir(parents=True)
    residue = verify_no_global_traces([])
    assert any("opencontext" in r and ".config" in r for r in residue)
    assert any(r.endswith("backups") for r in residue)


def test_verify_flag_exits_1_on_global_only_residue(tmp_path, monkeypatch):
    """A clean project but global HOME state present must make --verify exit non-zero.

    Anti-regression for the old `passed = len(residue) == 0` that ignored global
    residue, so verify reported clean while ~/.config/opencontext survived.
    """
    home = tmp_path / "home"
    home.mkdir()
    _isolate_home(monkeypatch, home)
    (home / ".config" / "opencontext").mkdir(parents=True)
    project = tmp_path / "project"
    project.mkdir()  # no OpenContext project traces

    import opencontext_cli.main as main_mod

    monkeypatch.setattr(main_mod, "_resolve_flag", lambda v, _: v)
    args = SimpleNamespace(
        verify=True,
        full=False,
        yes=False,
        dry_run=False,
        json=False,
        scope="local",
        root=str(project),
        all_agents=False,
        agents=[],
        purge=False,
    )
    from opencontext_cli.commands.uninstall_cmd import handle_uninstall

    with pytest.raises(SystemExit) as exc_info:
        handle_uninstall(args)
    assert exc_info.value.code == 1


def test_full_uninstall_global_state_removes_home_opencontext_state(tmp_path, monkeypatch):
    """--full --global-state removes known OpenContext HOME state."""
    home = tmp_path / "home"
    home.mkdir()
    _isolate_home(monkeypatch, home)
    project = tmp_path / "project"
    project.mkdir()

    profile = home / ".config" / "opencontext" / "profiles" / "default.json"
    profile.parent.mkdir(parents=True)
    profile.write_text("{}", encoding="utf-8")
    backup = home / ".opencontext" / "backups" / "b1" / "file.txt"
    backup.parent.mkdir(parents=True)
    backup.write_text("x", encoding="utf-8")

    from opencontext_cli.commands.uninstall_cmd import _run_full_uninstall

    _run_full_uninstall(str(project), "local", json_output=True, global_state=True)

    assert not (home / ".config" / "opencontext").exists()
    assert not (home / ".opencontext" / "backups").exists()
