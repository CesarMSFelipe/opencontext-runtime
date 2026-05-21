"""Tests for agent hints system."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.dx.agent_hints import AgentHintsFile, AgentHintsManager


class TestAgentHintsManager:
    """Test agent hints manager."""

    @pytest.fixture
    def manager(self, tmp_path: Path) -> AgentHintsManager:
        return AgentHintsManager(tmp_path)

    def test_discover_hints_empty(self, manager: AgentHintsManager) -> None:
        assert manager.discover_hints() == []

    def test_discover_hints(self, manager: AgentHintsManager, tmp_path: Path) -> None:
        (tmp_path / ".opencontexthints").write_text("project: Test\n")
        (tmp_path / "AGENTS.md").write_text("# Test Project\n")

        hints = manager.discover_hints()
        assert len(hints) == 2

    def test_parse_opencontexthints(self, manager: AgentHintsManager, tmp_path: Path) -> None:
        content = """project: My Project
description: A test project

[conventions]
- Use type hints
- Write tests

[architecture]
- Core in src/

[warnings]
- Never commit secrets
"""
        (tmp_path / ".opencontexthints").write_text(content)

        parsed = manager.parse_hints_file(tmp_path / ".opencontexthints")
        assert parsed is not None
        assert parsed.project_name == "My Project"
        assert parsed.description == "A test project"
        assert len(parsed.conventions) == 2
        assert parsed.conventions[0].content == "Use type hints"
        assert len(parsed.architecture) == 1
        assert len(parsed.warnings) == 1

    def test_parse_agents_md(self, manager: AgentHintsManager, tmp_path: Path) -> None:
        content = """# Test Project

## Conventions
- Use type hints
- Write docstrings

## Architecture
- Core in src/
- Adapters in adapters/

## Warnings
- Don't use globals
"""
        (tmp_path / "AGENTS.md").write_text(content)

        parsed = manager.parse_hints_file(tmp_path / "AGENTS.md")
        assert parsed is not None
        assert parsed.project_name == "Test Project"
        assert len(parsed.conventions) == 2
        assert len(parsed.architecture) == 2
        assert len(parsed.warnings) == 1

    def test_get_all_hints(self, manager: AgentHintsManager, tmp_path: Path) -> None:
        (tmp_path / ".opencontexthints").write_text("""project: My Project

[conventions]
- Use type hints
""")
        (tmp_path / "AGENTS.md").write_text("""# Test

## Conventions
- Write tests
""")

        combined = manager.get_all_hints()
        assert combined is not None
        assert combined.project_name == "My Project"
        assert len(combined.conventions) == 2

    def test_init_hints_file(self, manager: AgentHintsManager, tmp_path: Path) -> None:
        path = manager.init_hints_file()
        assert path is not None
        assert path.exists()
        content = path.read_text()
        assert "project:" in content
        assert "[conventions]" in content
        assert "[warnings]" in content

    def test_init_hints_file_exists(self, manager: AgentHintsManager, tmp_path: Path) -> None:
        (tmp_path / ".opencontexthints").write_text("existing")
        path = manager.init_hints_file()
        assert path is None

    def test_to_context_string(self, manager: AgentHintsManager) -> None:
        hints = AgentHintsFile(
            source="test",
            project_name="Test Project",
            description="A test",
            conventions=[],
            architecture=[],
            workflows=[],
            patterns=[],
            warnings=[],
        )
        ctx = manager.to_context_string(hints)
        assert "Project: Test Project" in ctx
        assert "Description: A test" in ctx

    def test_generate_hints_template(self, manager: AgentHintsManager) -> None:
        template = manager.generate_hints_template("My Project")
        assert "project: My Project" in template
        assert "[conventions]" in template
        assert "[architecture]" in template
        assert "[workflows]" in template
        assert "[patterns]" in template
        assert "[warnings]" in template
