"""GOLD-001..GOLD-014 — golden contracts for the public JSON surface (§19.2).

Level-B golden contract tests: prove the public JSON outputs the plan names
(version / status / doctor / run passed / run failed / memory search /
kg search / sdd cycle / pack / install / uninstall / config) do not change
accidentally. Schema + critical fields only — never giant snapshots (§19.2).
Black-box: every test drives the real binary in an isolated workspace.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import Any

import pytest
from tests.acceptance.helpers.workspace import Workspace, make_workspace

_SEMVER = re.compile(r"^\d+\.\d+\.\d+")


@pytest.fixture(scope="module")
def oc_bin() -> str:
    resolved = shutil.which("opencontext")
    if not resolved:
        pytest.skip("no opencontext binary on PATH: activate a venv with opencontext installed")
    return resolved


def _run_json(oc_bin: str, ws: Workspace, args: list[str], *, expect_exit: int = 0) -> Any:
    proc = subprocess.run(
        [oc_bin, *args],
        cwd=ws.root,
        env=ws.env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == expect_exit, (
        f"{args}: exit {proc.returncode} != {expect_exit}: {proc.stderr[:400]}"
    )
    return json.loads(proc.stdout)


@pytest.fixture(scope="module")
def ws(oc_bin: str, tmp_path_factory: pytest.TempPathFactory) -> Workspace:
    """A tiny installed+indexed workspace shared by the read-only contracts."""
    workspace = make_workspace(tmp_path_factory.mktemp("golden-json"))
    (workspace.root / "mod.py").write_text(
        "def alpha():\n    return beta()\n\n\ndef beta():\n    return 1\n", encoding="utf-8"
    )
    for argv in (["install", ".", "--yes", "--json"], ["index", ".", "--json"]):
        _run_json(oc_bin, workspace, argv)
    return workspace


@pytest.fixture(scope="module")
def passed_run(oc_bin: str, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """One PASSED OC Flow run (test_stub executor over py_bugfix_basic)."""
    workspace = make_workspace(tmp_path_factory.mktemp("golden-run"), "py_bugfix_basic")
    from tests.acceptance.helpers.workspace import CORRECT_ADD_EDITS

    workspace.write_stub_provider(CORRECT_ADD_EDITS)
    for argv in (["install", ".", "--yes", "--json"], ["index", ".", "--json"]):
        _run_json(oc_bin, workspace, argv)
    return _run_json(oc_bin, workspace, ["run", "Fix failing test in app.py", "--json"])


def test_version_json_contract(oc_bin: str, ws: Workspace) -> None:
    """GOLD-001: `version --json` reports a real semver and every schema field
    (and can never regress to 0.0.0 — the §19.5 regression example)."""
    payload = _run_json(oc_bin, ws, ["version", "--json"])
    assert _SEMVER.match(str(payload["opencontext"])), payload
    assert payload["opencontext"] != "0.0.0"
    for key in (
        "config_schema",
        "kg_schema",
        "memory_schema",
        "plugin_api",
        "runtime_api",
        "workflow_schema",
    ):
        assert payload.get(key), f"version schema field missing/empty: {key}"


def test_doctor_json_contract(oc_bin: str, ws: Workspace) -> None:
    """GOLD-002: `doctor --json` reports named checks with pass/fail counts."""
    payload = _run_json(oc_bin, ws, ["doctor", "--json"])
    assert isinstance(payload["checks"], list) and payload["checks"]
    for check in payload["checks"]:
        assert check.get("name"), check
        assert isinstance(check.get("ok"), bool), check
    assert isinstance(payload["passed"], int)
    assert isinstance(payload["failed"], int)
    assert payload.get("scope")


def test_status_json_contract(oc_bin: str, ws: Workspace) -> None:
    """GOLD-003: `status --json` carries schema, project, status and the
    canonical-status/exit-code truth pair."""
    payload = _run_json(oc_bin, ws, ["status", "--json"])
    for key in ("schema", "project", "status", "canonical_status", "exit_code", "workspace"):
        assert key in payload, f"status field missing: {key}"


def test_install_json_contract(oc_bin: str, ws: Workspace) -> None:
    """GOLD-004: `install --json` (idempotent re-run) reports schema + status."""
    payload = _run_json(oc_bin, ws, ["install", ".", "--yes", "--json"])
    assert payload.get("schema")
    assert payload.get("status")


def test_config_show_json_contract(oc_bin: str, ws: Workspace) -> None:
    """GOLD-005: `config show --json` reports schema, security mode, features."""
    payload = _run_json(oc_bin, ws, ["config", "show", "--json"])
    for key in ("schema", "security_mode", "features", "project"):
        assert key in payload, f"config show field missing: {key}"


def test_kg_search_json_contract(oc_bin: str, ws: Workspace) -> None:
    """GOLD-006: `knowledge-graph search --json` returns locatable symbols."""
    results = _run_json(oc_bin, ws, ["knowledge-graph", "search", "alpha", "--json"])
    assert isinstance(results, list) and results
    for row in results:
        for key in ("name", "kind", "file_path", "line"):
            assert key in row, f"kg search row missing {key}: {row}"


def test_kg_impact_json_contract(oc_bin: str, ws: Workspace) -> None:
    """GOLD-007: `knowledge-graph impact --json` returns affected symbols with
    their location and traversal depth."""
    results = _run_json(oc_bin, ws, ["knowledge-graph", "impact", "beta", "--json"])
    assert isinstance(results, list) and results
    for row in results:
        for key in ("name", "file_path", "depth"):
            assert key in row, f"impact row missing {key}: {row}"


def test_pack_json_contract(oc_bin: str, ws: Workspace) -> None:
    """GOLD-008: `pack --json` reports the budget, real usage, traceable items
    and the mandatory metrics block."""
    payload = _run_json(
        oc_bin, ws, ["pack", ".", "--query", "fix alpha", "--json", "--max-tokens", "400"]
    )
    assert payload["available_tokens"] == 400
    assert isinstance(payload["used_tokens"], int)
    for item in payload["included"]:
        for key in ("id", "source", "tokens"):
            assert key in item, f"pack item missing {key}"
    context = payload.get("context") or {}
    for key in ("kg_nodes_used", "memory_hits", "protected_spans", "protected_spans_kept"):
        assert key in context, f"pack metrics missing {key}"


def test_memory_save_json_contract(oc_bin: str, ws: Workspace) -> None:
    """GOLD-009: `memory v2 save` returns a dedup-aware receipt."""
    payload = _run_json(
        oc_bin,
        ws,
        [
            "memory",
            "v2",
            "save",
            "--title",
            "Test runner is pytest",
            "--content",
            "verify with pytest -q",
            "--type",
            "project_context",
        ],
    )
    receipt = payload["receipt"]
    for key in ("id", "title", "type", "project"):
        assert key in receipt, f"memory save receipt missing {key}"
    assert isinstance(payload["judgment_required"], bool)
    assert isinstance(payload["candidates"], list)


def test_memory_search_json_contract(oc_bin: str, ws: Workspace) -> None:
    """GOLD-010: `memory v2 search` returns ranked hits with lifecycle state."""
    # Self-sufficient seed (dedup-safe): never depends on another test's order.
    _run_json(
        oc_bin,
        ws,
        [
            "memory",
            "v2",
            "save",
            "--title",
            "Search seed: pytest verifies changes",
            "--content",
            "search seed observation about pytest",
            "--type",
            "project_context",
        ],
    )
    hits = _run_json(oc_bin, ws, ["memory", "v2", "search", "--query", "pytest"])
    assert isinstance(hits, list) and hits, "a saved observation must be findable"
    for hit in hits:
        for key in ("id", "title", "content", "type", "lifecycle_state"):
            assert key in hit, f"memory search hit missing {key}: {sorted(hit)}"


@pytest.mark.slow
def test_run_passed_json_contract(passed_run: dict[str, Any]) -> None:
    """GOLD-011: a PASSED `run --json` summary carries the verification truth
    fields — `passed` may only appear with real verification evidence."""
    assert passed_run["status"] == "passed"
    assert passed_run["exit_code"] == 0
    for key in (
        "run_id",
        "workflow",
        "canonical_status",
        "verification_outcome",
        "mutation_required",
        "tdd",
    ):
        assert key in passed_run, f"run summary missing {key}"


def test_run_needs_executor_json_contract(oc_bin: str, ws: Workspace) -> None:
    """GOLD-012: `run --json` without an executor reports needs_executor with
    exit code 5 — it never fakes success (§19.5 regression example)."""
    payload = _run_json(oc_bin, ws, ["run", "improve alpha", "--json"], expect_exit=5)
    assert payload["status"] == "needs_executor"
    assert payload["exit_code"] == 5
    assert payload["status"] != "passed"


def test_sdd_status_json_contract(oc_bin: str, ws: Workspace) -> None:
    """GOLD-013: `sdd status --json` reports the cycle state machine fields."""
    payload = _run_json(oc_bin, ws, ["sdd", "status", "--json"])
    for key in (
        "changeName",
        "currentPhase",
        "cycleState",
        "gates",
        "nextRecommended",
        "artifactStore",
        "blockedReasons",
    ):
        assert key in payload, f"sdd status field missing: {key}"


def test_uninstall_dry_run_json_contract(oc_bin: str, ws: Workspace) -> None:
    """GOLD-014: `uninstall --dry-run --json` reports scope, plan and status
    without mutating anything."""
    payload = _run_json(
        oc_bin,
        ws,
        ["uninstall", "--scope", "workspace", "--dry-run", "--yes", "--json", "--root", "."],
    )
    assert payload["dry_run"] is True
    assert payload["scope"] == "workspace"
    assert "status" in payload
    assert "results" in payload
    # Dry run must leave the workspace installed (config still present).
    assert (ws.root / ".opencontext").exists() or (ws.root / "opencontext.yaml").exists()
