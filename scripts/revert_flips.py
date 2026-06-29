#!/usr/bin/env python3
"""Auto-revert every tentatively-accepted flip after the FULL suite regressed (task 8.3).

The per-flip targeted probe passed for each subsystem, but the FULL test suite is the
final arbiter and it regressed: flipping ANY vNext ``*_enabled`` default violates the
codebase's encoded CL-005 contract (``tests/compat/test_compat_flags.py``:
``test_every_enabled_flag_defaults_legacy_unless_flipped`` / ``test_one_flip_is_isolated`` /
``test_catalog_includes_vnext_subsystem_flags``), because the subsystems have not met the
CL-006 "migrated" criteria (migration_state still legacy/adapted). Per the honesty bar we
auto-revert every flip: restore the legacy ``False`` default in config.py and re-emit each
evidence bundle as ``reverted=True`` — the bundle records the targeted parity result AND
the full-suite regression that triggered the revert.

Run after the arbiter:  .venv/bin/python scripts/revert_flips.py
"""

from __future__ import annotations

import json
from pathlib import Path

# Reuse the driver's config-default editing helpers.
import run_flip_sequence as drv  # type: ignore[import-not-found]

from opencontext_core.compat.flip_evidence import (
    FLIP_SEQUENCE,
    SUBSYSTEM_FLAGS,
    emit_flip_evidence,
    flip_bundle_path,
)

REPO = Path(__file__).resolve().parents[1]
_SUITE = "full-suite (CL-005 default-legacy contract)"
_REASON_SUITES_BEFORE = {_SUITE: "met"}
_REASON_SUITES_AFTER = {_SUITE: "failed"}


def main() -> int:
    for subsystem in FLIP_SEQUENCE:
        flag = SUBSYSTEM_FLAGS[subsystem]
        # 1) restore the legacy default in config.py (auto-revert).
        drv._set_default(subsystem, on=False)

        # 2) re-emit the bundle reflecting the full-suite regression -> reverted.
        prev = json.loads(flip_bundle_path(REPO, subsystem).read_text(encoding="utf-8"))
        before_tests = prev.get("benchmark_before", {}).get("tests", {})
        after_tests = prev.get("benchmark_after", {}).get("tests", {})
        bundle = emit_flip_evidence(
            REPO,
            subsystem,
            flag,
            config_before={flag: False},
            config_after={flag: True},
            benchmark_before={"suites": dict(_REASON_SUITES_BEFORE), "tests": before_tests},
            benchmark_after={"suites": dict(_REASON_SUITES_AFTER), "tests": after_tests},
            parity=prev.get("parity", {"passed": True}),
            rollback_flag=flag,
            rollback_path=drv.ROLLBACK_PATH,
        )
        assert bundle.reverted and not bundle.accepted, subsystem
        print(f"[REVERTED] {subsystem:22} {flag:34} {bundle.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
