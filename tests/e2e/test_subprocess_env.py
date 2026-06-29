"""Unit guard for the B7 / PROD-003 subprocess-env builder in ``conftest.py``.

The e2e journey launches the real CLI as a subprocess with ``cwd`` set to the copied
fixture dir. A RELATIVE ``PYTHONPATH`` entry inherited from the host (e.g.
``packages/opencontext_core`` when pytest was invoked from the repo root) would
otherwise resolve against the fixture dir and break ``import opencontext_cli``. This
test pins the contract that every PYTHONPATH entry handed to the subprocess is
ABSOLUTE and that both package source dirs are present — independent of the full DoD
journey, so the PYTHONPATH fix stays green even when other journey steps regress.
"""

from __future__ import annotations

import os
from pathlib import Path

from conftest import _PACKAGE_DIRS, _subprocess_env  # type: ignore[import-not-found]


def test_subprocess_env_resolves_relative_pythonpath_to_absolute(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # A host PYTHONPATH made of RELATIVE entries (the fragility B7 fixes).
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(["packages/opencontext_core", "."]))
    env = _subprocess_env(tmp_path / "home")

    entries = env["PYTHONPATH"].split(os.pathsep)
    # Every entry is absolute — none would mis-resolve against a subprocess cwd.
    assert all(Path(e).is_absolute() for e in entries), entries
    # Resolve-only: no other os.environ key is stripped (PATH still present).
    assert env.get("PATH") == os.environ.get("PATH")
    # HOME/USERPROFILE are redirected to the isolated temp home.
    assert env["HOME"] == str(tmp_path / "home")
    assert env["USERPROFILE"] == str(tmp_path / "home")


def test_subprocess_env_guarantees_both_package_dirs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("PYTHONPATH", raising=False)
    env = _subprocess_env(tmp_path / "home")
    entries = env["PYTHONPATH"].split(os.pathsep)
    # Both repo package source dirs are present so the subprocess can import the
    # packages even with no inherited PYTHONPATH and no site install.
    for pkg in _PACKAGE_DIRS:
        assert str(pkg) in entries, (pkg, entries)
        assert pkg.is_dir(), pkg
