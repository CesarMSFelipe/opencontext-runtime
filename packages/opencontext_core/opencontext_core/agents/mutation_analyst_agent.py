"""Mutation analysis agent — wraps MutationRunner."""

from __future__ import annotations

from typing import Any

from opencontext_core.agents.base import BaseAgent
from opencontext_core.mutation.runner import MutationRunner


# DEPRECATED(2.0): dead agent SDK spine (no live caller;
# superseded by opencontext_core.harness). Remove in 2.0.
class MutationAnalystAgent(BaseAgent):
    """Runs mutation analysis and reports coverage. Pure local."""

    async def execute(self) -> dict[str, Any]:
        scope = self.config.scope or {}
        threshold = scope.get("threshold", 80)
        file_scope = scope.get("scope", "changed")
        result = MutationRunner().run(self.project_root, scope=file_scope, threshold=threshold)
        return {
            "available": result.available,
            "score": result.score,
            "killed": result.killed,
            "survivors": result.survivors,
            "status": result.status.value,
            "threshold_met": result.score >= threshold if result.available else None,
            "error": result.error,
        }
