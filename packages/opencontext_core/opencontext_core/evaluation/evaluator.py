"""Evaluation interfaces and basic structural evaluator."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Protocol

import yaml

from opencontext_core.evaluation.models import (
    ContextBenchCase,
    ContextBenchCaseResult,
    ContextBenchSuiteResult,
    CostTriple,
    EfficiencyCaseResult,
    EvalCase,
    EvalResult,
)
from opencontext_core.evaluation.naive_agent import run_naive_case
from opencontext_core.runtime import OpenContextRuntime


class Evaluator(Protocol):
    """Evaluator interface for future quality checks."""

    def evaluate(self, case: EvalCase) -> EvalResult:
        """Evaluate one case."""


class BasicEvaluator:
    """Performs basic structural checks without model calls."""

    def evaluate(self, case: EvalCase) -> EvalResult:
        """Validate that the case is structurally usable."""

        reasons: list[str] = []
        if not case.input.strip():
            reasons.append("input is empty")
        if not case.workflow.strip():
            reasons.append("workflow is empty")
        if set(case.expected_sources) & set(case.forbidden_sources):
            reasons.append("same source appears in expected and forbidden sources")
        passed = not reasons
        return EvalResult(
            case_id=case.id,
            passed=passed,
            score=1.0 if passed else 0.0,
            reasons=reasons or ["basic structural checks passed"],
        )


def load_eval_cases(path: str | Path) -> list[EvalCase]:
    """Load eval cases from YAML or JSON."""

    eval_path = Path(path)
    raw_text = eval_path.read_text(encoding="utf-8")
    if eval_path.suffix.lower() == ".json":
        raw_data = json.loads(raw_text)
    else:
        raw_data = yaml.safe_load(raw_text)
    if isinstance(raw_data, dict) and "cases" in raw_data:
        raw_cases = raw_data["cases"]
    else:
        raw_cases = raw_data
    if not isinstance(raw_cases, list):
        raise ValueError("Eval file must contain a list of cases or a mapping with `cases`.")
    return [EvalCase.model_validate(raw_case) for raw_case in raw_cases]


class ContextBenchEvaluator:
    """Runs deterministic context quality and token-efficiency benchmark cases."""

    def __init__(
        self,
        runtime: OpenContextRuntime,
        *,
        root: str | Path = ".",
        max_tokens: int = 6000,
        min_token_reduction: float = 0.5,
    ) -> None:
        self.runtime = runtime
        self.root = Path(root)
        self.max_tokens = max_tokens
        self.min_token_reduction = min_token_reduction

    def evaluate_suite(self, cases: list[ContextBenchCase]) -> ContextBenchSuiteResult:
        """Evaluate a list of golden context benchmark cases."""

        baseline_tokens = _manifest_token_baseline(self.runtime)
        results = [self.evaluate_case(case, baseline_tokens=baseline_tokens) for case in cases]
        average_source_coverage = (
            sum(result.source_coverage for result in results) / len(results) if results else 0.0
        )
        average_token_reduction = (
            sum(result.token_reduction for result in results) / len(results) if results else 0.0
        )
        return ContextBenchSuiteResult(
            passed=all(result.passed for result in results),
            cases=results,
            average_source_coverage=average_source_coverage,
            average_token_reduction=average_token_reduction,
        )

    def evaluate_case(
        self,
        case: ContextBenchCase,
        *,
        baseline_tokens: int | None = None,
    ) -> ContextBenchCaseResult:
        """Evaluate one golden context benchmark case."""

        baseline = baseline_tokens or _manifest_token_baseline(self.runtime)
        prepared = self.runtime.prepare_context(
            case.query,
            root=self.root,
            max_tokens=self.max_tokens,
            refresh_index=False,
        )
        included_sources = prepared.included_sources
        missing_sources = [
            expected
            for expected in case.expected_sources
            if not _source_fragment_present(expected, included_sources)
        ]
        forbidden_hits = [
            forbidden
            for forbidden in case.forbidden_sources
            if _source_fragment_present(forbidden, included_sources)
        ]
        expected_count = len(case.expected_sources)
        source_coverage = (
            (expected_count - len(missing_sources)) / expected_count if expected_count > 0 else 1.0
        )
        context_tokens = prepared.token_usage.get(
            "final_context_pack",
            prepared.token_usage.get("prompt", 0),
        )
        token_reduction = max(0.0, 1.0 - (context_tokens / baseline)) if baseline > 0 else 0.0
        reasons: list[str] = []
        if source_coverage < case.min_source_coverage:
            _cov_reason = (
                f"source coverage {source_coverage:.2f} below required "
                f"{case.min_source_coverage:.2f}"
            )
            # Append a hint when the evaluated root is not the OC project itself.
            # Detection: the OC repo contains packages/opencontext_core; a generic
            # project typically does not.
            _is_oc_root = (self.root / "packages" / "opencontext_core").exists()
            if not _is_oc_root:
                _cov_reason += (
                    " (hint: run with --root <project> or a project-appropriate suite;"
                    " default suite targets OpenContext sources)"
                )
            reasons.append(_cov_reason)
        if forbidden_hits:
            reasons.append(f"forbidden sources included: {', '.join(forbidden_hits)}")
        if token_reduction < self.min_token_reduction:
            reasons.append(
                f"token reduction {token_reduction:.2f} below required "
                f"{self.min_token_reduction:.2f}"
            )
        return ContextBenchCaseResult(
            case_id=case.id,
            passed=not reasons,
            source_coverage=source_coverage,
            token_reduction=token_reduction,
            context_tokens=context_tokens,
            baseline_tokens=baseline,
            included_sources=included_sources,
            missing_sources=missing_sources,
            forbidden_hits=forbidden_hits,
            reasons=reasons or ["context coverage and token gates passed"],
        )

    def evaluate_efficiency_case(
        self,
        case: ContextBenchCase,
        *,
        refresh_index: bool = False,
        include_ceiling: bool = True,
    ) -> EfficiencyCaseResult:
        """Measure the honest cost of building this case's context, CON vs SIN.

        CON is a SINGLE real ``prepare_context`` call (KG + compression + memory):
        its cost is the pack's tokens, exactly one tool call, and the wall-clock to
        build it. The mandatory quality-parity gate (coverage / forbidden) is reused
        verbatim from :meth:`evaluate_case`; a CON pack that misses an expected source
        or hits a forbidden one is ``con_sufficient=False`` and is NOT a win. SIN is
        the realistic OpenContext-free grep+Read control. The whole-repo baseline is
        attached only as a labeled ``ceiling_tokens`` — never the headline.
        """

        t0 = time.monotonic()
        prepared = self.runtime.prepare_context(
            case.query,
            root=self.root,
            max_tokens=self.max_tokens,
            refresh_index=refresh_index,
        )
        con_latency_ms = (time.monotonic() - t0) * 1000

        included_sources = prepared.included_sources
        missing_sources = [
            expected
            for expected in case.expected_sources
            if not _source_fragment_present(expected, included_sources)
        ]
        forbidden_hits = [
            forbidden
            for forbidden in case.forbidden_sources
            if _source_fragment_present(forbidden, included_sources)
        ]
        expected_count = len(case.expected_sources)
        source_coverage = (
            (expected_count - len(missing_sources)) / expected_count if expected_count > 0 else 1.0
        )
        context_tokens = prepared.token_usage.get(
            "final_context_pack",
            prepared.token_usage.get("prompt", 0),
        )

        # Mandatory quality-parity verdict (R4/EB-4): correct context or it is no win.
        con_sufficient = source_coverage >= case.min_source_coverage and not forbidden_hits
        reasons: list[str] = []
        if source_coverage < case.min_source_coverage:
            reason = (
                f"source coverage {source_coverage:.2f} below required "
                f"{case.min_source_coverage:.2f}"
            )
            if not (self.root / "packages" / "opencontext_core").exists():
                reason += (
                    " (hint: the default benchmark suite targets OpenContext internals; "
                    "use --suite your-suite.yaml for this project)"
                )
            reasons.append(reason)
        if forbidden_hits:
            reasons.append(f"forbidden sources included: {', '.join(forbidden_hits)}")
        if not reasons:
            reasons.append("quality parity met (coverage and forbidden gates passed)")

        con = CostTriple(tokens=context_tokens, tool_calls=1, latency_ms=con_latency_ms)
        sin = run_naive_case(case, self.root)
        ceiling = _manifest_token_baseline(self.runtime) if include_ceiling else None

        return EfficiencyCaseResult(
            case_id=case.id,
            difficulty=case.difficulty,
            con=con,
            sin=sin,
            ceiling_tokens=ceiling,
            con_sufficient=con_sufficient,
            source_coverage=source_coverage,
            forbidden_hits=forbidden_hits,
            reasons=reasons,
        )


def load_context_bench_cases(path: str | Path) -> list[ContextBenchCase]:
    """Load context benchmark cases from YAML or JSON."""

    eval_path = Path(path)
    raw_text = eval_path.read_text(encoding="utf-8")
    if eval_path.suffix.lower() == ".json":
        raw_data = json.loads(raw_text)
    else:
        raw_data = yaml.safe_load(raw_text)
    raw_cases = raw_data.get("cases", raw_data) if isinstance(raw_data, dict) else raw_data
    if not isinstance(raw_cases, list):
        raise ValueError("ContextBench file must contain a list or a mapping with `cases`.")
    return [ContextBenchCase.model_validate(raw_case) for raw_case in raw_cases]


def _source_fragment_present(fragment: str, sources: list[str]) -> bool:
    return any(fragment in source for source in sources)


def _manifest_token_baseline(runtime: OpenContextRuntime) -> int:
    manifest = runtime.load_manifest()
    return sum(max(1, file.size_bytes // 4) for file in manifest.files)
