"""PR-017 §A gate suites (12) for the 1.0 release verdict.

Each suite is a callable returning a :class:`BenchmarkResult`. The
twelve §A suites are:

* A1  first_run              — end-to-end first-run probe (real: B1)
* A2  oc_flow_bugfix         — bugfix flow on a seeded project (real: B2)
* A3  sdd_feature            — SDD feature flow (real: B2)
* A4  context_token_efficiency (real: B3)
* A5  kg_retrieval_precision  — KG indexing + caller/callee assertions (real: B1)
* A6  memory_usefulness       — memory v2 promotion policy roundtrip (real: B1)
* A7  policy_security        (real: B3)
* A8  plugin_compatibility   (real: B3)
* A9  provider_fallback      (real: B3)
* A10 resume_rollback        — checkpoint/resume tests (real: B2)
* A11 benchmark_evidence     — self-referential integrity gate (real: B1)
* A12 release_signature      (real: B3)

HONESTY RULES: no suite may return success=True without executing real
behaviour. Suites whose target behaviour is not yet wired return
success=False with detail naming the pending batch.
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


# ---------------------------------------------------------------------------
# Honest-pending helper — used ONLY for suites not yet wired in this batch.
# Returns success=False with a named blocker; detail never contains "stub".
# ---------------------------------------------------------------------------


def _pending_suite(suite_id: str, detail: str) -> Callable[[], BenchmarkResult]:
    """Return an honest-fail callable for a suite pending implementation."""

    def run() -> BenchmarkResult:
        return BenchmarkResult(
            name=suite_id,
            success=False,
            methodology_version=current_methodology_version(),
            detail=detail,
        )

    return run


# ---------------------------------------------------------------------------
# Real suites wired in B1
# ---------------------------------------------------------------------------

from opencontext_core.benchmarks.v2.suites import (  # noqa: E402
    a5_kg_retrieval_precision,
    a6_memory_usefulness,
    a11_benchmark_evidence,
    first_run_user_flow,
)

_SUITES: dict[str, Callable[[], BenchmarkResult]] = {
    # B1 — real
    "A1": first_run_user_flow.run,
    "A5": a5_kg_retrieval_precision.run,
    "A6": a6_memory_usefulness.run,
    "A11": a11_benchmark_evidence.run,
    # B2 — pending (wired in B2 batch)
    "A2": _pending_suite("A2", "oc_flow_bugfix pending — wired in B2"),
    "A3": _pending_suite("A3", "sdd_feature pending — wired in B2"),
    "A10": _pending_suite("A10", "resume_rollback pending — wired in B2"),
    # B3 — pending (wired in B3 batch)
    "A4": _pending_suite("A4", "context_token_efficiency pending — wired in B3"),
    "A7": _pending_suite("A7", "policy_security pending — wired in B3"),
    "A8": _pending_suite("A8", "plugin_compatibility pending — wired in B3"),
    "A9": _pending_suite("A9", "provider_fallback pending — wired in B3"),
    "A12": _pending_suite("A12", "release_signature pending — wired in B3"),
}


def get_suite(suite_id: str) -> Callable[[], BenchmarkResult]:
    return _SUITES[suite_id]


def all_suites() -> dict[str, Callable[[], BenchmarkResult]]:
    return dict(_SUITES)
