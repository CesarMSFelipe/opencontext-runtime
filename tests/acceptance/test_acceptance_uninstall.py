"""AC-022 / AC-023: uninstall — manifest-driven, verified, residue-free.

Contracts: INSTALL_UNINSTALL_CONTRACT.md, ACCEPTANCE_CONTRACT.md.
"""

from __future__ import annotations

import pytest

from tests.acceptance.helpers.cli import run_json
from tests.acceptance.helpers.ops import install_workspace

pytestmark = pytest.mark.acceptance

_UNINSTALL_WS = [
    "uninstall",
    "--scope",
    "workspace",
    "--purge",
    "--verify",
    "--yes",
    "--json",
]


@pytest.mark.smoke
def test_workspace_uninstall_purges_managed_state(oc_bin, workspace) -> None:
    """AC-022: `uninstall --scope workspace --purge --verify` removes managed workspace residue."""
    ws = workspace("py_bugfix_basic")
    install_workspace(oc_bin, ws)
    assert (ws.root / ".opencontext").is_dir()

    # Dry-run first: it must plan, and delete nothing (uninstall algorithm step 2).
    proc, plan = run_json(
        oc_bin, [*_UNINSTALL_WS, "--dry-run", "--root", "."], cwd=ws.root, env=ws.env
    )
    assert proc.returncode == 0, f"dry-run must exit 0: {proc.stderr[:400]}"
    assert plan.get("dry_run") is True
    assert (ws.root / ".opencontext").is_dir(), "dry-run must not delete anything"
    assert (ws.root / "opencontext.yaml").is_file(), "dry-run must not delete anything"

    # Real uninstall: the managed core state must actually be gone.
    proc, report = run_json(oc_bin, [*_UNINSTALL_WS, "--root", "."], cwd=ws.root, env=ws.env)
    assert report.get("dry_run") is False
    assert not (ws.root / ".opencontext").exists(), "purge must remove .opencontext/"
    assert not (ws.root / "opencontext.yaml").exists(), "purge must remove opencontext.yaml"
    # User content is never touched.
    assert (ws.root / "app.py").is_file()
    assert (ws.root / "tests" / "test_app.py").is_file()


@pytest.mark.xfail(
    reason="GAP-022: managed-residue verification fails — install writes .gitignore "
    "but workspace purge leaves it, so --verify reports residue and exits 1 "
    "instead of the contract's clean 0",
    strict=False,
)
def test_workspace_uninstall_verify_passes_clean(oc_bin, workspace) -> None:
    """AC-022: after a workspace purge, `--verify` finds no managed residue and exits 0."""
    ws = workspace("py_bugfix_basic")
    install_workspace(oc_bin, ws)
    proc, report = run_json(oc_bin, [*_UNINSTALL_WS, "--root", "."], cwd=ws.root, env=ws.env)
    verify = report.get("verify") or {}
    assert verify.get("passed") is True, (
        f"managed residue remained after purge: {verify.get('residue')}"
    )
    assert proc.returncode == 0, (
        f"clean uninstall must exit 0 (9 only when residue remains), got {proc.returncode}"
    )


@pytest.mark.xfail(
    reason="GAP-023: manifest-driven product uninstall missing — global purge "
    "reports state_cleared but leaves HOME state dirs and verify scans the "
    "workspace instead of the product manifest, so verification never passes",
    strict=False,
)
def test_product_uninstall_uses_manifest_and_cleans_home_state(oc_bin, workspace) -> None:
    """AC-023: product uninstall `--purge --verify` is manifest-driven and cleans the install."""
    ws = workspace("py_bugfix_basic")
    install_workspace(oc_bin, ws)
    home = ws.home
    assert any(home.rglob("*opencontext*")), "install must create managed HOME state"

    proc, report = run_json(
        oc_bin,
        [
            "uninstall",
            "--scope",
            "global",
            "--purge",
            "--verify",
            "--yes",
            "--json",
            "--root",
            ".",
        ],
        cwd=ws.root,
        env=ws.env,
    )
    verify = report.get("verify") or {}
    assert verify.get("passed") is True, (
        f"product uninstall verification failed, residue: {verify.get('residue')}"
    )
    assert proc.returncode == 0, f"clean product uninstall must exit 0, got {proc.returncode}"
    leftovers = [p for p in home.rglob("*opencontext*") if p.exists() and "backup" not in str(p)]
    assert not leftovers, f"managed HOME state left behind: {leftovers[:10]}"
