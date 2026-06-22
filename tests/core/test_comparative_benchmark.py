"""Tests for the curated ground-truth scenarios (post-excision).

The fake ``ComparativeBenchmark`` (which scored OpenContext as a curated answer key
and never ran OpenContext) was EXCISED. What remains is :data:`BUILTIN_SCENARIOS`,
the ground-truth tasks that seed the real efficiency benchmark. These tests assert
(a) the ground-truth data is well-formed, (b) the fake scorer is gone, and (c) the
ground-truth tasks were actually converted into the honest efficiency cases, where
the real CON-vs-SIN benchmark runs against them.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.evaluation.comparative import BUILTIN_SCENARIOS, Scenario
from opencontext_core.evaluation.efficiency import EfficiencyBenchmark
from opencontext_core.evaluation.evaluator import load_context_bench_cases
from opencontext_core.evaluation.models import ContextBenchCase, EfficiencyCaseResult
from opencontext_core.runtime import OpenContextRuntime

PROJECT_ROOT = Path(__file__).parent.parent.parent
CONTEXTBENCH = PROJECT_ROOT / "examples" / "evals" / "contextbench.yaml"


class TestGroundTruthData:
    def test_three_difficulty_tiers(self) -> None:
        assert len(BUILTIN_SCENARIOS) == 3
        tiers = {s.difficulty for s in BUILTIN_SCENARIOS}
        assert tiers == {"simple", "medium", "hard"}

    def test_scenarios_carry_relevant_files(self) -> None:
        for s in BUILTIN_SCENARIOS:
            assert isinstance(s, Scenario)
            assert s.relevant_files, f"{s.id} has no relevant files"
            assert s.task

    def test_no_fake_scorer_remains(self) -> None:
        import opencontext_core.evaluation.comparative as cmp

        for fake in ("ComparativeBenchmark", "ScenarioResult", "format_comparative_report"):
            assert not hasattr(cmp, fake), f"{fake} must stay excised"


class TestGroundTruthConvertedToEfficiencyCases:
    """The 3 curated scenarios were mirrored into the honest contextbench suite."""

    def test_scenarios_present_as_cases(self) -> None:
        case_ids = {c.id for c in load_context_bench_cases(CONTEXTBENCH)}
        for s in BUILTIN_SCENARIOS:
            assert s.id in case_ids, f"scenario {s.id} not converted into a contextbench case"

    def test_converted_cases_carry_target_and_difficulty(self) -> None:
        cases = {c.id: c for c in load_context_bench_cases(CONTEXTBENCH)}
        for s in BUILTIN_SCENARIOS:
            case = cases[s.id]
            assert case.target_symbol, f"{s.id} case missing target_symbol"
            assert case.difficulty == s.difficulty


class TestRealEfficiencyRunReplacesFakeScorer:
    """A real CON-vs-SIN run executes — no answer-key precision/recall fiction."""

    def test_efficiency_case_runs_on_tmp_project(self, tmp_path: Path) -> None:
        # A minimal project the real prepare_context can index and pack.
        (tmp_path / "detector.py").write_text(
            "class BridgeDetector:\n    def count_by_type(self) -> dict:\n        return {}\n",
            encoding="utf-8",
        )
        (tmp_path / "caller.py").write_text(
            "from detector import BridgeDetector\n\n\n"
            "def scan() -> dict:\n"
            "    return BridgeDetector().count_by_type()\n",
            encoding="utf-8",
        )
        runtime = OpenContextRuntime(storage_path=tmp_path / ".storage" / "opencontext")
        runtime.index_project(tmp_path)

        bench = EfficiencyBenchmark(runtime, root=tmp_path, max_tokens=2000)
        case = ContextBenchCase(
            id="simple/bridge-count-method",
            query="Add count_by_type() to BridgeDetector",
            expected_sources=["detector.py"],
            target_symbol="BridgeDetector",
            difficulty="simple",
        )
        result = bench.evaluate_case(case)

        assert isinstance(result, EfficiencyCaseResult)
        # CON is one real call; SIN really grepped + read the hit files.
        assert result.con.tool_calls == 1
        assert result.sin.tool_calls >= 2
        assert result.con.tokens > 0
        assert result.sin.tokens > 0
