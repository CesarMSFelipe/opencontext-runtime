"""The Configurator writes the right shape per agent and never clobbers."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from opencontext_core.configurator.service import Configurator


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


def test_configure_claude_writes_mcp_servers_and_claude_md(home: Path) -> None:
    report = Configurator(project_root=home).configure(["claude-code"], scope="global")
    assert report["agents_configured"] == 1
    mcp = json.loads((home / ".claude" / "mcp.json").read_text(encoding="utf-8"))
    assert "opencontext" in mcp["mcpServers"]
    claude_md = (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
    assert "<!-- opencontext:instructions:start -->" in claude_md


def test_configure_claude_writes_project_mcp_json(home: Path, tmp_path: Path) -> None:
    """Claude Code reads per-repo MCP servers from a project-root ``.mcp.json``;
    configuring must emit it so a repo gets the OC tools without global config."""
    project = tmp_path / "proj"
    report = Configurator(project_root=project).configure(["claude-code"], scope="local")
    assert report["agents_configured"] == 1

    project_mcp = project / ".mcp.json"
    assert project_mcp.exists(), "project-level .mcp.json was not written"
    data = json.loads(project_mcp.read_text(encoding="utf-8"))
    entry = data["mcpServers"]["opencontext"]
    assert entry == {"type": "stdio", "command": "opencontext", "args": ["mcp"]}


def test_project_mcp_json_merges_and_reverses(home: Path, tmp_path: Path) -> None:
    """The project ``.mcp.json`` merges into a user's existing file and is removed
    cleanly by uninstall, leaving the developer's own servers intact."""
    project = tmp_path / "proj"
    project.mkdir()
    project_mcp = project / ".mcp.json"
    project_mcp.write_text(
        json.dumps({"mcpServers": {"mine": {"command": "x"}}, "userKey": 1}),
        encoding="utf-8",
    )

    cfg = Configurator(project_root=project)
    cfg.configure(["claude-code"], scope="local")
    merged = json.loads(project_mcp.read_text(encoding="utf-8"))
    assert "opencontext" in merged["mcpServers"]
    assert merged["mcpServers"]["mine"] == {"command": "x"}  # user server preserved
    assert merged["userKey"] == 1

    cfg.deconfigure(["claude-code"], scope="local")
    after = json.loads(project_mcp.read_text(encoding="utf-8"))
    assert "opencontext" not in after.get("mcpServers", {})  # ours removed
    assert after["mcpServers"]["mine"] == {"command": "x"}  # user server survives


def test_configure_vscode_uses_servers_root_key(home: Path) -> None:
    Configurator(project_root=home).configure(["vscode-copilot"], scope="global")
    mcp_path = home / ".vscode" / "mcp.json"
    assert mcp_path.exists()
    data = json.loads(mcp_path.read_text(encoding="utf-8"))
    assert "opencontext" in data["servers"]
    assert "mcpServers" not in data


def test_configure_codex_writes_toml(home: Path) -> None:
    Configurator(project_root=home).configure(["codex"], scope="global")
    toml_path = home / ".codex" / "config.toml"
    assert toml_path.exists()
    parsed = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    assert "opencontext" in parsed["mcp_servers"]


def test_agents_md_first_selection(home: Path, tmp_path: Path) -> None:
    """Agents that honor AGENTS.md get a managed block in the project AGENTS.md."""
    project = tmp_path / "proj"
    Configurator(project_root=project).configure(["opencode"], scope="local")
    agents_md = project / "AGENTS.md"
    assert agents_md.exists()
    assert "<!-- opencontext:instructions:start -->" in agents_md.read_text(encoding="utf-8")
    # And NOT a CLAUDE.md or other named file.
    assert not (project / "CLAUDE.md").exists()


def test_no_clobber_user_md(home: Path) -> None:
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True)
    (claude_dir / "CLAUDE.md").write_text("# Mine\n\nKeep this.\n", encoding="utf-8")
    Configurator(project_root=home).configure(["claude-code"], scope="global")
    after = (claude_dir / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Keep this." in after
    assert "<!-- opencontext:instructions:start -->" in after


def test_configure_is_idempotent(home: Path) -> None:
    cfg = Configurator(project_root=home)
    cfg.configure(["claude-code"], scope="global")
    cfg.configure(["claude-code"], scope="global")
    text = (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
    assert text.count("<!-- opencontext:instructions:start -->") == 1
    mcp = json.loads((home / ".claude" / "mcp.json").read_text(encoding="utf-8"))
    assert len(mcp["mcpServers"]) == 1


def test_detect_installed(home: Path) -> None:
    (home / ".claude").mkdir(parents=True)
    (home / ".codex").mkdir(parents=True)
    detected = Configurator(project_root=home).detect_installed()
    assert "claude-code" in detected
    assert "codex" in detected


def test_opencode_local_scope_reports_home_writes(home: Path, tmp_path: Path) -> None:
    project = tmp_path / "proj"
    report = Configurator(project_root=project).configure(["opencode"], scope="local")
    result = report["results"][0]

    assert str(project / "AGENTS.md") in result["local_files_written"]
    assert any(".config/opencode/mcp.json" in p for p in result["global_files_written"])
    assert any(".config/opencode/agents" in p for p in result["global_files_written"])
    assert result["global_write_reason"].startswith("Host-constrained local setup")
    assert not (home / ".config" / "opencode" / "agents" / "sdd-orchestrator.json").exists()


def test_dry_run_reports_exact_opencode_file_plan(home: Path, tmp_path: Path) -> None:
    project = tmp_path / "proj"
    report = Configurator(project_root=project).configure(["opencode"], scope="local", dry_run=True)
    result = report["results"][0]
    planned_paths = {entry["path"] for entry in result["plan"]}

    assert str(project / "AGENTS.md") in planned_paths
    assert any(path.endswith(".config/opencode/mcp.json") for path in planned_paths)
    assert not any(path.endswith("sdd-orchestrator.json") for path in planned_paths)
    assert result["local_files_written"]
    assert result["global_files_written"]
    assert result["global_write_reason"].startswith("Host-constrained local setup")
