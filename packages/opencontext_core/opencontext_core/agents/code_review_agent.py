"""Code review agent — graph analysis local, summary generation via host LLM."""

from __future__ import annotations

from typing import Any

from opencontext_core.agents.base import BaseAgent


# DEPRECATED(2.0): dead agent SDK spine (no live caller;
# superseded by opencontext_core.harness). Remove in 2.0.
class CodeReviewAgent(BaseAgent):
    """
    (local): extract changed symbols, callers, test coverage from graph.
    (prompt): emit structured prompt for host LLM to generate review.
    If provider configured → call directly. Else → return prompt for host.
    """

    async def execute(self) -> dict[str, Any]:
        scope = self.config.scope or {}
        changed_files = scope.get("changed_files", [])

        # local graph analysis
        graph_context = self._analyze_locally(changed_files)

        # generate review prompt (host executes)
        prompt = self._build_review_prompt(graph_context, changed_files)

        return {
            "graph_context": graph_context,
            "review_prompt": prompt,
            "changed_files": changed_files,
            "execution_mode": "prompt",  # host should execute this prompt
        }

    def _analyze_locally(self, changed_files: list[str]) -> dict[str, Any]:
        """Extract graph signals without LLM."""
        return {
            "changed_files": changed_files,
            "symbols_affected": [],  # would use knowledge graph
            "callers_affected": [],
            "test_coverage": "unknown",
        }

    def _build_review_prompt(self, context: dict[str, Any], files: list[str]) -> str:
        from opencontext_core.backends.compression.efficient import EfficientCompressionBackend

        compressor = EfficientCompressionBackend()
        ctx_str = compressor.compress(str(context), [])
        files_str = "\n".join(f"- {f}" for f in files)
        return (
            f"Review the following changes.\n"
            f"Changed files:\n{files_str}\n\n"
            f"Graph context: {ctx_str}\n\n"
            f"Report: critical issues, test gaps, security concerns. Be concise."
        )
