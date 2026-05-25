"""LocalAdapter — executes tasks via local subprocess commands.

Provider-neutral: runs system commands directly with no API dependencies.
Suitable for local execution, testing, and CI environments.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path

from opencontext_core.adapters.base import AgentAdapter, AgentResult

_LOCAL_AVAILABLE_COMMANDS = ["pytest", "python", "git", "opencontext", "ruff"]


class LocalAdapter(AgentAdapter):
    """Execute tasks locally via subprocess with direct command execution.

    This adapter does NOT use any AI coding tool — it runs shell commands
    directly. Useful for:
    - Running tests (pytest, ruff, mypy)
    - Executing scripts (python, bash)
    - Version control (git)
    - OpenContext CLI commands
    """

    name = "local"

    def __init__(self, available_commands: list[str] | None = None) -> None:
        self.available_commands = available_commands or _LOCAL_AVAILABLE_COMMANDS

    def check_available(self) -> bool:
        """Check if at least one known command is available on PATH."""
        for cmd in self.available_commands:
            if self._command_exists(cmd):
                return True
        # Always at least python and pytest should be available in a dev env
        return True

    def execute(
        self,
        instruction: str,
        cwd: Path | None = None,
        timeout: int = 300,
        env: dict[str, str] | None = None,
    ) -> AgentResult:
        """Execute a shell instruction locally.

        The instruction is split into a command and arguments, then run
        as a subprocess. Provider-neutral — no API calls.
        """
        if not instruction.strip():
            return AgentResult(success=False, exit_code=-1, stderr="Empty instruction")

        try:
            parts = shlex.split(instruction)
        except ValueError as exc:
            return AgentResult(success=False, exit_code=-1, stderr=f"Invalid instruction: {exc}")

        cmd = parts[0]
        if not self._command_exists(cmd):
            return AgentResult(
                success=False,
                exit_code=-1,
                stderr=f"Command not found on PATH: {cmd}",
            )

        # Merge env overrides with current process environment to preserve PATH etc.
        import os as _os

        merged_env = {**_os.environ.copy(), "PYTHONUNBUFFERED": "1"}
        if env:
            merged_env.update(env)

        try:
            result = subprocess.run(
                parts,
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
                output=result.stdout + result.stderr,
                metadata={
                    "command": cmd,
                    "args": parts[1:],
                    "cwd": str(cwd) if cwd else None,
                },
            )
        except FileNotFoundError:
            return AgentResult(
                success=False,
                exit_code=-2,
                stderr=f"Executable not found: {parts[0]}",
            )
        except subprocess.TimeoutExpired:
            return AgentResult(
                success=False,
                exit_code=-3,
                stderr=f"Command timed out after {timeout}s: {instruction[:80]}",
            )
        except OSError as exc:
            return AgentResult(
                success=False,
                exit_code=-4,
                stderr=f"OS error executing {parts[0]}: {exc}",
            )

    @staticmethod
    def _command_exists(cmd: str) -> bool:
        """Check if a command is available on PATH."""

        return shutil.which(cmd) is not None


class PythonAdapter(LocalAdapter):
    """Execute Python scripts directly. Subclass of LocalAdapter."""

    name = "python"

    def __init__(self) -> None:
        super().__init__(available_commands=["python", "python3", "pytest"])

    def execute(
        self,
        instruction: str,
        cwd: Path | None = None,
        timeout: int = 300,
        env: dict[str, str] | None = None,
    ) -> AgentResult:
        """Execute a Python module or script."""
        if instruction.startswith("pytest ") or instruction == "pytest":
            return super().execute(instruction, cwd=cwd, timeout=timeout, env=env)

        # Prepend python3 -c for inline code, or python3 for module execution
        if "\n" in instruction and not instruction.startswith("python"):
            instruction = f'{sys.executable} -c "{instruction}"'

        return super().execute(instruction, cwd=cwd, timeout=timeout, env=env)
