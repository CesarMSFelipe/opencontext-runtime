"""``opencontext benchmark release`` — library surface for the verdict command.

The CLI command is a thin wrapper over :func:`main`. Tests call the
:func:`_compute_verdict` and :func:`_run_release_no_subprocess` helpers
directly to keep the assertion surface hermetic (no subprocess).
"""

from __future__ import annotations

import json
import sys
from typing import Any

from opencontext_core.benchmarks.v2.release_runner import (
    run_release,
)
from opencontext_core.benchmarks.v2.runner import BenchmarkResult


def _compute_verdict(results: list[BenchmarkResult]) -> str:
    """Translate a list of results into the 1.0_READY / 1.0_NOT_READY string."""
    if not results:
        return "1.0_NOT_READY"
    return "1.0_READY" if all(r.success for r in results) else "1.0_NOT_READY"


def _run_release_no_subprocess(
    *, profile: str, run_gates: bool, run_suites: bool
) -> list[BenchmarkResult]:
    """Run the release verdict in-process — used by tests."""
    verdict = run_release(profile=profile, run_gates=run_gates, run_suites=run_suites)
    return verdict.results


def main(argv: list[str] | None = None) -> int:
    """CLI entry point — returns the process exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)
    profile = "balanced"
    fmt = "text"
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--profile":
            profile = argv[i + 1] if i + 1 < len(argv) else profile
            i += 2
        elif a == "--format":
            fmt = argv[i + 1] if i + 1 < len(argv) else fmt
            i += 2
        else:
            i += 1
    verdict = run_release(profile=profile, run_gates=True, run_suites=True)
    payload: dict[str, Any] = {
        "profile": verdict.profile,
        "verdict": verdict.verdict,
        "methodology_version": verdict.methodology_version,
        "results": [
            {
                "name": r.name,
                "success": r.success,
                "detail": r.detail,
                "metrics": r.metrics,
            }
            for r in verdict.results
        ],
    }
    if fmt == "json":
        print(json.dumps(payload, indent=2))
    else:
        print(f"verdict: {verdict.verdict!r}")
        print(f"profile: {verdict.profile}")
        print(f"methodology_version: {verdict.methodology_version}")
        for r in verdict.results:
            mark = "PASS" if r.success else "FAIL"
            print(f"  [{mark}] {r.name}: {r.detail}")
    return 0 if verdict.verdict == "1.0_READY" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
