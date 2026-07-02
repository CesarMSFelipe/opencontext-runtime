"""Integration gate: fresh install must not emit a legacy-state warning.

C3 (product-closure-r13): agent_installer.py:48-49 creates .opencontext/agent-configs/
eagerly in __init__. detect_legacy (runtime/__init__.py:322) finds .opencontext and
emits a spurious "legacy local state detected" warning. The fix is to stop the eager
mkdir and move it inside install().

This test uses an isolated tmp HOME so it does not touch the developer's real config.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest


@pytest.fixture()
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Return a fresh tmp HOME with no pre-existing OpenContext state."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


def test_fresh_install_no_legacy_warning(
    isolated_home: Path, tmp_path: Path
) -> None:
    """AgentInstaller.__init__ must not create .opencontext in the project root.

    Strict TDD: this test FAILS until agent_installer.py stops the eager mkdir
    at __init__ time. After C3, .opencontext is NOT created by the constructor
    and the legacy-state warning is never emitted.
    """
    project = tmp_path / "project"
    project.mkdir()

    # Capture any warnings emitted during AgentInstaller construction.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        # Import inside the with-block so the module-level code is covered too.
        from opencontext_core.agent_installer import AgentInstaller

        AgentInstaller(project_root=project)

    # Primary gate: .opencontext must NOT be created by __init__.
    oc_dir = project / ".opencontext"
    assert not oc_dir.exists(), (
        "AgentInstaller.__init__ must not eagerly create .opencontext; "
        "doing so causes a spurious 'legacy local state detected' warning. "
        "Move the mkdir inside install()."
    )

    # Secondary gate: no legacy-state warning was emitted.
    legacy_msgs = [
        str(w.message) for w in caught
        if "legacy" in str(w.message).lower() and "local state" in str(w.message).lower()
    ]
    assert not legacy_msgs, (
        f"Spurious legacy-state warning(s) on fresh install: {legacy_msgs}"
    )


def test_install_creates_storage_dir_lazily(
    isolated_home: Path, tmp_path: Path
) -> None:
    """agent-configs dir is created inside install(), not in __init__.

    After C3, AgentInstaller.__init__ does NOT touch the filesystem at all
    for the storage dir. The directory is only created when install() writes
    the first actual agent config file.
    """
    project = tmp_path / "lazy_project"
    project.mkdir()

    from opencontext_core.agent_installer import AgentInstaller

    installer = AgentInstaller(project_root=project)

    # After __init__ only: storage_dir attribute is set but dir must not exist yet.
    assert not installer.storage_dir.exists(), (
        f"storage_dir {installer.storage_dir} must not exist before install() is called"
    )
