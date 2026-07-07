"""AC-003 / AC-004: workspace setup and status detection.

Contracts: INSTALL_UNINSTALL_CONTRACT.md (workspace scope), CLI_CONTRACT.md,
RUN_STATE_CONTRACT.md (status ↔ exit code mapping).
"""

from __future__ import annotations

import pytest

from tests.acceptance.helpers.cli import run, run_json
from tests.acceptance.helpers.ops import install_workspace

pytestmark = pytest.mark.acceptance


@pytest.mark.smoke
def test_install_creates_expected_workspace_files(oc_bin, workspace) -> None:
    """AC-003: workspace `install` creates the expected files."""
    ws = workspace("py_bugfix_basic")
    payload = install_workspace(oc_bin, ws)
    assert payload.get("status") == "ok", payload
    assert payload.get("error") is None

    assert (ws.root / "opencontext.yaml").is_file(), "install must write opencontext.yaml"
    assert (ws.root / ".opencontext").is_dir(), "install must create .opencontext/"
    manifest = ws.root / ".opencontext" / "oc-manifest.json"
    assert manifest.is_file(), "install must write the workspace manifest (oc-manifest.json)"
    assert (ws.root / "AGENTS.md").is_file(), "install must write the agent instructions file"


def test_init_non_interactive_creates_workspace(oc_bin, workspace) -> None:
    """AC-003: `init --non-interactive` also produces a usable workspace config."""
    ws = workspace("py_bugfix_basic")
    proc = run(oc_bin, ["init", "--non-interactive"], cwd=ws.root, env=ws.env)
    assert proc.returncode == 0, proc.stderr[:500]
    assert (ws.root / "opencontext.yaml").is_file()
    assert (ws.root / ".opencontext").is_dir()


@pytest.mark.smoke
def test_status_json_detects_valid_workspace(oc_bin, workspace) -> None:
    """AC-004: `status --json` detects a valid workspace (ready, exit 0)."""
    ws = workspace("py_bugfix_basic")
    install_workspace(oc_bin, ws)
    proc, payload = run_json(oc_bin, ["status", "--json", "."], cwd=ws.root, env=ws.env)
    assert proc.returncode == 0, proc.stderr[:500]
    assert payload.get("status") == "ready", payload
    assert payload.get("canonical_status") == "passed", payload
    assert payload.get("exit_code") == 0, payload
    assert payload.get("config", {}).get("exists") is True
    assert payload.get("workspace", {}).get("exists") is True


def test_status_json_reports_missing_workspace_as_needs_configuration(oc_bin, workspace) -> None:
    """AC-004: `status --json` on a bare directory reports needs_configuration, exit 3."""
    ws = workspace()  # empty dir: no config, no workspace
    proc, payload = run_json(oc_bin, ["status", "--json", "."], cwd=ws.root, env=ws.env)
    assert proc.returncode == 3, (
        f"RUN_STATE_CONTRACT: needs_configuration must exit 3, got {proc.returncode}"
    )
    assert payload.get("canonical_status") == "needs_configuration", payload
    assert payload.get("exit_code") == 3, "reported exit_code must match the actual exit code"
    assert payload.get("config", {}).get("exists") is False
