"""Tests for the REALISTIC-SIN arm (window-reading OpenContext-free control).

It greps the symbol like the full SIN, but reads only a ~60-line window around each
hit. So on a large file with a single match its token cost is strictly LESS than the
full-file estimate. An import-guard asserts it never reaches the KG/index.
"""

from __future__ import annotations

import ast
from pathlib import Path

from opencontext_core.context.budgeting import estimate_tokens
from opencontext_core.evaluation.models import ContextBenchCase
from opencontext_core.evaluation.multi_arm import ArmResult
from opencontext_core.evaluation.realistic_agent import run_realistic_case

REALISTIC_AGENT_SRC = (
    Path(__file__).parent.parent.parent
    / "packages"
    / "opencontext_core"
    / "opencontext_core"
    / "evaluation"
    / "realistic_agent.py"
)


def _write(root: Path, rel: str, body: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


class TestRealisticPartialRead:
    def test_window_tokens_less_than_full_file(self, tmp_path: Path) -> None:
        # A 200-line file with the target on a single line in the middle.
        lines = [f"x_{i} = {i}" for i in range(200)]
        lines[100] = "def target_symbol() -> int:\n    return 1"
        body = "\n".join(lines) + "\n"
        big = _write(tmp_path, "big.py", body)

        case = ContextBenchCase(
            id="big", query="change target_symbol", target_symbol="target_symbol"
        )
        result = run_realistic_case(case, tmp_path)

        assert isinstance(result, ArmResult)
        assert result.arm == "REALISTIC-SIN"
        full_file_tokens = estimate_tokens(big.read_text())
        # The windowed read covers ~60 lines, far fewer than the 200-line file.
        assert 0 < result.tokens < full_file_tokens
        # 1 grep pass + 1 windowed read.
        assert result.tool_calls == 2
        assert result.latency_ms >= 0.0

    def test_no_hits_yields_zero_tokens(self, tmp_path: Path) -> None:
        _write(tmp_path, "a.py", "def something() -> int:\n    return 0\n")
        case = ContextBenchCase(id="m", query="change Absent", target_symbol="Absent")
        result = run_realistic_case(case, tmp_path)
        assert result.tokens == 0
        # Only the grep pass; nothing is read.
        assert result.tool_calls == 1

    def test_small_file_window_equals_full(self, tmp_path: Path) -> None:
        # A file shorter than the window: the window is the whole file.
        small = _write(tmp_path, "small.py", "def target_fn() -> int:\n    return 1\n")
        case = ContextBenchCase(id="s", query="x", target_symbol="target_fn")
        result = run_realistic_case(case, tmp_path)
        assert result.tokens == estimate_tokens(small.read_text())

    def test_deterministic_across_runs(self, tmp_path: Path) -> None:
        lines = [f"y_{i} = {i}" for i in range(120)]
        lines[60] = "def shared_sym() -> int:\n    return 1"
        _write(tmp_path, "d.py", "\n".join(lines) + "\n")
        case = ContextBenchCase(id="d", query="x", target_symbol="shared_sym")
        first = run_realistic_case(case, tmp_path)
        second = run_realistic_case(case, tmp_path)
        assert first.tokens == second.tokens
        assert first.tool_calls == second.tool_calls


class TestRealisticImportGuard:
    """The realistic control must NOT use OpenContext's KG/index to resolve files."""

    def test_imports_no_kg_or_runtime(self) -> None:
        tree = ast.parse(REALISTIC_AGENT_SRC.read_text(encoding="utf-8"))
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
                    f"Realistic control must not import {frag!r} (found via {name!r}); "
                    "the control may not use the system under test."
                )

    def test_no_subprocess(self) -> None:
        tree = ast.parse(REALISTIC_AGENT_SRC.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
        assert "subprocess" not in imported
