"""Session summary generator for structured session close reports."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SessionSummary:
    """Structured session summary."""

    goal: str = ""
    instructions: list[str] = field(default_factory=list)
    discoveries: list[str] = field(default_factory=list)
    accomplished: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    relevant_files: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Render as markdown."""

        lines = ["## Goal", self.goal or "(not specified)", ""]

        if self.instructions:
            lines.extend(["## Instructions"] + [f"- {i}" for i in self.instructions] + [""])

        if self.discoveries:
            lines.extend(["## Discoveries"] + [f"- {d}" for d in self.discoveries] + [""])

        if self.accomplished:
            lines.extend(["## Accomplished"] + [f"- {a}" for a in self.accomplished] + [""])

        if self.next_steps:
            lines.extend(["## Next Steps"] + [f"- {n}" for n in self.next_steps] + [""])

        if self.relevant_files:
            lines.extend(
                ["## Relevant Files"] + [f"- {f}" for f in self.relevant_files] + [""]
            )

        return "\n".join(lines)

    @classmethod
    def from_dict(cls, data: dict[str, list[str] | str]) -> SessionSummary:
        """Create from a dictionary."""

        return cls(
            goal=str(data.get("goal", "")),
            instructions=list(data.get("instructions", [])),
            discoveries=list(data.get("discoveries", [])),
            accomplished=list(data.get("accomplished", [])),
            next_steps=list(data.get("next_steps", [])),
            relevant_files=list(data.get("relevant_files", [])),
        )

    def to_dict(self) -> dict[str, list[str] | str]:
        """Convert to dictionary."""

        return {
            "goal": self.goal,
            "instructions": self.instructions,
            "discoveries": self.discoveries,
            "accomplished": self.accomplished,
            "next_steps": self.next_steps,
            "relevant_files": self.relevant_files,
        }
