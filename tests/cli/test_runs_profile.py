"""R3: `opencontext runs show <run_id> --profile` surfaces per-component timings.

Failing tests:
- With a seeded trace.json, --profile prints a timing table.
- Without a trace.json, --profile prints honest "no trace recorded", exit 0.
- Existing `runs show` (without --profile) is unaffected.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from opencontext_cli.commands.run_cmd import handle_run_inspect


def _make_run(root: Path, run_id: str, *, status: str = "passed") -> Path:
    run_dir = root / ".opencontext" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "workflow": "oc-flow",
                "task": "fix bug",
                "status": status,
                "created_at": "2026-06-24T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    return run_dir


def _seed_trace(run_dir: Path, timings: dict[str, float] | None = None) -> None:
    """Write a minimal trace.json with the given per-component timings."""
    data = {
        "run_id": run_dir.name,
        "timings_ms": timings or {"context": 120.0, "mutation": 80.0, "inspect": 40.0},
    }
    (run_dir / "trace.json").write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# RED tests — will fail until implementation is added
# ---------------------------------------------------------------------------


def test_profile_flag_prints_timing_table(tmp_path: Path, capsys) -> None:
    """runs show <id> --profile with a trace must print per-component timings."""
    run_dir = _make_run(tmp_path, "oc-abc")
    _seed_trace(run_dir)

    handle_run_inspect(
        SimpleNamespace(
            runs_action="show",
            run_id="oc-abc",
            root=str(tmp_path),
            json=False,
            profile=True,
        )
    )

    out = capsys.readouterr().out
    # Must include at least one component name from the seeded trace
    assert "context" in out or "mutation" in out, (
        f"Expected component timings in profile output.\nGot:\n{out}"
    )


def test_profile_flag_no_trace_honest_message(tmp_path: Path, capsys) -> None:
    """runs show <id> --profile with no trace.json must print honest message, exit 0."""
    _make_run(tmp_path, "oc-notrace")
    # No trace.json seeded

    handle_run_inspect(
        SimpleNamespace(
            runs_action="show",
            run_id="oc-notrace",
            root=str(tmp_path),
            json=False,
            profile=True,
        )
    )

    out = capsys.readouterr().out
    assert "no trace" in out.lower(), (
        f"Expected 'no trace' honest message in output.\nGot:\n{out}"
    )


def test_show_without_profile_unaffected(tmp_path: Path, capsys) -> None:
    """Existing runs show without --profile must still work as before."""
    _make_run(tmp_path, "oc-def")
    (tmp_path / ".opencontext" / "runs" / "oc-def" / "gates.json").write_text(
        json.dumps({"gates": []}), encoding="utf-8"
    )
    (tmp_path / ".opencontext" / "runs" / "oc-def" / "artifacts.json").write_text(
        json.dumps({"artifacts": []}), encoding="utf-8"
    )

    handle_run_inspect(
        SimpleNamespace(
            runs_action="show",
            run_id="oc-def",
            root=str(tmp_path),
            json=True,
            profile=False,
        )
    )

    out = json.loads(capsys.readouterr().out)
    assert out["run_id"] == "oc-def"
