"""AiderAdapter — wraps the aider CLI for AI pair-programmed changes.

Aider is an external AI coding tool. This adapter invokes it via subprocess
with configured instructions. Aider must be installed separately
(pip install aider-chat).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from opencontext_core.adapters.base import AgentAdapter, AgentResult


class AiderAdapter(AgentAdapter):
    """Adapter for the aider AI pair-programming CLI tool.

    Requires: `pip install aider-chat`
    Works with: OpenAI, Anthropic, Gemini, local models via Ollama, etc.

    The adapter invokes aider with:
    - `--message` for one-shot task execution
    - `--auto-commits` disabled (the orchestrator manages commits)
    - Provider-neutral: model selection is left to aider's config
    """

    name = "aider"

    def __init__(
        self,
        model: str | None = None,
        architect: bool = False,
        dark_mode: bool = True,
        auto_commits: bool = False,
        suggest_shell_commands: bool = False,
        lint: bool = True,
        test: bool = True,
    ) -> None:
        self.model = model
        self.architect = architect
        self.dark_mode = dark_mode
        self.auto_commits = auto_commits
        self.suggest_shell_commands = suggest_shell_commands
        self.lint = lint
        self.test = test

    def check_available(self) -> bool:
        """Check if aider CLI is available on PATH."""
        return shutil.which("aider") is not None

    def execute(
        self,
        instruction: str,
        cwd: Path | None = None,
        timeout: int = 600,
        env: dict[str, str] | None = None,
    ) -> AgentResult:
        """Execute a task instruction through aider.

        Constructs an aider CLI invocation with the given instruction
        as the --message argument.

        Args:
            instruction: The task description for aider.
            cwd: Working directory (project root).
            timeout: Maximum execution time (default 10 min for LLM calls).
            env: Optional environment overrides (e.g., API keys).

        Returns:
            AgentResult with aider's output.
        """
        if not self.check_available():
            return AgentResult(
                success=False,
                exit_code=-1,
                stderr=(
                    "aider is not installed. Install it with: pip install aider-chat\n"
                    "Then configure your API key via environment variables "
                    "(e.g., ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.)."
                ),
            )

        args = self._build_args(instruction)
        merged_env = {**os.environ, **(env or {})}

        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                cwd=str(cwd) if cwd else None,
                timeout=timeout,
                env=merged_env,
            )
            return AgentResult(
                success=result.returncode == 0,
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                output=(result.stdout or "") + (result.stderr or ""),
                metadata={
                    "model": self.model,
                    "architect": self.architect,
                    "instruction": instruction[:200],
                },
            )
        except FileNotFoundError:
            return AgentResult(
                success=False,
                exit_code=-2,
                stderr="aider executable not found despite previous check_available().",
            )
        except subprocess.TimeoutExpired:
            return AgentResult(
                success=False,
                exit_code=-3,
                stderr=f"aider timed out after {timeout}s.",
            )
        except OSError as exc:
            return AgentResult(
                success=False,
                exit_code=-4,
                stderr=f"OS error running aider: {exc}",
            )

    def _build_args(self, instruction: str) -> list[str]:
        """Build aider CLI argument list."""
        args = ["aider", "--message", instruction]

        if self.model:
            args.extend(["--model", self.model])
        if self.architect:
            args.append("--architect")
        if self.dark_mode:
            args.append("--dark-mode")
        if not self.auto_commits:
            args.append("--no-auto-commits")
        if not self.suggest_shell_commands:
            args.append("--no-suggest-shell-commands")
        if self.lint:
            args.append("--lint")
        if self.test:
            args.append("--test")

        # Provider-neutral defaults
        args.extend(
            [
                "--yes",  # Non-interactive
                "--no-stream",  # Capture full output
            ]
        )
        return args
