"""Reusable black-box operations composed from CLI calls (no product imports)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests.acceptance.helpers.cli import run_json
from tests.acceptance.helpers.workspace import Workspace

#: Generous ceiling for full workflow runs (`run`, `run --workflow sdd`).
WORKFLOW_TIMEOUT = 300


def install_workspace(oc_bin: str, ws: Workspace) -> dict[str, object]:
    """`opencontext install <root> --yes --json` — the quick workspace setup."""
    proc, payload = run_json(oc_bin, ["install", ".", "--yes", "--json"], cwd=ws.root, env=ws.env)
    assert proc.returncode == 0, (
        f"INSTALL_UNINSTALL_CONTRACT: install failed ({proc.returncode}): {proc.stderr[:500]}"
    )
    return payload


def index_workspace(oc_bin: str, ws: Workspace) -> dict[str, object]:
    """`opencontext index . --json` — build the knowledge graph index."""
    proc, payload = run_json(oc_bin, ["index", ".", "--json"], cwd=ws.root, env=ws.env)
    assert proc.returncode == 0, (
        f"KG_CONTEXT_COMPRESSION_CONTRACT: index failed ({proc.returncode}): {proc.stderr[:500]}"
    )
    return payload


def run_project_pytest(ws: Workspace, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the fixture project's own pytest (external RED/GREEN evidence)."""
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args],
        cwd=str(ws.root),
        env={**ws.env, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def find_run_dir(ws: Workspace, run_id: str) -> Path:
    """Locate the persisted run directory for *run_id* under the workspace."""
    matches = [
        p
        for p in (ws.root / ".opencontext").rglob(run_id)
        if p.is_dir() and p.parent.name == "runs"
    ]
    assert matches, (
        f"RUN_STATE_CONTRACT: no persisted run directory for {run_id} under "
        f"{ws.root / '.opencontext'}"
    )
    return matches[0]
