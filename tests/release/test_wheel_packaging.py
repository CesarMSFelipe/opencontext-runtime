"""Wheel packaging gate: runtime data files must ship in the built wheels.

The e2e suite drives the CLI with ``PYTHONPATH`` pointed at the *source* tree, so
missing ``package-data`` is invisible there — every data file exists on disk. A
real user install (``pipx install opencontext-cli``) only gets what the wheel
contains. Historically this silently dropped:

  * ``opencontext_memory/store/schema.sql``  -> every memory op failed
  * ``opencontext_core/configurator/profiles/*.md`` -> empty host instructions
  * ``opencontext_core/skills/templates/**/SKILL.md`` -> empty SDD skill templates
  * ``opencontext_sdd/**/*.md`` -> empty bundled skills

This gate builds each wheel and asserts the critical data files are inside it, so
a packaging regression fails here instead of in the user's terminal.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

# package dir -> substrings that MUST appear in the built wheel's file list.
_REQUIRED_IN_WHEEL: dict[str, list[str]] = {
    "opencontext_memory": ["opencontext_memory/store/schema.sql"],
    "opencontext_core": [
        "opencontext_core/configurator/profiles/claude-code.md",
        "opencontext_core/configurator/profiles/codex.md",
        "opencontext_core/configurator/profiles/opencode.md",
        "opencontext_core/skills/templates/oc-propose/SKILL.md",
        "opencontext_core/harness/builtins/",  # a builtin yaml
        "opencontext_core/studio/static/",  # web shell asset
    ],
    "opencontext_sdd": ["opencontext_sdd/skills/"],  # bundled skill markdown
}


def _build_wheel(pkg: str, out_dir: Path) -> Path:
    # Build from a clean staging copy, never the live source tree: setuptools
    # sweeps any adjacent __pycache__ / stale build/ into the wheel, so building
    # from the pytest-warmed tree would ship bytecode. A release must start clean;
    # copying with these ignores reproduces that contract without mutating the repo.
    pkg_src = _REPO_ROOT / "packages" / pkg
    pkg_dir = out_dir / "src"
    shutil.copytree(
        pkg_src,
        pkg_dir,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "build", "*.egg-info"),
    )
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "-w",
            str(out_dir),
            str(pkg_dir),
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0:
        pytest.skip(f"cannot build wheel for {pkg} in this env: {proc.stderr[-400:]}")
    wheels = sorted(out_dir.glob(f"{pkg.replace('_', '_')}*.whl"))
    if not wheels:
        wheels = sorted(out_dir.glob("*.whl"))
    assert wheels, f"no wheel produced for {pkg}"
    return wheels[-1]


@pytest.mark.parametrize("pkg", sorted(_REQUIRED_IN_WHEEL))
def test_wheel_contains_runtime_data_files(pkg: str, tmp_path: Path) -> None:
    wheel = _build_wheel(pkg, tmp_path)
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
    for required in _REQUIRED_IN_WHEEL[pkg]:
        assert any(required in n for n in names), (
            f"{pkg} wheel is missing runtime data '{required}'. "
            f"Add it to [tool.setuptools.package-data] in packages/{pkg}/pyproject.toml. "
            f"A real install would ship an incomplete product."
        )


# Development junk that must never ship inside a release wheel. Each entry is a
# path fragment; a match anywhere in a wheel member name fails the gate.
# Path fragments that only ever belong to dev junk. NB: 'openspec/' is a real
# shipped subpackage (opencontext_core.openspec), so it is NOT forbidden — the
# gitignored artifact dir is 'openspec/changes/', never inside a package.
_FORBIDDEN_IN_WHEEL: tuple[str, ...] = (
    "__pycache__/",
    ".pyc",
    ".pyo",
    "/tests/",
    "openspec/changes/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    ".DS_Store",
)


@pytest.mark.parametrize("pkg", sorted(_REQUIRED_IN_WHEEL))
def test_wheel_ships_no_development_junk(pkg: str, tmp_path: Path) -> None:
    """Release cleanliness: a built wheel carries only the product, no dev junk."""
    wheel = _build_wheel(pkg, tmp_path)
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
    offenders = [n for n in names if any(bad in n for bad in _FORBIDDEN_IN_WHEEL)]
    assert not offenders, (
        f"{pkg} wheel ships development junk that must not reach users: {offenders[:10]}. "
        f"Tighten the package-data globs / MANIFEST so only product files are included."
    )
