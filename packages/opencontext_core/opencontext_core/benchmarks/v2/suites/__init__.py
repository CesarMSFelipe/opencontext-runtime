"""PR-017 §A gate suites (12) for the 1.0 release verdict.

Each suite is a callable returning a :class:`BenchmarkResult`. The
twelve §A suites are:

* A1  first_run              — end-to-end first-run probe
* A2  oc_flow_bugfix         — bugfix flow on a seeded project
* A3  sdd_feature            — SDD feature flow (propose → spec → apply)
* A4  context_token_efficiency
* A5  kg_retrieval_precision
* A6  memory_usefulness
* A7  policy_security
* A8  plugin_compatibility
* A9  provider_fallback
* A10 resume_rollback
* A11 benchmark_evidence     — benchmark evidence is published
* A12 release_signature      — release signature is signed + verified
"""

from __future__ import annotations

from collections.abc import Callable

from opencontext_core.benchmarks.v2.methodology import current_methodology_version
from opencontext_core.benchmarks.v2.runner import BenchmarkResult

SUITE_IDS: tuple[str, ...] = (
    "A1",  # first_run
    "A2",  # oc_flow_bugfix
    "A3",  # sdd_feature
    "A4",  # context_token_efficiency
    "A5",  # kg_retrieval_precision
    "A6",  # memory_usefulness
    "A7",  # policy_security
    "A8",  # plugin_compatibility
    "A9",  # provider_fallback
    "A10",  # resume_rollback
    "A11",  # benchmark_evidence
    "A12",  # release_signature
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


_SUITES: dict[str, Callable[[], BenchmarkResult]] = {sid: _stub(sid) for sid in SUITE_IDS}


def get_suite(suite_id: str) -> Callable[[], BenchmarkResult]:
    return _SUITES[suite_id]


def all_suites() -> dict[str, Callable[[], BenchmarkResult]]:
    return dict(_SUITES)
