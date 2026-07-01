"""Done-in-v1 probe runner (commit-000).

Aggregates the 17 behavioral probes from ``tests/release/test_v1_behavioral.py``
and emits ``artifacts/done-in-v1-validation.json``. Failed/blocked probes are
recorded in ``summary.reclassified_to_gap`` so downstream consumers can detect
phases that must be reclassified DONE-IN-V1 → GAP-FROM-V1.

The runner is deterministic — same input → same output — and never mutates
production code.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE_TEST = REPO_ROOT / "tests" / "release" / "test_v1_behavioral.py"
ARTIFACT = "done-in-v1-validation.json"


def _run_pytest_collect() -> list[str]:
    """Collect probe test ids from the behavioral probe test file."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(PROBE_TEST),
            "--collect-only",
            "-v",
            "--no-header",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    ids: list[str] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if "<Function " in stripped and stripped.endswith(">"):
            # Format: <Function test_name>
            name = stripped[len("<Function "):-1]
            ids.append(name)
    return ids


def _run_pytest(node_ids: list[str]) -> tuple[str, dict[str, tuple[str, str]]]:
    """Run each probe in isolation; return (overall, {id: (status, detail)})."""
    statuses: dict[str, tuple[str, str]] = {}
    overall = "passed"
    for node_id in node_ids:
        start = time.monotonic()
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                f"{PROBE_TEST}::{node_id}",
                "--tb=no",
                "-q",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        if result.returncode == 0:
            statuses[node_id] = ("passed", f"tests/release/test_v1_behavioral.py:{node_id}")
        else:
            err = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else ""
            statuses[node_id] = ("failed", err)
            overall = "failed"
        # Attach duration info via side-channel: encode in the detail string.
        statuses[node_id] = (statuses[node_id][0], f"duration_ms={duration_ms}")
    return overall, statuses


def _capability_for(node_id: str) -> str:
    """Map a probe test id to its capability bucket (phase matrix)."""
    if node_id.startswith("test_workflow_registry"):
        return "workflow_registry"
    if node_id.startswith("test_brain_records_"):
        return "brain_scheduler"
    if node_id.startswith("test_capability_graph"):
        return "capability_graph"
    if node_id.startswith("test_harness_"):
        return "harness_registry"
    if (
        node_id.startswith("test_policy_")
        or node_id.startswith("test_provider_")
        or node_id.startswith("test_redaction_")
    ):
        return "policy_provider"
    if node_id.startswith("test_simulate_") or node_id.startswith("test_recommendation_"):
        return "runtime_intelligence"
    if node_id.startswith("test_plugin_"):
        return "plugin_marketplace"
    return "unknown"


def run(output_dir: Path | str | None = None) -> Path:
    """Run the 17 probes and write the JSON artifact. Returns the output path."""
    output_dir = Path(output_dir or REPO_ROOT / "artifacts")
    output_dir.mkdir(parents=True, exist_ok=True)

    node_ids = _run_pytest_collect()
    _overall, statuses = _run_pytest(node_ids)

    probes = []
    reclassified: list[str] = []
    passed = failed = blocked = 0
    for nid in node_ids:
        status, detail = statuses.get(nid, ("blocked", "no result"))
        if status == "passed":
            passed += 1
        elif status == "failed":
            failed += 1
            reclassified.append(_capability_for(nid))
        else:
            blocked += 1
            reclassified.append(_capability_for(nid))
        probes.append(
            {
                "id": nid,
                "capability": _capability_for(nid),
                "name": nid.replace("test_", "").replace("_", " "),
                "status": status,
                "evidence_refs": [detail],
                "duration_ms": 0,
            }
        )

    payload = {
        "schema_version": "opencontext.done_in_v1_validation.v1",
        "validated_at": datetime.now(UTC).isoformat(),
        "probe_count": len(probes),
        "probes": probes,
        "summary": {
            "passed": passed,
            "failed": failed,
            "blocked": blocked,
            "reclassified_to_gap": reclassified,
        },
    }

    out_path = output_dir / ARTIFACT
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def main() -> int:
    out_path = run()
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())