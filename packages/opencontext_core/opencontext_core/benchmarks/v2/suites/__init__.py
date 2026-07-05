"""PR-017 §A gate suites (12) for the 1.0 release verdict.

Each suite is a callable returning a :class:`BenchmarkResult`. The
twelve §A suites are:

* A1  first_run              — end-to-end first-run probe (real: B1)
* A2  oc_flow_bugfix         — bugfix flow on a seeded project (real: B1+B2)
* A3  sdd_feature            — SDD feature flow (real: B1+B2)
* A4  context_token_efficiency — in-process ContextSubstrateBuilder compression gate (real: B3)
* A5  kg_retrieval_precision  — KG indexing + caller/callee assertions (real: B1)
* A6  memory_usefulness       — memory v2 promotion policy roundtrip (real: B1)
* A7  policy_security        — subprocess pytest over policy/gateway tests (real: B3)
* A8  plugin_compatibility   — subprocess pytest over plugin SDK tests (real: B3)
* A9  provider_fallback      — subprocess pytest over fallback tests (real: B3)
* A10 resume_rollback        — checkpoint/resume tests (real: B1+B2)
* A11 benchmark_evidence     — self-referential integrity gate (real: B1)
* A12 release_signature      — check dist/ signed artifact + signing infra (real: B3)

HONESTY RULES: no suite may return success=True without executing real
behaviour. A suite that cannot verify its target returns success=False
with detail naming the blocker.
"""

from __future__ import annotations

from collections.abc import Callable

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
# Real suites — all 12 §A suites wired (B1 + B2 + B3)
# ---------------------------------------------------------------------------

from opencontext_core.benchmarks.v2.suites import (  # noqa: E402
    a2_oc_flow_bugfix,
    a3_sdd_feature,
    a4_context_token_efficiency,
    a5_kg_retrieval_precision,
    a6_memory_usefulness,
    a7_policy_security,
    a8_plugin_compatibility,
    a9_provider_fallback,
    a10_resume_rollback,
    a11_benchmark_evidence,
    a12_release_signature,
    first_run_user_flow,
)

_SUITES: dict[str, Callable[[], BenchmarkResult]] = {
    # B1 — real
    "A1": first_run_user_flow.run,
    "A5": a5_kg_retrieval_precision.run,
    "A6": a6_memory_usefulness.run,
    "A11": a11_benchmark_evidence.run,
    # B2 — real
    "A2": a2_oc_flow_bugfix.run,
    "A3": a3_sdd_feature.run,
    "A10": a10_resume_rollback.run,
    # B3 — real
    "A4": a4_context_token_efficiency.run,
    "A7": a7_policy_security.run,
    "A8": a8_plugin_compatibility.run,
    "A9": a9_provider_fallback.run,
    "A12": a12_release_signature.run,
}


def get_suite(suite_id: str) -> Callable[[], BenchmarkResult]:
    return _SUITES[suite_id]


def all_suites() -> dict[str, Callable[[], BenchmarkResult]]:
    return dict(_SUITES)
