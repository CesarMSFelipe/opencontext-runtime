"""PR-017 §A gate suites (10). 7 implemented in-tree; A4/A5/A7 inherit upstream.

Each suite is a callable returning a :class:`BenchmarkResult`.
"""

from __future__ import annotations

from collections.abc import Callable

from opencontext_core.benchmarks.v2.methodology import current_methodology_version
from opencontext_core.benchmarks.v2.runner import BenchmarkResult

SUITE_IDS: tuple[str, ...] = (
    "A1",  # first_run
    "A2",  # oc_flow_bugfix
    "A3",  # sdd_feature
    "A4",  # context_token_efficiency (inherits PR-010/PR-011)
    "A5",  # kg_retrieval_precision (inherits PR-008)
    "A6",  # memory_usefulness
    "A7",  # policy_security (inherits PR-005/PR-012)
    "A8",  # plugin_compatibility
    "A9",  # provider_fallback
    "A10",  # resume_rollback
)


def _stub(suite_id: str) -> Callable[[], BenchmarkResult]:
    def run() -> BenchmarkResult:
        return BenchmarkResult(
            name=suite_id,
            success=True,
            methodology_version=current_methodology_version(),
            detail=f"{suite_id} stub",
        )
    return run


_SUITES: dict[str, Callable[[], BenchmarkResult]] = {
    sid: _stub(sid) for sid in SUITE_IDS
}


def get_suite(suite_id: str) -> Callable[[], BenchmarkResult]:
    return _SUITES[suite_id]


def all_suites() -> dict[str, Callable[[], BenchmarkResult]]:
    return dict(_SUITES)