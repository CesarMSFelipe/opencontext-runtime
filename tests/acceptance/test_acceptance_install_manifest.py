"""INST-001 / INST-002 / INST-003: install manifests through the real CLI.

Contracts: INSTALL_UNINSTALL_CONTRACT.md (per-scope manifest schemas, reinstall
idempotence). These scenarios pin the WIRING: the unit layer already pins the
manifest field construction, but only a real `install` run proves the v2
registration is actually reached (finalize is wrapped in try/except and the v1
ownership writers also create oc-manifest.json, so a wiring break would
otherwise stay green).
"""

from __future__ import annotations

import json

import pytest

from tests.acceptance.helpers.cli import run_json
from tests.acceptance.helpers.ops import install_workspace
from tests.acceptance.helpers.workspace import make_workspace

# All tests here share the module-scoped `manifest_run` fixture, whose real
# `install` run dominates wall time (>=25s of setup). Mark the whole module slow
# so `-m "not slow"` actually skips that fixture cost, not just one test.
pytestmark = [pytest.mark.acceptance, pytest.mark.slow]


@pytest.fixture(scope="module")
def manifest_run(oc_bin, tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    """One workspace installed twice + product-scope probes, shared by the pins."""
    ws = make_workspace(tmp_path_factory.mktemp("inst-manifest"), "py_bugfix_basic")
    manifest_path = ws.root / ".opencontext" / "oc-manifest.json"

    install_workspace(oc_bin, ws)
    first = json.loads(manifest_path.read_text(encoding="utf-8"))

    _, product_status_after_install = run_json(
        oc_bin, ["product", "status", "--json"], cwd=ws.root, env=ws.env
    )
    _, product_install = run_json(oc_bin, ["product", "install", "--json"], cwd=ws.root, env=ws.env)
    _, product_status_after_register = run_json(
        oc_bin, ["product", "status", "--json"], cwd=ws.root, env=ws.env
    )

    install_workspace(oc_bin, ws)  # reinstall over the existing install
    second = json.loads(manifest_path.read_text(encoding="utf-8"))

    return {
        "first": first,
        "second": second,
        "product_status_after_install": product_status_after_install,
        "product_install": product_install,
        "product_status_after_register": product_status_after_register,
    }


def test_workspace_install_registers_v2_manifest(manifest_run) -> None:
    """INST-002: a real workspace `install` registers a schema_version-2 manifest
    with non-empty created_paths (not just the v1 ownership stub)."""
    manifest = manifest_run["first"]
    assert manifest.get("schema_version") == 2, (
        "workspace install must reach the v2 manifest registration, "
        f"got: {json.dumps(manifest)[:400]}"
    )
    created = manifest.get("created_paths")
    assert isinstance(created, list) and created, "v2 manifest must record created_paths"
    assert "opencontext.yaml" in created
    assert manifest.get("install_method")
    assert isinstance(manifest.get("state_paths"), list) and manifest["state_paths"]


def test_reinstall_through_real_cli_is_idempotent(manifest_run) -> None:
    """INST-003: a second real `install` over the same workspace merges the
    manifest — same created_paths, no duplicates, nothing dropped or replaced
    by a near-empty diff."""
    first, second = manifest_run["first"], manifest_run["second"]
    assert second.get("schema_version") == 2
    assert set(second["created_paths"]) == set(first["created_paths"]), (
        "reinstall must merge created_paths, not replace them with the second run's diff"
    )
    assert len(second["created_paths"]) == len(set(second["created_paths"])), (
        "reinstall must not duplicate created_paths entries"
    )
    assert second.get("install_id") == first.get("install_id"), (
        "reinstall must keep the workspace install_id stable"
    )


def test_full_install_registers_product_manifest(manifest_run) -> None:
    """INST-001: a full `install` (global step included) registers the
    product-scope manifest under HOME, so `product status --json` reports it."""
    status = manifest_run["product_status_after_install"]
    assert status.get("manifest_present") is True, (
        "product status must see the HOME manifest right after a full install"
    )


def test_product_install_registers_manifest(manifest_run) -> None:
    """INST-001: `product install` registers/refreshes the product manifest and
    `product status --json` surfaces the contract fields."""
    assert manifest_run["product_install"].get("manifest_registered") is True
    status = manifest_run["product_status_after_register"]
    assert status.get("manifest_present") is True
    manifest = status.get("manifest") or {}
    for key in (
        "schema_version",
        "install_id",
        "install_method",
        "product_version",
        "created_paths",
        "shell_profile_blocks",
        "symlinks",
        "env_vars",
        "state_paths",
    ):
        assert key in manifest, f"product manifest is missing contract field '{key}'"
