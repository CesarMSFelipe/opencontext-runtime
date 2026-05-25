"""AgentAdapter base — abstract interface for AI coding tool adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AgentResult:
    """Result from executing a task through an agent adapter."""

    success: bool
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    output: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentAdapter(ABC):
    """Abstract base for AI coding tool adapters.

    Each adapter wraps a specific agent (aider, local, etc.) and provides
    a uniform interface for the harness runner to execute tasks.
    """

    name: str = ""

    @abstractmethod
    def check_available(self) -> bool:
        """Return True if this agent is available on the system."""
        ...

    @abstractmethod
    def execute(
        self,
        instruction: str,
        cwd: Path | None = None,
        timeout: int = 300,
        env: dict[str, str] | None = None,
    ) -> AgentResult:
        """Execute a task instruction through the agent.

        Args:
            instruction: Task description or instruction for the agent.
            cwd: Working directory for execution.
            timeout: Maximum execution time in seconds.
            env: Optional environment overrides.

        Returns:
            AgentResult with execution outcome.
        """
        ...

    def run_workflow(
        self,
        workflow: str,
        task: str,
        root: Path,
        timeout: int = 600,
    ) -> AgentResult:
        """Run a full SDD workflow through the agent.

        Default implementation calls execute() with a formatted workflow instruction.
        Override for agent-specific workflow handling.
        """
        instruction = (
            f"Run the {workflow} workflow for: {task}\n\n"
            f"Follow SDD phases: explore -> propose -> apply -> verify -> review -> archive.\n"
            f"Use the project at {root}.\n"
            f"Do NOT commit or push changes."
        )
        return self.execute(instruction, cwd=root, timeout=timeout)
