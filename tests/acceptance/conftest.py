"""Black-box acceptance harness bootstrap (ACCEPTANCE_CONTRACT.md AC-001..AC-030).

The suite invokes the real ``opencontext`` binary as a subprocess — it never
imports ``opencontext_*`` modules. The binary is selected with ``--oc-bin``
(default: ``shutil.which("opencontext")``, i.e. the active venv) so the same
tests run against a local checkout install or a cleanly installed package.

Every test gets an isolated tmp workspace AND an isolated ``$HOME`` + XDG
dirs, so global state never leaks in either direction.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest

from tests.acceptance.helpers.cli import run_json
from tests.acceptance.helpers.ops import (
    WORKFLOW_TIMEOUT,
    index_workspace,
    install_workspace,
    run_project_pytest,
)
from tests.acceptance.helpers.workspace import (
    CORRECT_ADD_EDITS,
    Workspace,
    make_workspace,
)

# The fixture projects contain deliberately-failing seeded tests; never collect
# them in place (same convention as tests/golden/conftest.py).
collect_ignore_glob = ["fixtures/*"]

# --- Lane timing accounting (TIME-SMOKE / TIME-FULL-ACC) --------------------
# ACCEPTANCE_CONTRACT.md "Timing budgets" (plan §21.1) gives the smoke and full
# acceptance lanes wall-clock budgets. The guards in test_acceptance_timing.py
# enforce them in-lane: this conftest records when the lane started and what
# was selected, and reorders the guard meta-tests to run LAST so the elapsed
# wall clock they read covers the whole lane.

_ACCEPTANCE_DIR = Path(__file__).resolve().parent
_TIMING_GUARD_FILE = "test_acceptance_timing.py"


def pytest_sessionstart(session: pytest.Session) -> None:
    session.config._oc_lane_start = time.monotonic()  # type: ignore[attr-defined]


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if getattr(config, "_oc_lane_start", None) is None:
        # Fallback: for invocations where this conftest is not an initial
        # conftest (e.g. whole-repo runs) sessionstart never fired here.
        config._oc_lane_start = time.monotonic()  # type: ignore[attr-defined]

    def _is_acceptance(item: pytest.Item) -> bool:
        path = Path(item.path).resolve()
        return _ACCEPTANCE_DIR == path.parent or _ACCEPTANCE_DIR in path.parents

    acceptance = [item for item in items if _is_acceptance(item)]
    guards = [item for item in acceptance if Path(item.path).name == _TIMING_GUARD_FILE]
    scenarios = [item for item in acceptance if item not in guards]
    config._oc_lane_selection = {  # type: ignore[attr-defined]
        "only_acceptance_selected": len(acceptance) == len(items),
        "scenario_count": len(scenarios),
        "smoke_scenario_count": sum(
            1 for item in scenarios if item.get_closest_marker("smoke") is not None
        ),
    }
    # Run the timing guards last so their wall-clock reading covers the lane.
    for guard in guards:
        items.remove(guard)
        items.append(guard)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--oc-bin",
        action="store",
        default=None,
        help="Path to the opencontext binary under test "
        "(default: shutil.which('opencontext') from the active venv).",
    )
    parser.addoption(
        "--oc-wheel",
        action="store",
        default=None,
        help="Path to a built opencontext-cli wheel for the release scenarios "
        "(AC-029/AC-030). Default: newest dist/*.whl when present.",
    )


@pytest.fixture(scope="session")
def oc_bin(request: pytest.FixtureRequest) -> str:
    """Resolve the binary under test; skip the whole suite when absent."""
    explicit = request.config.getoption("--oc-bin")
    resolved = explicit or shutil.which("opencontext")
    if not resolved:
        pytest.skip(
            "no opencontext binary found: pass --oc-bin or activate a venv "
            "with opencontext installed"
        )
    path = Path(resolved).resolve()
    if not path.exists():
        pytest.skip(f"--oc-bin {path} does not exist")
    return str(path)


@pytest.fixture()
def workspace(tmp_path: Path):
    """Factory for per-test isolated workspaces: ``workspace(fixture_name=None)``."""
    counter = {"n": 0}

    def factory(fixture: str | None = None) -> Workspace:
        counter["n"] += 1
        return make_workspace(tmp_path / f"ws{counter['n']}", fixture)

    return factory


@pytest.fixture(scope="session")
def stub_run(oc_bin: str, tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    """One shared, completed OC Flow run over py_bugfix_basic with the test_stub executor.

    Reused by AC-010 (mutation + verification), AC-013 (RED→GREEN), AC-018
    (memory reuse), AC-025 (report bundle) and AC-026 (resume), so the suite
    pays for exactly one full workflow run for all of them.
    """
    ws = make_workspace(tmp_path_factory.mktemp("stub-run"), "py_bugfix_basic")
    ws.write_stub_provider(CORRECT_ADD_EDITS)
    install_workspace(oc_bin, ws)
    index_workspace(oc_bin, ws)

    # Memory saved BEFORE the run: the run is then a "second run" that could
    # retrieve this approved memory (MEMORY_CONTRACT rule 4 / AC-018).
    memory_proc, memory_payload = run_json(
        oc_bin,
        [
            "memory",
            "v2",
            "save",
            "--title",
            "Test runner is pytest",
            "--content",
            "This project verifies changes with pytest: python -m pytest -q tests/test_app.py",
            "--type",
            "project_context",
        ],
        cwd=ws.root,
        env=ws.env,
    )
    assert memory_proc.returncode == 0, memory_proc.stderr[:400]

    # RED evidence, captured externally BEFORE the run: the seeded test fails.
    red = run_project_pytest(ws, "tests/test_app.py")

    run_proc, summary = run_json(
        oc_bin,
        ["run", "Fix failing test in app.py", "--json"],
        cwd=ws.root,
        env=ws.env,
        timeout=WORKFLOW_TIMEOUT,
    )

    # GREEN evidence, captured externally AFTER the run.
    green = run_project_pytest(ws, "tests/test_app.py")

    return {
        "ws": ws,
        "memory_receipt": memory_payload,
        "red": red,
        "run_proc": run_proc,
        "summary": summary,
        "green": green,
    }


@pytest.fixture(scope="session")
def large_indexed_ws(oc_bin: str, tmp_path_factory: pytest.TempPathFactory) -> Workspace:
    """py_large_context installed + indexed once, shared by the KG/pack scenarios."""
    ws = make_workspace(tmp_path_factory.mktemp("large-ctx"), "py_large_context")
    install_workspace(oc_bin, ws)
    index_workspace(oc_bin, ws)
    return ws
