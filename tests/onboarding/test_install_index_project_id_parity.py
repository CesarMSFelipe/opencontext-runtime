"""Regression: install and index must derive the SAME project_id for a root.

Bug (real E2E): ``opencontext install <root>`` and ``opencontext index <root>``
computed DIFFERENT ``project_id`` hashes for the same project, creating two
separate ``~/.local/state/opencontext/projects/<hash>/`` store dirs (observed
``3663240fbded`` vs ``f2fd1838d837``). The divergence was cwd-dependent:

* ``index`` anchors ``project_index.root`` to ``Path(root).resolve()`` (CLI
  ``_runtime_for_root``), so its storage hashes the *resolved project root*.
* ``install`` (``OnboardingService.run``) built the indexing runtime with only a
  ``config_path``; the written ``opencontext.yaml`` keeps ``project_index.root=".""``,
  so the runtime resolved ``"."`` against the *current cwd* — a different hash
  whenever install ran from a directory other than the project root. Install's
  KG/memory then landed in an orphaned, cwd-keyed dir.

These tests pin the invariant at the storage boundary: onboarding, run from a
foreign cwd, must create its state under ``project_id(root.resolve())`` — the
exact hash the index runtime uses — for absolute, relative, and symlinked roots.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from opencontext_core.onboarding.service import OnboardingOptions, OnboardingService
from opencontext_core.paths import project_id


def _make_project(root: Path) -> None:
    """Create a minimal indexable project at *root*."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "app.py").write_text('def hello():\n    return "hi"\n', encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "proj"\nversion = "0.0.0"\n', encoding="utf-8"
    )


def _project_hash_dirs(xdg_state_tmp: Path) -> list[str]:
    """Return the project hash dir names created under the isolated XDG state."""
    projects = xdg_state_tmp / "opencontext" / "projects"
    if not projects.is_dir():
        return []
    return sorted(p.name for p in projects.iterdir() if p.is_dir())


def _run_install_from_cwd(root: Path, cwd: Path) -> None:
    """Run OnboardingService.run(root) with the process cwd set to *cwd*.

    Simulates ``opencontext install <root>`` invoked from a directory that is
    NOT the project root — the exact condition under which the split-state bug
    manifested.
    """
    prev = Path.cwd()
    os.chdir(cwd)
    try:
        # force_agent_files keeps the run self-contained; active_clients is left to
        # the isolated-home default (opencode) so no real agent config is touched.
        OnboardingService().run(OnboardingOptions(root=root, force_agent_files=True))
    finally:
        os.chdir(prev)


def test_install_uses_resolved_root_project_id_not_cwd(tmp_path: Path, xdg_state_tmp: Path) -> None:
    """Install run from a foreign cwd stores under project_id(resolved root).

    This is the core regression: previously install hashed the cwd, producing a
    dir that ``index`` (which hashes the resolved root) never reads.
    """
    root = tmp_path / "proj"
    _make_project(root)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    _run_install_from_cwd(root, cwd=elsewhere)

    expected = project_id(root.resolve())
    dirs = _project_hash_dirs(xdg_state_tmp)
    # Exactly one store dir, and it is keyed to the resolved project root — not to
    # ``elsewhere`` (the cwd), which is what the buggy code hashed.
    assert dirs == [expected], (
        f"expected a single store dir {expected!r} (project_id of the resolved "
        f"root); got {dirs!r}. A cwd-keyed dir here means install/index split-state."
    )
    assert project_id(elsewhere.resolve()) not in dirs


def test_install_and_index_runtime_agree_on_project_id(tmp_path: Path, xdg_state_tmp: Path) -> None:
    """Install's storage dir equals the one the index runtime resolves.

    ``index`` builds its runtime with ``project_index.root`` anchored to
    ``Path(root).resolve()`` (CLI ``_runtime_for_root``). This test reproduces
    that derivation and asserts install landed in the same hash dir — from a
    foreign cwd, so a cwd-relative regression would fail here.
    """
    from opencontext_core.config import load_config_or_defaults
    from opencontext_core.runtime import OpenContextRuntime

    root = tmp_path / "proj"
    _make_project(root)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    _run_install_from_cwd(root, cwd=elsewhere)
    install_dirs = _project_hash_dirs(xdg_state_tmp)

    # Build the index-side runtime exactly like the CLI's _runtime_for_root: load
    # the project's written config, then anchor project_index.root to the resolved
    # root. Do it from the foreign cwd to exercise the cwd-independence contract.
    prev = Path.cwd()
    os.chdir(elsewhere)
    try:
        cfg = load_config_or_defaults(root / "opencontext.yaml")
        cfg = cfg.model_copy(
            update={
                "project_index": cfg.project_index.model_copy(update={"root": str(root.resolve())})
            }
        )
        index_runtime = OpenContextRuntime(config=cfg)
        index_storage = index_runtime.storage_path
    finally:
        os.chdir(prev)

    assert index_storage.name == project_id(root.resolve())
    # Install must have written to the SAME hash dir the index runtime resolves.
    assert index_storage.name in install_dirs
    assert install_dirs == [project_id(root.resolve())]


def test_install_project_id_relative_vs_absolute_root(tmp_path: Path, xdg_state_tmp: Path) -> None:
    """A relative and an absolute spelling of the same root share one project_id.

    ``project_id`` resolves the root, so a relative root (resolved against cwd)
    and its absolute form must hash identically — and install must honor that.
    """
    root = tmp_path / "proj"
    _make_project(root)

    # Relative root: run install from tmp_path with root spelled as "proj".
    prev = Path.cwd()
    os.chdir(tmp_path)
    try:
        OnboardingService().run(OnboardingOptions(root=Path("proj"), force_agent_files=True))
    finally:
        os.chdir(prev)

    expected = project_id(root.resolve())
    # project_id parity between the two spellings (formula-level guarantee).
    assert project_id(Path(tmp_path / "proj")) == project_id(root.resolve())
    # Install (given the relative root) stored under that single resolved hash.
    assert _project_hash_dirs(xdg_state_tmp) == [expected]


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX symlink semantics; Windows symlinks need privilege"
)
def test_install_project_id_symlinked_root(tmp_path: Path, xdg_state_tmp: Path) -> None:
    """A symlinked path to the project resolves to the real root's project_id.

    ``Path.resolve()`` follows symlinks, so installing via a symlink must store
    under the real directory's hash — not a symlink-path hash — keeping it aligned
    with an index run that used the real path.
    """
    real = tmp_path / "real_proj"
    _make_project(real)
    link = tmp_path / "link_proj"
    link.symlink_to(real, target_is_directory=True)

    # Sanity: the symlink and the real dir resolve to the same project_id.
    assert project_id(link) == project_id(real)

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    _run_install_from_cwd(link, cwd=elsewhere)

    expected = project_id(real.resolve())
    assert _project_hash_dirs(xdg_state_tmp) == [expected]
