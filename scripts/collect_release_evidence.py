#!/usr/bin/env python3
"""Produce the repo-root acceptance evidence artifacts from a REAL DoD journey (VDM-006/007).

Runs the audit Definition-of-Done sequence (install -> doctor --strict -> index -> run
"Fix failing test" --workflow auto -> pytest) over the golden bugfix fixture in an
isolated temp project, derives the 15 functional (B) + 3 governance (D) gate outcomes
from the genuine journey, and writes two artifacts the ``release acceptance`` evaluator
reads:

* ``<root>/.opencontext/e2e/dod-proof.json``        — the mandatory ``e2e-dod`` gate.
* ``<root>/.opencontext/e2e/release-evidence.json`` — the 15 B + 3 D gate evidence.

It REUSES the single journey driver + evidence collector from
``tests/e2e/test_developer_journey.py`` (one implementation, no drift). Honesty
(build-rule #1): a dimension the journey could not exercise is simply omitted so its
gate stays NOT_MEASURED — never a fabricated pass.

Run:  .venv/bin/python scripts/collect_release_evidence.py --root .
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
# The journey driver + collector live in the e2e test module (single source of truth).
sys.path.insert(0, str(_REPO_ROOT / "tests" / "e2e"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect DoD + B/D release evidence.")
    parser.add_argument("--root", default=".", help="Repo root to write evidence under.")
    args = parser.parse_args()
    root = Path(args.root).resolve()

    from test_developer_journey import (  # type: ignore[import-not-found]
        _collect_functional_governance,
        run_dod_journey,
    )

    from conftest import _subprocess_env  # type: ignore[import-not-found]
    from opencontext_core.evaluation.golden import FIXTURE_DIRS, GOLDEN_ROOT
    from opencontext_core.operating_model.release_gate import (
        write_dod_proof,
        write_release_evidence,
    )

    base = Path(tempfile.mkdtemp(prefix="release_evidence_"))
    try:
        work = base / "repo"
        shutil.copytree(GOLDEN_ROOT / FIXTURE_DIRS["oc-flow-localized-bugfix"], work)
        home = base / "home"
        home.mkdir(parents=True, exist_ok=True)
        # Same absolute-PYTHONPATH subprocess env the e2e uses, so the real-CLI `run`
        # mutation step (now a subprocess via run_dod_journey) imports the packages
        # regardless of how this script was invoked (B7).
        env = _subprocess_env(home)

        steps, summary = run_dod_journey(work, env)
        passed = all(bool(s["ok"]) for s in steps)
        functional, governance = _collect_functional_governance(work, steps, summary)

        proof_path = write_dod_proof(root, passed=passed, steps=steps)
        evidence_path = write_release_evidence(root, functional=functional, governance=governance)
    finally:
        shutil.rmtree(base, ignore_errors=True)

    print(f"DoD journey passed: {passed}")
    print(f"  wrote {proof_path} ({len(steps)} steps)")
    print(f"  wrote {evidence_path} ({len(functional)} B + {len(governance)} D gates)")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
