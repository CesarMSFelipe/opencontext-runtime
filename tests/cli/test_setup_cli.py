"""CLI tests for the `opencontext setup` agent-configuration command.

These tests exercise the headline "configure my agent(s)" path that wires
the parser into ``Configurator``. Every test monkeypatches ``Path.home`` to a
temp dir and uses a tmp project root so nothing is written into the repo.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import opencontext_cli.commands.setup_cmd as setup_cmd
import opencontext_cli.main as cli_main


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point Path.home at a temp dir so agent home dirs never touch the repo."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    proj.mkdir()
    return proj


def _parse(argv: list[str]):
    return cli_main._build_parser().parse_args(argv)


def test_setup_configures_named_agent_and_reports(
    home: Path, project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _parse(["setup", "claude-code", "--scope", "global", "--root", str(project), "--yes"])
    cli_main._dispatch(args)

    # The managed instructions block landed in the agent's CLAUDE.md.
    claude_md = (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
    assert "<!-- opencontext:instructions:start -->" in claude_md
    # MCP server entry was written.
    mcp = json.loads((home / ".claude" / "mcp.json").read_text(encoding="utf-8"))
    assert "opencontext" in mcp["mcpServers"]
    # The human report mentions the agent that was configured.
    out = capsys.readouterr().out
    assert "claude-code" in out


def test_setup_local_scope_writes_project_agents_md(
    home: Path, project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _parse(["setup", "opencode", "--root", str(project), "--yes"])
    cli_main._dispatch(args)

    agents_md = project / "AGENTS.md"
    assert agents_md.exists()
    assert "<!-- opencontext:instructions:start -->" in agents_md.read_text(encoding="utf-8")


def test_setup_dry_run_writes_nothing(
    home: Path, project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _parse(
        ["setup", "claude-code", "--scope", "global", "--root", str(project), "--dry-run"]
    )
    cli_main._dispatch(args)

    assert not (home / ".claude" / "CLAUDE.md").exists()
    assert not (home / ".claude" / "mcp.json").exists()
    assert not (project / "AGENTS.md").exists()
    out = capsys.readouterr().out.lower()
    assert "dry" in out
    # Dry-run still names the agent it *would* configure.
    assert "claude-code" in out


def test_setup_no_args_configures_detected_agents(
    home: Path, project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Simulate an installed agent by creating its config dir under the temp home.
    (home / ".codex").mkdir(parents=True)

    args = _parse(["setup", "--root", str(project), "--yes"])
    cli_main._dispatch(args)

    # codex is project-scoped for instructions and writes TOML mcp config in home.
    assert (home / ".codex" / "config.toml").exists()
    out = capsys.readouterr().out
    assert "codex" in out


def test_setup_no_detected_agents_reports_hint(
    home: Path, project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _parse(["setup", "--root", str(project), "--yes"])
    cli_main._dispatch(args)

    out = capsys.readouterr().out.lower()
    assert "no" in out and "agent" in out


def test_setup_all_configures_every_known_agent(
    home: Path, project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _parse(["setup", "--all", "--scope", "global", "--root", str(project), "--yes"])
    cli_main._dispatch(args)

    out = capsys.readouterr().out
    # A representative sample of known agents should be reported.
    assert "claude-code" in out
    assert "codex" in out
    # And the home dirs were actually created.
    assert (home / ".claude").exists()
    assert (home / ".codex").exists()


def test_setup_json_output_is_machine_readable(
    home: Path, project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _parse(
        ["setup", "claude-code", "--scope", "global", "--root", str(project), "--yes", "--json"]
    )
    cli_main._dispatch(args)

    payload = json.loads(capsys.readouterr().out)
    assert payload["agents_configured"] == 1
    assert payload["scope"] == "global"
    assert payload["results"][0]["agent"] == "claude-code"


def test_setup_unknown_agent_is_reported_not_crash(
    home: Path, project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _parse(["setup", "definitely-not-an-agent", "--root", str(project), "--yes"])
    cli_main._dispatch(args)

    out = capsys.readouterr().out.lower()
    assert "definitely-not-an-agent" in out
    assert "unknown" in out or "skip" in out


def test_setup_preset_path_still_dispatches_to_legacy(
    home: Path, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Back-compat: --preset must still drive the legacy plan-based installer."""
    called: dict[str, object] = {}

    def _fake_automated(*args: object, **kwargs: object) -> None:
        called["hit"] = True

    monkeypatch.setattr(setup_cmd, "_run_automated", _fake_automated)

    args = _parse(
        ["setup", "--preset", "context-first", "--non-interactive", "--root", str(project)]
    )
    cli_main._dispatch(args)
    assert called.get("hit") is True


def test_setup_without_yes_proceeds_on_non_tty(
    home: Path, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-interactive stdin (CI) must not block on a confirmation prompt."""
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    args = _parse(["setup", "claude-code", "--scope", "global", "--root", str(project)])
    cli_main._dispatch(args)

    assert (home / ".claude" / "CLAUDE.md").exists()


def test_setup_without_yes_respects_confirm_decline(
    home: Path, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On an interactive stdin, declining the prompt writes nothing."""
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(setup_cmd.prompts, "confirm", lambda *a, **k: False)

    args = _parse(["setup", "claude-code", "--scope", "global", "--root", str(project)])
    cli_main._dispatch(args)

    assert not (home / ".claude" / "CLAUDE.md").exists()


def test_setup_dry_run_via_env(
    home: Path, project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """OPENCONTEXT_DRY_RUN enables dry-run when the flag is absent."""
    monkeypatch.setenv("OPENCONTEXT_DRY_RUN", "1")

    args = _parse(["setup", "claude-code", "--scope", "global", "--root", str(project), "--yes"])
    cli_main._dispatch(args)

    assert not (home / ".claude" / "CLAUDE.md").exists()
    assert "dry" in capsys.readouterr().out.lower()


def test_setup_parse_agents_helper_unchanged() -> None:
    """The legacy helper that other tests rely on keeps its behavior."""
    assert setup_cmd._parse_agents(["opencode,cursor", "codex"]) == [
        "opencode",
        "cursor",
        "codex",
    ]
