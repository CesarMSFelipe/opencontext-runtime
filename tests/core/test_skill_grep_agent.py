"""Tests for the SKILL-GREP arm (a prose-skill + grep "load the skill, then grep" loop).

* tokens == SKILL_FILE_TOKENS (the standing prompt) + Σ estimate_tokens(full hit file).
* It must resolve files by PLAIN REGEX over the working tree — an import-guard asserts
  it never reaches OpenContext's indexing/runtime/knowledge-graph.
"""

from __future__ import annotations

import ast
from pathlib import Path

from opencontext_core.context.budgeting import estimate_tokens
from opencontext_core.evaluation.models import ContextBenchCase
from opencontext_core.evaluation.multi_arm import ArmResult
from opencontext_core.evaluation.skill_grep_agent import (
    SKILL_FILE_TOKENS,
    run_skill_grep_case,
)

SKILL_GREP_AGENT_SRC = (
    Path(__file__).parent.parent.parent
    / "packages"
    / "opencontext_core"
    / "opencontext_core"
    / "evaluation"
    / "skill_grep_agent.py"
)


def _write(root: Path, rel: str, body: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


class TestSkillGrepHonestCost:
    def test_tokens_equal_skill_plus_hit_file_estimates(self, tmp_path: Path) -> None:
        target = _write(
            tmp_path,
            "pkg/widget.py",
            "class Widget:\n    def render(self) -> str:\n        return 'w'\n",
        )
        caller = _write(
            tmp_path,
            "pkg/usage.py",
            "from pkg.widget import Widget\n\n\ndef use() -> str:\n    return Widget().render()\n",
        )
        # A third file that never mentions Widget must NOT contribute tokens.
        _write(tmp_path, "pkg/unrelated.py", "def nothing() -> int:\n    return 0\n")

        case = ContextBenchCase(
            id="widget-case",
            query="Modify the Widget class",
            target_symbol="Widget",
        )
        result = run_skill_grep_case(case, tmp_path)

        assert isinstance(result, ArmResult)
        assert result.arm == "SKILL-GREP"
        expected = (
            SKILL_FILE_TOKENS
            + estimate_tokens(target.read_text())
            + estimate_tokens(caller.read_text())
        )
        assert result.tokens == expected
        # 1 grep pass + 2 reads (widget.py, usage.py); unrelated.py is not read.
        assert result.tool_calls == 3
        assert result.latency_ms >= 0.0

    def test_standing_prompt_cost_paid_even_with_no_hits(self, tmp_path: Path) -> None:
        _write(tmp_path, "pkg/other.py", "def other() -> int:\n    return 0\n")
        case = ContextBenchCase(
            id="missing",
            query="change MissingSymbol",
            target_symbol="MissingSymbol",
        )
        result = run_skill_grep_case(case, tmp_path)
        # No hit files, but the loaded skill is still paid for; only the grep pass runs.
        assert result.tokens == SKILL_FILE_TOKENS
        assert result.tool_calls == 1

    def test_top_k_caps_the_hit_files(self, tmp_path: Path) -> None:
        for i in range(10):
            _write(tmp_path, f"m{i}.py", f"def helper_{i}() -> int:\n    return shared_sym()\n")
        _write(tmp_path, "core.py", "def shared_sym() -> int:\n    return 1\n")
        case = ContextBenchCase(id="popular", query="x", target_symbol="shared_sym")
        result = run_skill_grep_case(case, tmp_path, top_k=3)
        # At most top_k reads regardless of how many files mention the symbol.
        assert result.tool_calls == 1 + 3

    def test_skill_file_tokens_is_positive(self) -> None:
        assert SKILL_FILE_TOKENS > 0


class TestSkillGrepImportGuard:
    """The SKILL-GREP control must NOT use OpenContext's KG/index to resolve files."""

    def test_imports_no_kg_or_runtime(self) -> None:
        tree = ast.parse(SKILL_GREP_AGENT_SRC.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imported.add(module)
                for alias in node.names:
                    imported.add(f"{module}.{alias.name}")

        forbidden_fragments = (
            "opencontext_core.indexing",
            "opencontext_core.runtime",
            "knowledge_graph",
            "KnowledgeGraph",
            "OpenContextRuntime",
        )
        for name in imported:
            for frag in forbidden_fragments:
                assert frag not in name, (
                    f"SKILL-GREP control must not import {frag!r} (found via {name!r}); "
                    "the control may not use the system under test."
                )

    def test_no_subprocess(self) -> None:
        tree = ast.parse(SKILL_GREP_AGENT_SRC.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
        assert "subprocess" not in imported
