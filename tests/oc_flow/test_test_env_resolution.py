"""Project test-environment resolution for verification commands.

Resolution order: (1) an explicit ``workflow_defaults.test_command`` in
``.opencontext/harness.yaml`` wins; (2) the PROJECT's own interpreter
(``<root>/.venv/bin/python`` or ``venv/bin/python``) when it exists AND has
pytest importable; (3) the current ``sys.executable`` (runtime) fallback.
The chosen source is recorded in the verification evidence as the additive
``runner_source`` field ("configured" | "project_venv" | "runtime").
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from opencontext_core.oc_flow.runner import (
    ResolvedTestCommand,
    _discover_test_command,
    resolve_test_command,
)

_TEST_FILE = "def test_truth() -> None:\n    assert True\n"


def _fake_venv(root: Path, name: str = ".venv", *, with_pytest: bool = True) -> Path:
    """Create a structurally valid fake venv layout; returns its python path."""
    bin_dir = root / name / "bin"
    bin_dir.mkdir(parents=True)
    python = bin_dir / "python"
    python.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    python.chmod(0o755)
    if with_pytest:
        (bin_dir / "pytest").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    return python


# ------------------------------------------------------------- resolution order
def test_project_venv_interpreter_chosen(tmp_path: Path) -> None:
    (tmp_path / "test_sample.py").write_text(_TEST_FILE, encoding="utf-8")
    python = _fake_venv(tmp_path)

    resolved = resolve_test_command(tmp_path)

    assert isinstance(resolved, ResolvedTestCommand)
    assert resolved.source == "project_venv"
    assert resolved.command is not None
    assert resolved.command[0] == str(python)
    assert resolved.command[1:3] == ["-m", "pytest"]


def test_venv_dir_named_venv_also_resolves(tmp_path: Path) -> None:
    (tmp_path / "test_sample.py").write_text(_TEST_FILE, encoding="utf-8")
    python = _fake_venv(tmp_path, name="venv")

    resolved = resolve_test_command(tmp_path)

    assert resolved.source == "project_venv"
    assert resolved.command is not None and resolved.command[0] == str(python)


def test_venv_without_pytest_falls_back_to_runtime(tmp_path: Path) -> None:
    (tmp_path / "test_sample.py").write_text(_TEST_FILE, encoding="utf-8")
    _fake_venv(tmp_path, with_pytest=False)

    resolved = resolve_test_command(tmp_path)

    assert resolved.source == "runtime"
    assert resolved.command is not None and resolved.command[0] == sys.executable


def test_configured_test_command_wins_over_project_venv(tmp_path: Path) -> None:
    (tmp_path / "test_sample.py").write_text(_TEST_FILE, encoding="utf-8")
    _fake_venv(tmp_path)
    harness = tmp_path / ".opencontext" / "harness.yaml"
    harness.parent.mkdir(parents=True)
    harness.write_text(
        "workflow_defaults:\n  test_command: make test\n",
        encoding="utf-8",
    )

    resolved = resolve_test_command(tmp_path)

    assert resolved.source == "configured"
    assert resolved.command == ["make", "test"]


def test_configured_test_command_accepts_argv_list(tmp_path: Path) -> None:
    harness = tmp_path / ".opencontext" / "harness.yaml"
    harness.parent.mkdir(parents=True)
    harness.write_text(
        "workflow_defaults:\n  test_command: [npx, jest, --ci]\n",
        encoding="utf-8",
    )

    resolved = resolve_test_command(tmp_path)

    assert resolved.source == "configured"
    assert resolved.command == ["npx", "jest", "--ci"]


def test_no_tests_yields_no_command(tmp_path: Path) -> None:
    resolved = resolve_test_command(tmp_path)
    assert resolved.command is None
    assert resolved.source == "runtime"


def test_discover_test_command_back_compat(tmp_path: Path) -> None:
    (tmp_path / "test_sample.py").write_text(_TEST_FILE, encoding="utf-8")
    command = _discover_test_command(tmp_path)
    assert command is not None
    assert command[0] == sys.executable
    assert command[1:4] == ["-m", "pytest", "-q"]
    assert command[-1].endswith("test_sample.py")


# --------------------------------------------------- evidence: runner_source
def test_runner_source_recorded_in_verification_evidence(tmp_path: Path, monkeypatch) -> None:
    """An end-to-end run records runner_source in run.json + verification.json."""
    import shutil

    from opencontext_core.oc_flow import cli as oc_flow_cli
    from opencontext_core.oc_flow.cli import run_oc_flow_cli
    from opencontext_core.providers.detect import DetectedProvider

    monkeypatch.setattr(
        oc_flow_cli,
        "detect_provider",
        lambda: DetectedProvider(name="mock", api_key="", model="mock", source="fallback"),
    )
    golden = Path(__file__).resolve().parents[1] / "golden" / "oc_flow_bugfix_python"
    work = tmp_path / "fixture"
    shutil.copytree(golden, work)

    summary = run_oc_flow_cli(
        "Fix failing test", root=work, workflow="oc-flow", lane="fast", quiet=True
    )
    assert summary["status"] == "completed"

    run_dirs = list((work / ".opencontext" / "sessions").glob("*/runs/*"))
    assert run_dirs, "the run must persist its run dir"
    manifest = json.loads((run_dirs[0] / "run.json").read_text(encoding="utf-8"))
    assert manifest["verification"]["runner_source"] == "runtime"
    verification = json.loads((run_dirs[0] / "verification.json").read_text(encoding="utf-8"))
    assert verification["runner_source"] == "runtime"
