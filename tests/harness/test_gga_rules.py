"""GGA rules phase scans the real written source, not the manifest JSON."""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.harness.config import PhaseConfig
from opencontext_core.harness.models import BudgetMode, GateStatus
from opencontext_core.harness.phases import GGARulesPhase
from opencontext_core.harness.runner import HarnessRunner


def test_gga_flags_forbidden_pattern_in_written_source(tmp_path: Path) -> None:
    """H5: GGA scanned the apply-manifest.json (suffix skipped) so rules passed
    vacuously. It must scan the source the apply manifest says was written."""
    (tmp_path / ".opencontext").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".opencontext" / "rules.yaml").write_text(
        "forbidden_patterns:\n  - TODO_FIXME_BANNED\n", encoding="utf-8"
    )

    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("x = 1  # TODO_FIXME_BANNED\n", encoding="utf-8")

    runner = HarnessRunner(root=tmp_path)
    state = runner.create_run("sdd", "gga task")
    run_dir = tmp_path / ".opencontext" / "runs" / state.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / "apply-manifest.json"
    manifest_path.write_text(
        json.dumps({"status": "applied", "changes": [{"path": str(src)}]}),
        encoding="utf-8",
    )

    from opencontext_core.harness.models import HarnessArtifact

    state.artifacts.append(
        HarnessArtifact(id="m", phase="apply", path=str(manifest_path), kind="apply-manifest")
    )

    result = GGARulesPhase(PhaseConfig(budget_tokens=2000), BudgetMode.OFF).run(state)

    assert result.status == GateStatus.FAILED
    report = json.loads((run_dir / "gga.json").read_text(encoding="utf-8"))
    assert report["blocker_count"] == 1
    assert any("TODO_FIXME_BANNED" in v["detail"] for v in report["violations"])
