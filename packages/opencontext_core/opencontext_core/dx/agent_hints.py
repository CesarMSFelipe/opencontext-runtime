"""Agent hints system for project-specific instructions.

Provides a way to define project-specific instructions, conventions,
and context that helps AI agents understand the codebase better.

Supports multiple formats:
- .opencontexthints - Primary hints file
- AGENTS.md - Generic agent instructions
- .cursor/rules/ - Cursor-specific rules
- .windsurf/rules/ - Windsurf-specific rules
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar


@dataclass
class AgentHint:
    """A single hint or instruction for an AI agent."""

    category: str
    content: str
    priority: int = 0  # Higher = more important
    tags: list[str] = field(default_factory=list)


@dataclass
class AgentHintsFile:
    """Parsed hints file content."""

    source: str
    project_name: str | None
    description: str | None
    conventions: list[AgentHint]
    architecture: list[AgentHint]
    workflows: list[AgentHint]
    patterns: list[AgentHint]
    warnings: list[AgentHint]


class AgentHintsManager:
    """Manages agent hints for a project.

    Discovers, parses, and provides hints in a unified format
    regardless of the source file format.
    """

    HINTS_FILES: ClassVar[list[str]] = [
        ".opencontexthints",
        "AGENTS.md",
        "CLAUDE.md",
        ".cursor/rules/opencontext.mdc",
        ".windsurf/rules/opencontext.md",
    ]

    def __init__(self, project_path: str | Path = ".") -> None:
        self.project_path = Path(project_path)

    def discover_hints(self) -> list[Path]:
        """Discover all hints files in the project."""
        found: list[Path] = []
        for filename in self.HINTS_FILES:
            path = self.project_path / filename
            if path.exists():
                found.append(path)
        return found

    def parse_hints_file(self, path: Path) -> AgentHintsFile | None:
        """Parse a hints file into structured hints."""
        try:
            content = path.read_text()
        except Exception:
            return None

        # Determine format based on filename
        filename = path.name

        if filename == ".opencontexthints":
            return self._parse_opencontexthints(content, str(path))
        elif filename == "AGENTS.md" or filename == "CLAUDE.md":
            return self._parse_agents_md(content, str(path))
        elif filename.endswith(".mdc") or filename.endswith(".md"):
            return self._parse_rules_md(content, str(path))

        return None

    def _parse_opencontexthints(self, content: str, source: str) -> AgentHintsFile:
        """Parse .opencontexthints format.

        Format:
        project: My Project
        description: A brief description

        [conventions]
        - Use type hints everywhere
        - Prefer dataclasses over dicts

        [architecture]
        - Core is in packages/opencontext_core/
        - CLI is in packages/opencontext_cli/

        [workflows]
        - Run tests with pytest
        - Format with ruff

        [patterns]
        - Repository pattern for data access
        - Strategy pattern for providers

        [warnings]
        - Never commit secrets
        - Don't use global state
        """
        lines = content.strip().split("\n")

        project_name = None
        description = None
        current_section = None
        sections: dict[str, list[AgentHint]] = {
            "conventions": [],
            "architecture": [],
            "workflows": [],
            "patterns": [],
            "warnings": [],
        }

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            if line.startswith("project:"):
                project_name = line.split(":", 1)[1].strip()
            elif line.startswith("description:"):
                description = line.split(":", 1)[1].strip()
            elif line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1].lower()
            elif line.startswith("-") and current_section in sections:
                hint_content = line[1:].strip()
                if hint_content:
                    sections[current_section].append(
                        AgentHint(
                            category=current_section,
                            content=hint_content,
                            priority=len(sections[current_section]),
                        )
                    )

            i += 1

        return AgentHintsFile(
            source=source,
            project_name=project_name,
            description=description,
            conventions=sections["conventions"],
            architecture=sections["architecture"],
            workflows=sections["workflows"],
            patterns=sections["patterns"],
            warnings=sections["warnings"],
        )

    def _parse_agents_md(self, content: str, source: str) -> AgentHintsFile:
        """Parse AGENTS.md or CLAUDE.md format."""
        lines = content.strip().split("\n")

        project_name = None
        description = None
        current_section = None
        sections: dict[str, list[AgentHint]] = {
            "conventions": [],
            "architecture": [],
            "workflows": [],
            "patterns": [],
            "warnings": [],
        }

        for line in lines:
            stripped = line.strip()

            # Try to extract project name from first heading
            if stripped.startswith("# ") and not project_name:
                project_name = stripped[2:].strip()

            # Section headers
            if stripped.startswith("## "):
                section_name = stripped[3:].strip().lower()
                if "convention" in section_name:
                    current_section = "conventions"
                elif "arch" in section_name:
                    current_section = "architecture"
                elif "workflow" in section_name or "process" in section_name:
                    current_section = "workflows"
                elif "pattern" in section_name:
                    current_section = "patterns"
                elif "warning" in section_name or "caution" in section_name:
                    current_section = "warnings"
                else:
                    current_section = None
            elif stripped.startswith("-") or stripped.startswith("*"):
                if current_section and current_section in sections:
                    hint_content = stripped[1:].strip()
                    if hint_content:
                        sections[current_section].append(
                            AgentHint(
                                category=current_section,
                                content=hint_content,
                                priority=len(sections[current_section]),
                            )
                        )

        return AgentHintsFile(
            source=source,
            project_name=project_name,
            description=description,
            conventions=sections["conventions"],
            architecture=sections["architecture"],
            workflows=sections["workflows"],
            patterns=sections["patterns"],
            warnings=sections["warnings"],
        )

    def _parse_rules_md(self, content: str, source: str) -> AgentHintsFile:
        """Parse Cursor/Windsurf rules format."""
        # Rules files are usually simpler - just a list of instructions
        lines = content.strip().split("\n")

        conventions: list[AgentHint] = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                conventions.append(
                    AgentHint(
                        category="conventions",
                        content=stripped,
                        priority=len(conventions),
                    )
                )

        return AgentHintsFile(
            source=source,
            project_name=None,
            description=None,
            conventions=conventions,
            architecture=[],
            workflows=[],
            patterns=[],
            warnings=[],
        )

    def get_all_hints(self) -> AgentHintsFile | None:
        """Get combined hints from all discovered files.

        Returns a single AgentHintsFile with merged content from all sources.
        """
        files = self.discover_hints()
        if not files:
            return None

        combined = AgentHintsFile(
            source="combined",
            project_name=None,
            description=None,
            conventions=[],
            architecture=[],
            workflows=[],
            patterns=[],
            warnings=[],
        )

        for file_path in files:
            parsed = self.parse_hints_file(file_path)
            if parsed:
                if parsed.project_name and not combined.project_name:
                    combined.project_name = parsed.project_name
                if parsed.description and not combined.description:
                    combined.description = parsed.description

                combined.conventions.extend(parsed.conventions)
                combined.architecture.extend(parsed.architecture)
                combined.workflows.extend(parsed.workflows)
                combined.patterns.extend(parsed.patterns)
                combined.warnings.extend(parsed.warnings)

        return combined

    def generate_hints_template(self, project_name: str) -> str:
        """Generate a template .opencontexthints file."""
        return f"""project: {project_name}
description: Project-specific instructions for AI agents

[conventions]
- Use type hints for all function signatures
- Write docstrings for public APIs
- Prefer immutable data structures
- Keep functions under 50 lines

[architecture]
- Core business logic is in the domain layer
- Infrastructure concerns are in adapters
- Use dependency injection for testability

[workflows]
- Run the full test suite before committing
- Use conventional commits for changelog generation
- Update documentation when changing public APIs

[patterns]
- Repository pattern for data access
- Strategy pattern for interchangeable algorithms
- Factory pattern for complex object creation

[warnings]
- Never commit secrets or API keys
- Don't use global mutable state
- Avoid circular dependencies between modules
"""

    def init_hints_file(self) -> Path | None:
        """Initialize a .opencontexthints file in the project."""
        hints_path = self.project_path / ".opencontexthints"
        if hints_path.exists():
            return None

        # Try to get project name from git or directory
        project_name = self.project_path.name

        template = self.generate_hints_template(project_name)
        hints_path.write_text(template)
        return hints_path

    def to_context_string(self, hints: AgentHintsFile | None) -> str:
        """Convert hints to a context string suitable for prompts."""
        if not hints:
            return ""

        sections: list[str] = []

        if hints.project_name:
            sections.append(f"Project: {hints.project_name}")
        if hints.description:
            sections.append(f"Description: {hints.description}")

        if hints.conventions:
            sections.append("\nConventions:")
            for hint in hints.conventions:
                sections.append(f"  - {hint.content}")

        if hints.architecture:
            sections.append("\nArchitecture:")
            for hint in hints.architecture:
                sections.append(f"  - {hint.content}")

        if hints.workflows:
            sections.append("\nWorkflows:")
            for hint in hints.workflows:
                sections.append(f"  - {hint.content}")

        if hints.patterns:
            sections.append("\nPatterns:")
            for hint in hints.patterns:
                sections.append(f"  - {hint.content}")

        if hints.warnings:
            sections.append("\nWarnings:")
            for hint in hints.warnings:
                sections.append(f"  - {hint.content}")

        return "\n".join(sections)
