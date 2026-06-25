"""REQ-01: workspace-scoped install must not invoke global agent integration.

Verifies that when --scope workspace is passed to _install(), the
"Global agent integration" block (which writes to $HOME/.claude/, etc.)
is entirely skipped.
"""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch


def test_workspace_install_skips_global_agent_installer(tmp_path, monkeypatch):
    """--scope workspace must not call AgentInstaller (which writes global files)."""
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    project_root = tmp_path / "project"
    project_root.mkdir()

    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.chdir(project_root)

    args = argparse.Namespace(
        scope="workspace",
        root=str(project_root),
        yes=True,
        json=False,
        dry_run=False,
        skill_root=None,
        config=None,
    )

    installer_called = []

    def fake_agent_installer(*a, **kw):
        installer_called.append(True)
        m = MagicMock()
        m.detect_installed_agents.return_value = []
        m.install.return_value = {}
        return m

    # Patch everything imported inside _install() so the test is unit-level.
    with (
        patch("opencontext_core.agent_installer.AgentInstaller", fake_agent_installer),
        patch(
            "opencontext_core.install_manager.InstallationManager",
            return_value=MagicMock(
                _is_installed=MagicMock(return_value=False),
                _install_skills=MagicMock(return_value=None),
                _save_state=MagicMock(return_value=None),
            ),
        ),
        patch("opencontext_core.workspace.layout.ensure_workspace"),
        patch("opencontext_core.doctor.checks.run_doctor", return_value=[]),
        patch(
            "opencontext_core.runtime.OpenContextRuntime",
            return_value=MagicMock(config=MagicMock()),
        ),
    ):
        from opencontext_cli.main import _install

        try:
            _install(args)
        except SystemExit:
            pass
        except Exception:
            pass  # other parts of install may fail; that is not what we test

    assert installer_called == [], (
        "--scope workspace must not invoke AgentInstaller (global integration skipped). "
        f"AgentInstaller was called {len(installer_called)} time(s)."
    )


def test_global_install_uses_agent_installer(tmp_path, monkeypatch):
    """Default (global) install DOES call AgentInstaller."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.chdir(project_root)

    args = argparse.Namespace(
        scope=None,  # default → global behaviour
        root=str(project_root),
        yes=True,
        json=False,
        dry_run=False,
        skill_root=None,
        config=None,
    )

    installer_called = []

    def fake_agent_installer(*a, **kw):
        installer_called.append(True)
        m = MagicMock()
        m.detect_installed_agents.return_value = []
        m.install.return_value = {"agents_configured": 0}
        return m

    with (
        patch("opencontext_core.agent_installer.AgentInstaller", fake_agent_installer),
        patch(
            "opencontext_core.install_manager.InstallationManager",
            return_value=MagicMock(
                _is_installed=MagicMock(return_value=False),
                _install_skills=MagicMock(return_value=None),
                _save_state=MagicMock(return_value=None),
            ),
        ),
        patch("opencontext_core.workspace.layout.ensure_workspace"),
        patch("opencontext_core.doctor.checks.run_doctor", return_value=[]),
        patch(
            "opencontext_core.runtime.OpenContextRuntime",
            return_value=MagicMock(config=MagicMock()),
        ),
    ):
        from opencontext_cli.main import _install

        try:
            _install(args)
        except SystemExit:
            pass
        except Exception:
            pass

    assert installer_called, (
        "Global (default) install must call AgentInstaller but it was not called."
    )


def test_workspace_install_writes_nothing_under_home_integration(tmp_path, monkeypatch):
    """End-to-end: a real --scope workspace install must leave $HOME untouched.

    This is the integration counterpart to the unit test above — it runs the
    REAL onboarding/configurator path (no mocking) and asserts that not a single
    file lands under $HOME, while project-local agent files ARE created.
    """
    import subprocess
    import sys

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    (project / "src").mkdir()
    (project / "src" / "app.py").write_text("def h():\n    return 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)

    env = dict(**{k: v for k, v in __import__("os").environ.items()})
    env["HOME"] = str(fake_home)
    env.pop("XDG_CONFIG_HOME", None)
    proc = subprocess.run(
        [
            sys.executable, "-m", "opencontext_cli.main", "install", ".",
            "--yes", "--agent", "claude-code", "--memory", "local",
            "--budget", "warn", "--git", "none", "--scope", "workspace",
        ],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, f"install failed: {proc.stdout}\n{proc.stderr}"

    home_files = [p for p in fake_home.rglob("*") if p.is_file()]
    assert home_files == [], (
        "--scope workspace must not write any file under $HOME. Found: "
        + ", ".join(str(p.relative_to(fake_home)) for p in home_files)
    )
    # Project-local agent wiring must still happen.
    assert (project / ".mcp.json").exists()
    assert (project / "opencontext.yaml").exists()
    assert (project / ".claude" / "agents" / "oc-orchestrator.md").exists()
