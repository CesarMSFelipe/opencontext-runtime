"""Three OpenContext personas: data, CLI, and per-agent emission."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from opencontext_cli.commands import persona_cmd
from opencontext_core.configurator.service import Configurator
from opencontext_core.personas import PERSONAS, get_persona

_EXPECTED = {
    "oc-orchestrator",
    "oc-explorer",
    "oc-architect",
    "oc-builder",
    "oc-professor",
    "oc-reviewer",
    "oc-tester",
}


def test_distinct_personas() -> None:
    ids = {p.id for p in PERSONAS}
    assert ids == _EXPECTED
    # Distinct prompts, each grounded in OpenContext tools.
    prompts = [p.system_prompt for p in PERSONAS]
    assert len({*prompts}) == len(_EXPECTED)
    assert all("opencontext_" in p.system_prompt for p in PERSONAS)


def test_get_persona() -> None:
    assert get_persona("oc-professor").name == "OC Professor"
    assert get_persona("nope") is None


def test_persona_cli_list_and_show(capsys) -> None:
    assert persona_cmd.handle_persona(Namespace(persona_command="list")) == 0
    out = capsys.readouterr().out
    assert "oc-orchestrator" in out and "oc-reviewer" in out

    assert persona_cmd.handle_persona(Namespace(persona_command="show", id="oc-reviewer")) == 0
    assert "one finding per line" in capsys.readouterr().out.lower()

    assert persona_cmd.handle_persona(Namespace(persona_command="show", id="ghost")) == 1


def test_configure_writes_persona_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    project = tmp_path / "proj"
    project.mkdir()
    cfg = Configurator(project_root=project)
    cfg.configure(["claude-code"], scope="local")

    agents_dir = project / ".claude" / "agents"
    written = {p.stem for p in agents_dir.glob("oc-*.md")}
    assert written == _EXPECTED
    body = (agents_dir / "oc-orchestrator.md").read_text(encoding="utf-8")
    assert "name: OC Orchestrator" in body

    cfg.deconfigure(["claude-code"], scope="local")
    assert not list(agents_dir.glob("oc-*.md"))
