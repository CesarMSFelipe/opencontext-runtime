"""Tests for the realistic OpenContext-free control (SIN runner).

A real agent WITHOUT OpenContext, asked to modify symbol X, greps the tree for X,
sees who references it, greps those, then Reads every hit file in full. The SIN
runner models exactly that:

* ``tokens``     = Σ estimate_tokens(full text of each grep-hit file)
* ``tool_calls`` = grep_passes + reads (counted directly, not derived)
* ``latency_ms`` = wall-clock of the loop

CRUCIALLY it must resolve files by PLAIN REGEX over the working tree — never via
OpenContext's KnowledgeGraph/index. Using the system-under-test to power the control
would understate the control's cost and overstate OpenContext's win. An import-guard
test asserts the module cannot reach the KG.
"""

from __future__ import annotations

import ast
from pathlib import Path

from opencontext_core.context.budgeting import estimate_tokens
from opencontext_core.evaluation.models import ContextBenchCase, CostTriple
from opencontext_core.evaluation.naive_agent import (
    CALLER_GREP_CAP,
    run_naive_case,
)

NAIVE_AGENT_SRC = (
    Path(__file__).parent.parent.parent
    / "packages"
    / "opencontext_core"
    / "opencontext_core"
    / "evaluation"
    / "naive_agent.py"
)


def _write(root: Path, rel: str, body: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


class TestSinHonestCost:
    def test_tokens_equal_sum_of_hit_file_tokens(self, tmp_path: Path) -> None:
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
        _write(tmp_path, "pkg/unrelated.py", "def nothing() -> int:\n    return 0\n")

        case = ContextBenchCase(
            id="widget-case",
            query="Modify the Widget class",
            target_symbol="Widget",
        )
        result = run_naive_case(case, tmp_path)

        assert isinstance(result, CostTriple)
        expected_tokens = estimate_tokens(target.read_text()) + estimate_tokens(caller.read_text())
        assert result.tokens == expected_tokens
        # widget.py and usage.py both mention "Widget"; unrelated.py does not.
        assert result.tokens > 0

    def test_tool_calls_equal_grep_passes_plus_reads(self, tmp_path: Path) -> None:
        _write(tmp_path, "pkg/widget.py", "class Widget:\n    pass\n")
        _write(
            tmp_path,
            "pkg/usage.py",
            "from pkg.widget import Widget\n\n\n"
            "def build_thing() -> Widget:\n    return Widget()\n",
        )
        case = ContextBenchCase(
            id="widget-case",
            query="Modify Widget",
            target_symbol="Widget",
        )
        result = run_naive_case(case, tmp_path)
        # Headline control is bounded (caller-grep off by default): exactly
        # 1 primary grep pass + 2 reads (widget.py, usage.py) == 3.
        assert result.tool_calls == 3
        assert result.latency_ms >= 0.0

    def test_default_is_bounded_to_primary_hits(self, tmp_path: Path) -> None:
        """Default (CALLER_GREP_CAP == 0): SIN reads only files mentioning the target."""
        assert CALLER_GREP_CAP == 0
        _write(tmp_path, "core.py", "def target_fn() -> int:\n    return 1\n")
        # A file that calls target_fn DOES mention it (so it is a primary hit).
        _write(tmp_path, "caller.py", "def use() -> int:\n    return target_fn()\n")
        # A file that does NOT mention target_fn must NOT be read.
        _write(tmp_path, "noise.py", "def unrelated() -> int:\n    return 0\n")
        case = ContextBenchCase(id="b", query="change target_fn", target_symbol="target_fn")
        result = run_naive_case(case, tmp_path)
        # 1 grep + 2 reads (core.py, caller.py); noise.py is never opened.
        assert result.tool_calls == 3

    def test_caller_grep_cap_override_is_bounded(self, tmp_path: Path) -> None:
        """The optional caller-grep mechanism is bounded by the explicit cap."""
        _write(tmp_path, "core.py", "def target_fn() -> int:\n    return 1\n")
        for i in range(20):
            _write(
                tmp_path,
                f"caller_{i}.py",
                f"def caller_name_{i}() -> int:\n    return target_fn()\n",
            )
        case = ContextBenchCase(id="popular", query="change target_fn", target_symbol="target_fn")
        capped = run_naive_case(case, tmp_path, caller_grep_cap=3)
        uncapped_default = run_naive_case(case, tmp_path)  # cap 0
        # The override runs more grep passes than the bounded default, but stays finite.
        assert capped.tool_calls >= uncapped_default.tool_calls
        assert capped.tool_calls > 0

    def test_deterministic_across_runs(self, tmp_path: Path) -> None:
        _write(tmp_path, "a.py", "def shared_sym() -> int:\n    return 1\n")
        _write(tmp_path, "b.py", "def other() -> int:\n    return shared_sym()\n")
        case = ContextBenchCase(id="d", query="x", target_symbol="shared_sym")
        first = run_naive_case(case, tmp_path)
        second = run_naive_case(case, tmp_path)
        assert first.tokens == second.tokens
        assert first.tool_calls == second.tool_calls

    def test_target_symbol_derived_when_absent(self, tmp_path: Path) -> None:
        _write(tmp_path, "mod.py", "def prepare_context() -> None:\n    pass\n")
        case = ContextBenchCase(
            id="derive",
            query="How does prepare_context build the pack?",
        )
        result = run_naive_case(case, tmp_path)
        # Derives a target from the query and still produces a cost.
        assert isinstance(result, CostTriple)
        assert result.tool_calls >= 1


class TestSinImportGuard:
    """R1: the SIN must NOT use OpenContext's KnowledgeGraph/index to resolve files."""

    def test_imports_no_kg_or_runtime(self) -> None:
        tree = ast.parse(NAIVE_AGENT_SRC.read_text(encoding="utf-8"))
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
                    f"SIN runner must not import {frag!r} (found via {name!r}); "
                    "the control may not use the system under test."
                )
