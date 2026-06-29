#!/usr/bin/env python3
"""Execute the parity-gated vNext default-flip sequence (AVH-007 / B3, task 8.3).

For each subsystem in the documented :data:`FLIP_SEQUENCE`, in order:

1. snapshot the legacy default (flag OFF);
2. run the subsystem's targeted tests BEFORE (legacy) -> failure count;
3. tentatively flip the flag default to ``True`` in ``config.py``;
4. run the targeted tests AFTER (vNext) -> failure count;
5. ``compat.parity.check_parity`` legacy-vs-vNext (no NEW failures == parity holds);
6. ACCEPT iff parity holds AND the after-benchmark (targeted failures) is not worse,
   keeping the default ``True`` and writing an accepted evidence bundle; otherwise
   AUTO-REVERT (restore the ``False`` default) and write a reverted bundle with the
   reason.

Flips are cumulative: an accepted flip stays ON while the next subsystem is evaluated,
so vNext becomes the default subsystem-by-subsystem only where parity is proven. The
mechanism NEVER forces a flip. Bundles land in ``.opencontext/flips/<subsystem>.json``.

Run:  .venv/bin/python scripts/run_flip_sequence.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from opencontext_core.compat.flip_evidence import (
    FLIP_SEQUENCE,
    SUBSYSTEM_FLAGS,
    emit_flip_evidence,
    sequence_violation,
)
from opencontext_core.compat.parity import check_parity

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "packages" / "opencontext_core" / "opencontext_core" / "config.py"
ROLLBACK_PATH = "packages/opencontext_core/opencontext_core/config.py"

# subsystem -> targeted test paths (the per-flip parity probe).
SUBSETS: dict[str, list[str]] = {
    "workflow_registry": ["tests/workflows", "tests/registries"],
    "artifact_store": ["tests/runtime", "tests/harness"],
    "oc_flow": ["tests/workflows", "tests/runtime"],
    "context_engine": [
        "tests/planning",
        "tests/behavioral",
        "tests/core/test_context_plan.py",
        "tests/core/test_context_engine_v2_strategies.py",
        "tests/core/test_context_contract.py",
    ],
    "knowledge_graph": ["tests/cache", "tests/core/test_kg_v2_observability.py"],
    "memory": [
        "tests/core/test_memory_v2_provider.py",
        "tests/core/test_memory_provenance.py",
        "tests/core/test_memory_review.py",
        "tests/core/test_memory_harvester.py",
        "tests/architecture/test_no_direct_memory_writes.py",
    ],
    "provider_gateway": ["tests/providers", "tests/runtime"],
    "persona_registry": ["tests/registries"],
    "skill_registry": ["tests/registries"],
    "harness_registry": ["tests/registries", "tests/harness"],
    "runtime_brain": ["tests/runtime", "tests/intelligence"],
    "runtime_intelligence": ["tests/intelligence"],
}

_RT_BRAIN_OLD = (
    "    enabled: bool = Field(\n        default=False,\n"
    "        description=(\n"
    '            "Enable advisory Runtime Brain decision recording.'
)


def _anchors(subsystem: str) -> tuple[str, str]:
    """Return the (off, on) source snippets for *subsystem*'s flag default."""
    flag = SUBSYSTEM_FLAGS[subsystem]
    if subsystem == "runtime_brain":
        on = _RT_BRAIN_OLD.replace("default=False", "default=True")
        return _RT_BRAIN_OLD, on
    field = flag.split(".")[-1]
    off = f"    {field}: bool = Field(\n        default=False"
    on = f"    {field}: bool = Field(\n        default=True"
    return off, on


def _set_default(subsystem: str, *, on: bool) -> None:
    off_snip, on_snip = _anchors(subsystem)
    text = CONFIG.read_text(encoding="utf-8")
    want, have = (on_snip, off_snip) if on else (off_snip, on_snip)
    if want in text:
        return  # already in the desired state
    if have not in text:
        raise SystemExit(f"anchor not found for {subsystem} (on={on})")
    CONFIG.write_text(text.replace(have, want, 1), encoding="utf-8")


def _run_targeted(subsystem: str) -> dict[str, int]:
    """Run the subsystem's targeted tests; counts come from junit XML (robust).

    The repo pins ``addopts = -q`` which suppresses the terminal summary line in
    captured output, so we read exact counts from ``--junitxml`` instead. A run that
    produced NO junit file (a collection crash) is recorded as a failure, never a
    silent green (build-rule #1: never fabricate a pass).
    """
    paths = [str(REPO / p) for p in SUBSETS[subsystem]]
    xml_path = Path(tempfile.mkdtemp(prefix="flip_")) / "j.xml"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:randomly",
            "--tb=no",
            f"--junitxml={xml_path}",
            *paths,
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    counts = {
        "tests": 0,
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "returncode": proc.returncode,
    }
    try:
        root = ET.parse(xml_path).getroot()
        suites = root.findall("testsuite") or ([root] if root.tag == "testsuite" else [])
        for s in suites:
            counts["tests"] += int(s.get("tests", 0))
            counts["failed"] += int(s.get("failures", 0))
            counts["errors"] += int(s.get("errors", 0))
            counts["skipped"] += int(s.get("skipped", 0))
        counts["passed"] = counts["tests"] - counts["failed"] - counts["errors"] - counts["skipped"]
    except (OSError, ET.ParseError):
        counts["errors"] = max(counts["errors"], 1)  # no XML -> crash -> count as failure
    return counts


def main() -> int:
    accepted: list[str] = []
    rows: list[tuple[str, str, str]] = []
    for subsystem in FLIP_SEQUENCE:
        flag = SUBSYSTEM_FLAGS[subsystem]
        _set_default(subsystem, on=False)  # ensure legacy baseline for the before-run
        before = _run_targeted(subsystem)
        b_fail = before["failed"] + before["errors"]

        _set_default(subsystem, on=True)  # tentatively flip
        after = _run_targeted(subsystem)
        a_fail = after["failed"] + after["errors"]

        # No targeted tests ran => parity is UNPROVEN, never a silent accept.
        if after["tests"] == 0 or before["tests"] == 0:
            parity = check_parity(subsystem, flag, legacy="ran", vnext="no-targeted-tests")
        else:
            parity = check_parity(
                subsystem, flag, legacy=b_fail, vnext=a_fail, equals=lambda a, b: b <= a
            )
        bundle = emit_flip_evidence(
            REPO,
            subsystem,
            flag,
            config_before={flag: False},
            config_after={flag: True},
            benchmark_before={"tests": {"passed": before["passed"], "failed": b_fail}},
            benchmark_after={"tests": {"passed": after["passed"], "failed": a_fail}},
            parity=parity,
            rollback_flag=flag,
            rollback_path=ROLLBACK_PATH,
        )
        if bundle.accepted:
            accepted.append(subsystem)  # keep the flag ON (cumulative)
            verdict = "ACCEPTED"
        else:
            _set_default(subsystem, on=False)  # AUTO-REVERT
            verdict = "REVERTED"
        rows.append((subsystem, verdict, f"before_fail={b_fail} after_fail={a_fail}"))
        print(f"[{verdict:8}] {subsystem:22} flag={flag:34} {rows[-1][2]}")

    violation = sequence_violation(accepted)
    if violation:
        print(f"\nSEQUENCE VIOLATION: {violation}")
    print(f"\nACCEPTED ({len(accepted)}): {accepted or '(none)'}")
    print(
        f"REVERTED ({len(FLIP_SEQUENCE) - len(accepted)}): "
        f"{[s for s in FLIP_SEQUENCE if s not in accepted]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
