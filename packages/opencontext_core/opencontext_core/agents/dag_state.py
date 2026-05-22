"""DAG state management for SDD phase tracking and recovery."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from opencontext_core.compat import UTC


@dataclass
class DAGState:
    """State of an SDD workflow DAG."""

    change: str
    phase: str = "idle"
    artifacts: dict[str, bool] = field(default_factory=dict)
    completed_phases: list[str] = field(default_factory=list)
    tasks_progress: dict[str, Any] = field(default_factory=dict)
    last_updated: datetime = field(default_factory=lambda: datetime.now(tz=UTC))

    def mark_completed(self, phase: str) -> None:
        """Mark a phase as completed."""

        if phase not in self.completed_phases:
            self.completed_phases.append(phase)
        self.phase = phase
        self.last_updated = datetime.now(tz=UTC)

    def mark_artifact_saved(self, artifact_type: str) -> None:
        """Mark an artifact as saved."""

        self.artifacts[artifact_type] = True
        self.last_updated = datetime.now(tz=UTC)

    def is_phase_completed(self, phase: str) -> bool:
        """Check if a phase is completed."""

        return phase in self.completed_phases

    def is_artifact_saved(self, artifact_type: str) -> bool:
        """Check if an artifact is saved."""

        return self.artifacts.get(artifact_type, False)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""

        return {
            "change": self.change,
            "phase": self.phase,
            "artifacts": dict(self.artifacts),
            "completed_phases": list(self.completed_phases),
            "tasks_progress": dict(self.tasks_progress),
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DAGState:
        """Deserialize from dictionary."""

        return cls(
            change=str(data.get("change", "")),
            phase=str(data.get("phase", "idle")),
            artifacts=dict(data.get("artifacts", {})),
            completed_phases=list(data.get("completed_phases", [])),
            tasks_progress=dict(data.get("tasks_progress", {})),
            last_updated=datetime.fromisoformat(
                str(data.get("last_updated", datetime.now(tz=UTC).isoformat()))
            ),
        )

    def save(self) -> str:
        """Serialize to YAML-like string for persistence."""

        lines = [
            f"change: {self.change}",
            f"phase: {self.phase}",
            f"last_updated: {self.last_updated.isoformat()}",
            "artifacts:",
        ]
        for artifact, saved in self.artifacts.items():
            lines.append(f"  {artifact}: {saved}")
        lines.append("completed_phases:")
        for phase in self.completed_phases:
            lines.append(f"  - {phase}")

        return "\n".join(lines)

    @classmethod
    def recover(cls, content: str) -> DAGState | None:
        """Recover state from a persisted string."""

        data: dict[str, Any] = {"artifacts": {}, "completed_phases": []}
        current_key: str | None = None

        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            if stripped.startswith("- "):
                if current_key == "completed_phases":
                    data["completed_phases"].append(stripped[2:].strip())
                continue

            if ":" in stripped:
                key, value = stripped.split(":", 1)
                key = key.strip()
                value = value.strip()

                if key == "artifacts":
                    current_key = "artifacts"
                    continue
                elif key == "completed_phases":
                    current_key = "completed_phases"
                    continue

                if current_key == "artifacts":
                    data["artifacts"][key] = value.lower() == "true"
                else:
                    data[key] = value

        if not data.get("change"):
            return None

        return cls.from_dict(data)
