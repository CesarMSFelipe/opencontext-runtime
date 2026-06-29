"""Three OpenContext personas: data, CLI, and per-agent emission."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from opencontext_cli.commands import persona_cmd
from opencontext_core.configurator.service import Configurator
from opencontext_core.personas import PERSONAS, PHASE_PERSONAS, get_persona

_PUBLIC_EXPECTED = {
    "oc-orchestrator",
    "oc-professor",
    "oc-reviewer",
}

_EXPECTED = {
    "oc-orchestrator",
    "oc-explorer",
    "oc-architect",
    "oc-builder",
    "oc-professor",
    "oc-reviewer",
    "oc-tester",
    "oc-context-engineer",
    "oc-requirements",
    "oc-planner",
    "oc-harness-verifier",
    "oc-archivist",
    "oc-evolution-steward",
    # PR-006 added the two missing book built-ins (doc 05 §7.11/§7.12).
    "oc-diagnostician",
    "oc-security-reviewer",
}


def test_phase_personas_mapping() -> None:
    assert PHASE_PERSONAS["spec"] == "oc-requirements"
    assert PHASE_PERSONAS["tasks"] == "oc-planner"
    assert PHASE_PERSONAS["verify"] == "oc-harness-verifier"


def test_distinct_personas() -> None:
    ids = {p.id for p in PERSONAS}
    assert ids == _EXPECTED
    # Distinct prompts, each grounded in OpenContext tools.
    prompts = [p.system_prompt for p in PERSONAS]
    assert len({*prompts}) == len(_EXPECTED)
    assert all("opencontext_" in p.system_prompt for p in PERSONAS)


def test_every_persona_prompt_primes_memory_and_stays_kg_first() -> None:
    """The prime->act->save loop lives in the prompt body, not just frontmatter:
    every loop-running persona's system_prompt instructs priming with
    opencontext_memory_context, and NO persona regresses the KG-first contract by
    allowing native Grep/Glob. The Professor is the standalone teaching persona and
    is intentionally not a phase driver, so it does not run the prime->act->save loop."""
    for persona in PERSONAS:
        if persona.id != "oc-professor":
            assert "opencontext_memory_context" in persona.system_prompt, (
                f"{persona.id} never primes memory in its prompt"
            )
        assert "Grep" not in persona.tools, f"{persona.id} leaks native Grep"
        assert "Glob" not in persona.tools, f"{persona.id} leaks native Glob"


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


def test_every_persona_has_a_tool_allowlist() -> None:
    """KG-first is enforced by a per-persona tool surface: every persona allows the
    opencontext MCP tools and never the native code-search tools (Grep/Glob)."""
    for persona in PERSONAS:
        assert persona.tools, f"{persona.id} has no tool allow-list"
        joined = " ".join(persona.tools)
        assert "opencontext_" in joined, f"{persona.id} cannot reach the KG"
        assert "Grep" not in persona.tools, f"{persona.id} leaks native Grep"
        assert "Glob" not in persona.tools, f"{persona.id} leaks native Glob"
    # Writers may edit; read-only phases may not.
    assert "Edit" in get_persona("oc-builder").tools
    assert "Write" in get_persona("oc-tester").tools
    assert "Edit" not in get_persona("oc-explorer").tools
    assert "Write" not in get_persona("oc-reviewer").tools


def test_configure_writes_persona_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    project = tmp_path / "proj"
    project.mkdir()
    cfg = Configurator(project_root=project)
    cfg.configure(["claude-code"], scope="local")

    agents_dir = project / ".claude" / "agents"
    written = {p.stem for p in agents_dir.glob("oc-*.md")}
    assert written == _PUBLIC_EXPECTED
    body = (agents_dir / "oc-orchestrator.md").read_text(encoding="utf-8")
    assert "name: OC Orchestrator" in body

    cfg.deconfigure(["claude-code"], scope="local")
    assert not list(agents_dir.glob("oc-*.md"))


def test_rendered_persona_has_tools_frontmatter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rendered persona file pins its tool surface in frontmatter: the KG tools
    are present and native Grep is absent, so code search is forced through the KG."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    project = tmp_path / "proj"
    project.mkdir()
    Configurator(project_root=project).configure(["claude-code"], scope="local")

    body = (project / ".claude" / "agents" / "oc-reviewer.md").read_text(encoding="utf-8")
    frontmatter = body.split("---", 2)[1]
    assert "tools:" in frontmatter
    assert "opencontext_" in frontmatter
    assert "Grep:" not in frontmatter
    assert "Glob:" not in frontmatter
