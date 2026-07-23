"""Shared test safeguards.

Some tests configure agents or run installers that write instruction files
(AGENTS.md, CLAUDE.md, ...) relative to the working directory. This guard ensures
no test can leave a write in the repository's own root files: it snapshots them
around every test and restores any that changed.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

# --------------------------------------------------------------------------- #
# Parallel (pytest-xdist) worker isolation
# --------------------------------------------------------------------------- #
#
# The suite resolves user-level state from HOME: ``~/.opencontext`` (daemon,
# config, storage) and ``~/.engram`` (memory SQLite; see engram_bridge
# ``_engram_db_path`` -> ``Path.home()/.engram/engram.db``). A few tests also
# ASSERT the real ``~/.opencontext`` is byte-unchanged around a run (e.g.
# ``tests/core/test_ci_quality_checks.py``). Single-process, that assertion
# holds because those tests are tmp_path-isolated. Under ``-n auto`` it does
# NOT: a sibling test on another worker legitimately writes to the shared real
# ``~/.opencontext`` mid-run, so the snapshot changes and the guard fails.
#
# Fix it once, centrally: give every xdist worker its own HOME under a per-worker
# temp directory. Everything the product reads (``~/.opencontext``, ``~/.engram``,
# the XDG defaults) derives from ``Path.home()``, so redirecting HOME isolates all
# of it. Nothing then touches the real user dirs, so those guards stay stable and
# cross-worker pollution is impossible.
#
# Behave EXACTLY as today when not run under a real xdist worker (plain
# ``pytest``, ``pytest one_file.py``, or the xdist controller whose worker_id is
# "master"): no env is rewritten, so serial output is byte-identical. PATH is
# never modified, so subprocess tool discovery (ruff/mypy/...) is unaffected.


def _xdist_worker_id() -> str | None:
    """Return the current xdist worker id, or ``None`` when not parallel.

    ``PYTEST_XDIST_WORKER`` is set to ``gw0``, ``gw1``, ... on real workers and
    is absent (or "master" on the controller) otherwise.
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if not worker or worker == "master":
        return None
    return worker


@pytest.fixture(scope="session")
def _worker_home() -> Path | None:
    """Per-worker HOME directory (created once per worker), or ``None`` if serial.

    Session-scoped so each worker pays a single mkdir, not one per test. The
    directory lives under the OS temp root and is intentionally left in place;
    pytest/OS temp cleanup reclaims it, and keeping it avoids racing teardown
    against still-running subprocesses that may hold handles under HOME.
    """
    worker = _xdist_worker_id()
    if worker is None:
        return None
    base = Path(tempfile.gettempdir()) / "oc-xdist-home" / worker
    base.mkdir(parents=True, exist_ok=True)
    return base


@pytest.fixture(autouse=True)
def _isolate_worker_home(
    request: pytest.FixtureRequest,
    _worker_home: Path | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redirect HOME and derived user-state dirs to a per-worker temp dir.

    No-op unless running under a real xdist worker, so single-process behaviour
    is unchanged. ``monkeypatch`` auto-reverts after each test.

    A small set of tests are real-environment probes: they assert on the
    developer/CI machine's ACTUAL OpenContext health or acceptance verdict
    (``run_all_checks()``, ``AcceptanceEvaluator(repo_root=PROJECT_ROOT)``), so a
    clean isolated HOME legitimately changes their result. Those opt out with
    ``@pytest.mark.no_home_isolation`` and keep the real HOME even under xdist —
    exactly as they behave serially. They are read-only probes, so they do not
    pollute the shared user dirs.
    """
    if _worker_home is None:
        return
    if request.node.get_closest_marker("no_home_isolation") is not None:
        return
    home = str(_worker_home)
    # HOME is the single lever: every user-level dir the product touches derives
    # from ``Path.home()`` — ``~/.opencontext`` (daemon/config/storage),
    # ``~/.engram`` (memory SQLite; engram_bridge ``_engram_db_path``), and the
    # XDG defaults (``Path.home()/.config|.cache``). ``Path.home()`` reads HOME on
    # POSIX and USERPROFILE on Windows, so set both.
    #
    # Deliberately do NOT set XDG_STATE_HOME/XDG_CONFIG_HOME/XDG_CACHE_HOME here.
    # They are redundant (HOME already redirects the XDG defaults) and actively
    # harmful: the golden first-run journey tests spawn ``opencontext index``
    # subprocesses that set their OWN isolated HOME but inherit our environment
    # otherwise. If we export XDG_STATE_HOME, user-mode storage writes
    # ``project_manifest.json`` under our injected XDG dir while the test looks
    # for it under the subprocess HOME — a split brain that fails the gate. HOME
    # alone keeps the subprocess and its assertions pointing at the same root.
    monkeypatch.setenv("HOME", home)
    monkeypatch.setenv("USERPROFILE", home)
    # Redirecting HOME breaks user-site console-script shims (e.g. a
    # ``~/.local/bin/pytest`` whose interpreter resolves site-packages under the
    # old HOME): a few tests shell out to bare ``pytest``/``opencontext``. Put
    # the RUNNING interpreter's bin dir first on PATH so those subprocesses
    # resolve to the same hermetic env pytest itself runs from — which is what
    # CI (where there is no user-site shim ahead of it) already does. PATH is
    # otherwise preserved, so all other tool discovery is unchanged.
    interp_bin = str(Path(sys.executable).parent)
    monkeypatch.setenv("PATH", interp_bin + os.pathsep + os.environ.get("PATH", ""))


@pytest.fixture()
def xdg_state_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Set XDG_STATE_HOME to tmp_path so user-mode storage is isolated per test.

    Also removes OPENCONTEXT_STORAGE_MODE from the environment so tests
    see the default user-mode behaviour without interference from a
    developer's local shell settings.
    """
    state_dir = tmp_path / "xdg_state"
    state_dir.mkdir()
    monkeypatch.setenv("XDG_STATE_HOME", str(state_dir))
    monkeypatch.delenv("OPENCONTEXT_STORAGE_MODE", raising=False)
    return state_dir


_REPO_ROOT = Path(__file__).resolve().parent.parent
_GUARDED = ("AGENTS.md", "CLAUDE.md", "GEMINI.md", "QWEN.md", "opencontext.yaml")
_LOG = os.environ.get("OPENCONTEXT_POLLUTION_LOG")


@pytest.fixture(autouse=True)
def _protect_repo_root_files(request: pytest.FixtureRequest):
    before = {
        name: (path.read_text(encoding="utf-8") if (path := _REPO_ROOT / name).exists() else None)
        for name in _GUARDED
    }
    yield
    for name, prior in before.items():
        path = _REPO_ROOT / name
        now = path.read_text(encoding="utf-8") if path.exists() else None
        if now == prior:
            continue
        if prior is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(prior, encoding="utf-8")
        if _LOG:
            with open(_LOG, "a", encoding="utf-8") as handle:
                handle.write(f"{request.node.nodeid} -> {name}\n")
