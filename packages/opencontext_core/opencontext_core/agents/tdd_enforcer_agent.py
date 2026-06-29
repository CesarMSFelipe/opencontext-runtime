"""TDD enforcer agent — verifies red→green→refactor cycle."""

from __future__ import annotations

import subprocess
from typing import Any

from opencontext_core.agents.base import BaseAgent


# DEPRECATED(2.0): dead agent SDK spine (no live caller;
# superseded by opencontext_core.harness). Remove in 2.0.
class TDDEnforcerAgent(BaseAgent):
    """Runs test suite and reports TDD cycle status. Pure local."""

    async def execute(self) -> dict[str, Any]:
        scope = self.config.scope or {}
        test_cmd = scope.get("test_command", "python3 -m pytest")
        test_path = scope.get("test_path", "tests/")

        result = subprocess.run(
            f"{test_cmd} {test_path} --tb=short -q".split(),
            capture_output=True,
            text=True,
            cwd=self.project_root,
            timeout=120,
        )
        passed = result.returncode == 0
        # Parse counts from pytest output
        import re

        m = re.search(r"(\d+) passed", result.stdout)
        f = re.search(r"(\d+) failed", result.stdout)
        return {
            "passed": passed,
            "test_count": int(m.group(1)) if m else 0,
            "failure_count": int(f.group(1)) if f else 0,
            "output": result.stdout[-2000:],
            "cycle_status": "green" if passed else "red",
        }
