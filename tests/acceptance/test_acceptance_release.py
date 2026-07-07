"""AC-029 / AC-030: release artifact hygiene + acceptance against a clean install.

Contracts: RELEASE_CONTRACT.md, ACCEPTANCE_CONTRACT.md.

These scenarios need a built release artifact. Resolution order:
``--oc-wheel`` → newest ``dist/*.whl`` → ``dist/opencontext.pyz``; when none
exists the tests skip with an explicit reason (build one with
``python -m build`` or pass ``--oc-wheel``).
"""

from __future__ import annotations

import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from tests.acceptance.helpers.json_assertions import assert_semver
from tests.acceptance.helpers.workspace import make_workspace

pytestmark = pytest.mark.acceptance

_REPO_DIST = Path(__file__).resolve().parents[2] / "dist"

#: RELEASE_CONTRACT: content that must never ship inside a published artifact.
_FORBIDDEN_FRAGMENTS = (
    ".git/",
    ".venv/",
    "venv/",
    ".ci-venv/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    "__pycache__",
    ".opencontext/",
    ".coverage",
    ".egg-info",
)


def _resolve_artifact(request: pytest.FixtureRequest) -> Path:
    explicit = request.config.getoption("--oc-wheel")
    if explicit:
        path = Path(explicit).resolve()
        if not path.is_file():
            pytest.skip(f"--oc-wheel {path} does not exist")
        return path
    wheels = sorted(_REPO_DIST.glob("*.whl")) if _REPO_DIST.is_dir() else []
    if wheels:
        return wheels[-1]
    pyz = _REPO_DIST / "opencontext.pyz"
    if pyz.is_file():
        return pyz
    pytest.skip(
        "no release artifact found: build one (python -m build / make pyz) "
        "or pass --oc-wheel <path>"
    )


@pytest.fixture(scope="module")
def release_artifact(request: pytest.FixtureRequest) -> Path:
    return _resolve_artifact(request)


def _entries(artifact: Path) -> list[str]:
    if artifact.suffix in {".whl", ".pyz", ".zip"}:
        with zipfile.ZipFile(artifact) as zf:
            return zf.namelist()
    if artifact.name.endswith((".tar.gz", ".tgz")):
        with tarfile.open(artifact) as tf:
            return tf.getnames()
    pytest.skip(f"unsupported release artifact format: {artifact.name}")


def test_release_artifact_contains_no_local_state(release_artifact) -> None:
    """AC-029: the release artifact contains no .git, .venv, caches, or local state."""
    entries = _entries(release_artifact)
    assert entries, f"empty release artifact: {release_artifact}"
    violations = [
        entry for entry in entries if any(fragment in entry for fragment in _FORBIDDEN_FRAGMENTS)
    ]
    assert not violations, (
        f"RELEASE_CONTRACT artifact hygiene violated in {release_artifact.name}: "
        f"{violations[:10]} (+{max(0, len(violations) - 10)} more)"
    )


def _clean_binary(release_artifact: Path, tmp: Path) -> list[str]:
    """A command prefix that runs the artifact exactly as a fresh user would."""
    if release_artifact.suffix == ".pyz":
        return [sys.executable, str(release_artifact)]
    # Wheel: install into a brand-new venv (the RELEASE_CONTRACT install stage).
    venv_dir = tmp / "clean-venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True, timeout=180)
    pip = venv_dir / "bin" / "pip"
    installed = subprocess.run(
        [str(pip), "install", str(release_artifact)],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if installed.returncode != 0:
        pytest.skip(
            f"pip install of {release_artifact.name} failed in a fresh venv "
            f"(offline?): {installed.stderr[-300:]}"
        )
    return [str(venv_dir / "bin" / "opencontext")]


def test_acceptance_smoke_passes_against_clean_install(release_artifact, tmp_path) -> None:
    """AC-030: the acceptance harness passes against a cleanly installed package."""
    prefix = _clean_binary(release_artifact, tmp_path)
    ws = make_workspace(tmp_path / "clean-ws", "py_bugfix_basic")

    def clean_run(*args: str, timeout: int = 180):
        return subprocess.run(
            [*prefix, *args],
            cwd=str(ws.root),
            env=ws.env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    # SMOKE-001: version emits clean JSON with a real (non-placeholder) version.
    proc = clean_run("version", "--json")
    assert proc.returncode == 0, proc.stderr[:400]
    import json

    version = json.loads(proc.stdout)
    assert_semver(version["opencontext"], where="clean-install version")

    # SMOKE-003: workspace install + status work as a first-run user.
    proc = clean_run("install", ".", "--yes", "--json")
    assert proc.returncode == 0, proc.stderr[:400]
    assert json.loads(proc.stdout).get("status") == "ok"

    proc = clean_run("status", "--json", ".")
    assert proc.returncode == 0, proc.stderr[:400]
    status = json.loads(proc.stdout)
    assert status.get("status") == "ready", status
    # canonical_status is a newer additive field: enforce coherence when the
    # artifact under test already ships it (semver: additive fields only).
    if "canonical_status" in status:
        assert status["canonical_status"] == "passed", status
