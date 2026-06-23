"""Smoke test for `opencontext benchmark head2head` — the first-class head-to-head CLI."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_head2head_cli_json_exit_zero(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    (repo / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "pkg" / "core.py").write_text(
        'def transform(value):\n    """Transform a value."""\n    return value * 2\n',
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            "opencontext",
            "benchmark",
            "head2head",
            "--repos",
            str(repo),
            "--query",
            "add validation to transform",
            "--target",
            "transform",
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    # stdout is the JSON payload (warnings go to stderr); parse from the first '['.
    start = proc.stdout.find("[")
    data = json.loads(proc.stdout[start:])
    assert data, "no reports emitted"
    report = data[0]
    arms = {a["arm"] for a in report["arms"]}
    assert "OC-SURGICAL" in arms
    assert "SKILL-GREP" in arms
    assert "semantic_layer" in report
