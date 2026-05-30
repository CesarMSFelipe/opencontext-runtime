from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import opencontext_cli.commands.setup_cmd as setup_cmd
from opencontext_core.setup.plan import build_plan
from opencontext_core.user_prefs import UserConfigStore


class FakeRuntime:
    def index_project(self, root: str | Path) -> SimpleNamespace:
        return SimpleNamespace(files=["a.py"], symbols=["main"])


class FakeAgentInstaller:
    calls: ClassVar[list[dict[str, object]]] = []

    def __init__(self, project_root: str | Path = ".") -> None:
        self.project_root = Path(project_root)

    def install(self, *, targets: list[object], location: str, yes: bool) -> dict[str, object]:
        self.calls.append({"targets": [str(t) for t in targets], "location": location, "yes": yes})
        return {"status": "installed"}


def test_parse_agents_supports_repeated_and_comma_values() -> None:
    assert setup_cmd._parse_agents(["opencode,cursor", "codex"]) == [
        "opencode",
        "cursor",
        "codex",
    ]


def test_execute_plan_leaves_agents_sdd_and_index_ready(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    monkeypatch.setattr(UserConfigStore, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(UserConfigStore, "CONFIG_FILE", config_dir / "user-config.json")
    monkeypatch.setattr(setup_cmd, "OpenContextRuntime", FakeRuntime)
    monkeypatch.setattr(setup_cmd, "AgentInstaller", FakeAgentInstaller)
    FakeAgentInstaller.calls.clear()

    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    plan = build_plan(preset_id="context-essential", profile_id="developer")

    setup_cmd._execute_plan(
        plan,
        agents=["opencode", "cursor"],
        tdd_mode="ask",
        root=str(project),
        max_tokens=2400,
    )

    prefs = json.loads((config_dir / "user-config.json").read_text(encoding="utf-8"))
    assert prefs["setup_completed"] is True
    assert prefs["active_agent"] == "opencode"
    assert prefs["sdd_tdd_mode"] == "ask"
    assert prefs["sdd_token_budget"] == 2400
    assert prefs["agent_integrations"]["opencode"] is True
    assert prefs["agent_integrations"]["cursor"] is True
    assert (project / ".opencontext" / "sdd" / "context.json").exists()
    assert (project / "AGENTS.md").exists()
    assert (project / ".cursor" / "rules" / "opencontext.mdc").exists()
    assert FakeAgentInstaller.calls
