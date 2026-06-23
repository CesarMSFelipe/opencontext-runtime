"""Tests for the multi-arm head-to-head measurement primitive.

``run_head_to_head`` runs a panel of agent arms over the same (repo, case). With no
``oc_arm_runner`` it must still produce the two control arms (SKILL-GREP, REALISTIC-SIN)
for every (repo, case) pair, and must NOT fabricate the OpenContext arms.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.evaluation.models import ContextBenchCase
from opencontext_core.evaluation.multi_arm import (
    ArmResult,
    CapabilityMatrix,
    MultiArmReport,
    run_head_to_head,
)


def _write(root: Path, rel: str, body: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


class TestModelsInstantiate:
    def test_arm_result_fields(self) -> None:
        arm = ArmResult(arm="OC-SURGICAL", tokens=120, tool_calls=2, latency_ms=3.5)
        assert arm.arm == "OC-SURGICAL"
        assert arm.tokens == 120
        assert arm.tool_calls == 2
        assert arm.latency_ms == 3.5

    def test_capability_matrix_fields(self) -> None:
        matrix = CapabilityMatrix(
            portability=True,
            tdd_gate=True,
            kg_grounding=True,
            impact_consulted=True,
            memory_used=True,
            spec_artifact=True,
            artifact_chain=True,
            correctness=True,
        )
        assert matrix.portability
        assert matrix.tdd_gate
        assert matrix.kg_grounding
        assert matrix.impact_consulted
        assert matrix.memory_used
        assert matrix.spec_artifact
        assert matrix.artifact_chain
        assert matrix.correctness

    def test_multi_arm_report_defaults(self) -> None:
        report = MultiArmReport(repo="/repo", case_id="c1")
        assert report.repo == "/repo"
        assert report.case_id == "c1"
        assert report.arms == []
        assert report.matrix == {}
        assert report.semantic_layer is False


class TestRunHeadToHeadControlsOnly:
    def test_yields_control_arms_without_oc_runner(self, tmp_path: Path) -> None:
        _write(tmp_path, "pkg/widget.py", "class Widget:\n    pass\n")
        _write(
            tmp_path,
            "pkg/usage.py",
            "from pkg.widget import Widget\n\n\ndef use() -> Widget:\n    return Widget()\n",
        )
        case = ContextBenchCase(id="widget", query="change Widget", target_symbol="Widget")

        reports = run_head_to_head([str(tmp_path)], [case], oc_arm_runner=None)

        assert len(reports) == 1
        report = reports[0]
        arm_names = {a.arm for a in report.arms}
        assert arm_names == {"SKILL-GREP", "REALISTIC-SIN"}
        # No OpenContext arms are fabricated when no runner is wired.
        assert not any(a.arm.startswith("OC-") for a in report.arms)
        # The matrix covers exactly the arms produced.
        assert set(report.matrix) == arm_names
        for matrix in report.matrix.values():
            assert isinstance(matrix, CapabilityMatrix)

    def test_report_count_is_repos_times_cases(self, tmp_path: Path) -> None:
        repo_a = tmp_path / "repo_a"
        repo_b = tmp_path / "repo_b"
        _write(repo_a, "a.py", "def alpha() -> int:\n    return 1\n")
        _write(repo_b, "b.py", "def beta() -> int:\n    return 2\n")
        cases = [
            ContextBenchCase(id="case-alpha", query="x", target_symbol="alpha"),
            ContextBenchCase(id="case-beta", query="y", target_symbol="beta"),
            ContextBenchCase(id="case-gamma", query="z", target_symbol="gamma"),
        ]
        repos = [str(repo_a), str(repo_b)]

        reports = run_head_to_head(repos, cases)

        assert len(reports) == len(repos) * len(cases)
        # Each (repo, case) pair appears exactly once.
        pairs = {(r.repo, r.case_id) for r in reports}
        assert pairs == {(repo, c.id) for repo in repos for c in cases}

    def test_oc_arm_runner_results_are_merged(self, tmp_path: Path) -> None:
        _write(tmp_path, "core.py", "def target_fn() -> int:\n    return 1\n")
        case = ContextBenchCase(id="t", query="change target_fn", target_symbol="target_fn")

        oc_matrix = CapabilityMatrix(
            portability=True,
            tdd_gate=True,
            kg_grounding=True,
            impact_consulted=True,
            memory_used=True,
            spec_artifact=True,
            artifact_chain=True,
            correctness=True,
        )

        def fake_oc_runner(
            repo: str, c: ContextBenchCase
        ) -> tuple[list[ArmResult], dict[str, CapabilityMatrix]]:
            arm = ArmResult(arm="OC-SURGICAL", tokens=42, tool_calls=1, latency_ms=0.0)
            return [arm], {"OC-SURGICAL": oc_matrix}

        reports = run_head_to_head([str(tmp_path)], [case], oc_arm_runner=fake_oc_runner)

        report = reports[0]
        arm_names = {a.arm for a in report.arms}
        assert arm_names == {"SKILL-GREP", "REALISTIC-SIN", "OC-SURGICAL"}
        assert report.matrix["OC-SURGICAL"].kg_grounding is True
