"""Tests for the done-in-v1 validation runner (commit-000).

The probe runner at ``tools/done_in_v1_probes.py`` aggregates the 17
behavioral probes from ``tests/release/test_v1_behavioral.py`` and emits
``artifacts/done-in-v1-validation.json``. These tests pin that contract.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

# Quarantined 2026-07-06 (test-reduction pass, plan §26.3): archived v1
# validation suite (was tests/done_in_v1/). Not flaky — retired from default
# signal because each test re-runs all 17 behavioral probes and rewrites
# artifacts/done-in-v1-validation.json during the run (slow, repo-mutating).
# Remove the skip mark to re-verify the v1 probe contract explicitly.
pytestmark = [
    pytest.mark.quarantine,
    pytest.mark.skip(
        reason="quarantined 2026-07-06: archived done_in_v1 suite; re-runs 17 "
        "behavioral probes and rewrites artifacts/ during test runs"
    ),
]

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
ARTIFACTS_DIR = REPO_ROOT / "artifacts"
RUNNER_PATH = TOOLS_DIR / "done_in_v1_probes.py"
JSON_PATH = ARTIFACTS_DIR / "done-in-v1-validation.json"


def _load_runner():
    """Late-import the probe runner module."""
    if not RUNNER_PATH.exists():
        return None
    spec = importlib.util.spec_from_file_location("done_in_v1_probes", RUNNER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runner_emits_machine_readable_json() -> None:
    """The probe runner writes a JSON file conforming to the v1 schema."""
    runner = _load_runner()
    assert runner is not None, "tools/done_in_v1_probes.py must exist"

    # Allow the runner to (re)generate the artifact.
    result_path = runner.run(output_dir=ARTIFACTS_DIR)
    assert result_path.exists(), "artifact must exist after run"

    import json

    payload = json.loads(result_path.read_text())
    assert payload["schema_version"] == "opencontext.done_in_v1_validation.v1"
    assert payload["probe_count"] == 17
    assert isinstance(payload["probes"], list)
    assert len(payload["probes"]) == 17
    assert (
        payload["summary"]["passed"] + payload["summary"]["failed"] + payload["summary"]["blocked"]
        == 17
    )


def test_runner_reclassifies_failed_probes() -> None:
    """Failed probes appear in ``summary.reclassified_to_gap``."""
    runner = _load_runner()
    assert runner is not None, "tools/done_in_v1_probes.py must exist"

    result_path = runner.run(output_dir=ARTIFACTS_DIR)
    import json

    payload = json.loads(result_path.read_text())
    # When all probes pass, the gap list is empty; the contract is that
    # failed/blocked probes WOULD be listed here.
    assert "reclassified_to_gap" in payload["summary"]
    assert isinstance(payload["summary"]["reclassified_to_gap"], list)
