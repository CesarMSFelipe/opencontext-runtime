"""E2E developer-journey bootstrap (B10 / AVH-017).

Copies the DoD golden fixture (``tests/golden/oc_flow_bugfix_python``) to an isolated
temp project with a temp ``$HOME``, so the journey drives the real CLI
(``install -> doctor --strict -> index``) without touching the developer's machine or
global config.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from opencontext_core.evaluation.golden import FIXTURE_DIRS, GOLDEN_ROOT

#: Repo root (…/tests/e2e/conftest.py -> parents[2]) and its two package source dirs.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE_DIRS = (
    _REPO_ROOT / "packages" / "opencontext_core",
    _REPO_ROOT / "packages" / "opencontext_cli",
)


def _subprocess_env(home: Path) -> dict[str, str]:
    """Build a subprocess env with a temp ``$HOME`` and an ABSOLUTE ``PYTHONPATH``.

    The e2e journey launches the CLI as a subprocess with ``cwd`` set to the copied
    fixture dir, so any RELATIVE ``PYTHONPATH`` entry inherited from the host (e.g.
    ``packages/opencontext_core`` when pytest was invoked from the repo root) would
    resolve against the fixture dir and fail to import ``opencontext_cli``. Resolve
    every existing entry to an absolute path and guarantee both package source dirs
    are present, so the subprocess imports the packages regardless of how (or from
    where) pytest was invoked. Resolve-only: no other ``os.environ`` key is stripped.
    """
    entries: list[str] = []
    for raw in os.environ.get("PYTHONPATH", "").split(os.pathsep):
        if raw:
            entries.append(str(Path(raw).resolve()))
    for pkg in _PACKAGE_DIRS:
        abs_pkg = str(pkg)
        if abs_pkg not in entries:
            entries.append(abs_pkg)
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home)}
    env["PYTHONPATH"] = os.pathsep.join(entries)
    return env


@pytest.fixture
def golden_root() -> Path:
    """The source-controlled DoD bugfix fixture directory."""
    return GOLDEN_ROOT / FIXTURE_DIRS["oc-flow-localized-bugfix"]


@pytest.fixture
def isolated_env(golden_root: Path, tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """An isolated copy of the golden project + an env with a temp ``$HOME``."""
    work = tmp_path / "repo"
    shutil.copytree(golden_root, work)
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    env = _subprocess_env(home)
    return work, env
