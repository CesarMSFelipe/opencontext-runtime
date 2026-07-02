"""Release gate: dist/opencontext.pyz must match the editable install's CLI surface.

C6 (product-closure-r13): The existing pyz predates `sdd` command restoration.
This test:
  1. Builds a fresh pyz from the current source tree via scripts/build_binary.py
  2. Runs `python <pyz> <cmd> --help` for a matrix of subcommands
  3. Asserts exit 0 for every subcommand
  4. Asserts the pyz top-level subcommand set == the editable parser's set
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BUILD_SCRIPT = _REPO_ROOT / "scripts" / "build_binary.py"

# Subcommands exercised by the parity matrix.
_MATRIX = ["", "sdd", "verify", "index", "uninstall", "studio"]


@pytest.fixture(scope="module")
def built_pyz(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build a fresh pyz from the current source tree and return its path."""
    tmp = tmp_path_factory.mktemp("pyz_build")
    out = tmp / "opencontext.pyz"

    # Import and call build() directly (no subprocess needed).
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    try:
        from build_binary import build  # type: ignore[import]

        build(out)
    finally:
        sys.path.pop(0)

    assert out.exists(), f"build() did not produce output at {out}"
    return out


def _pyz_cmd(pyz: Path, subcommand: str) -> list[str]:
    args = [sys.executable, str(pyz)]
    if subcommand:
        args.append(subcommand)
    args.append("--help")
    return args


@pytest.mark.parametrize("subcommand", _MATRIX)
def test_pyz_subcommand_help_exits_zero(built_pyz: Path, subcommand: str) -> None:
    """Every subcommand --help must exit 0 in the pyz.

    Strict TDD: fails if the pyz is stale and 'sdd' is absent.
    """
    cmd = _pyz_cmd(built_pyz, subcommand)
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    assert result.returncode == 0, (
        f"`{' '.join(cmd)}` exited {result.returncode}:\n"
        f"stdout: {result.stdout.decode(errors='replace')}\n"
        f"stderr: {result.stderr.decode(errors='replace')}"
    )


def _extract_subcommands_from_help(help_text: str) -> set[str]:
    """Parse argparse --help output and return the set of top-level subcommand names.

    Handles both formats:
      - positional-arguments block with indented ``    cmd    description`` lines
      - ``{cmd1,cmd2,...}`` inline list
    """
    import re

    subs: set[str] = set()
    # Format 1: {cmd1,cmd2,...} inline.
    for m in re.finditer(r"\{([^}]+)\}", help_text):
        for part in m.group(1).split(","):
            word = part.strip()
            if word:
                subs.add(word)
    # Format 2: positional-arguments block — lines like "    cmd     description".
    in_positional = False
    for line in help_text.splitlines():
        if re.match(r"positional arguments:", line.strip()):
            in_positional = True
            continue
        if in_positional:
            if line.startswith("  ") and not line.startswith("   "):
                # 2-space indent = section separator / heading
                if not line.strip().startswith("-"):
                    continue
            if line.startswith("    "):
                # 4-space indent = subcommand line
                word = line.strip().split()[0]
                if word and re.match(r"^[a-zA-Z][a-zA-Z0-9_-]*$", word):
                    subs.add(word)
            elif line.strip() == "" or (line.strip() and not line.startswith(" ")):
                in_positional = False
    return subs


def test_pyz_subcommand_set_matches_editable(built_pyz: Path) -> None:
    """The pyz top-level subcommand set must equal the editable parser's set.

    Strict TDD: fails until the pyz is rebuilt from the current source tree
    (build via scripts/build_binary.py).
    """
    # Collect subcommands from the editable install via its --help output.
    editable_result = subprocess.run(
        [sys.executable, "-m", "opencontext_cli.main", "--help"],
        capture_output=True,
        timeout=30,
    )
    assert editable_result.returncode == 0, (
        f"editable --help failed: {editable_result.stderr.decode(errors='replace')}"
    )
    editable_subs = _extract_subcommands_from_help(
        editable_result.stdout.decode(errors="replace")
    )

    # Collect subcommands from the pyz by parsing --help output.
    pyz_result = subprocess.run(
        [sys.executable, str(built_pyz), "--help"],
        capture_output=True,
        timeout=30,
    )
    assert pyz_result.returncode == 0, (
        f"pyz --help failed: {pyz_result.stderr.decode(errors='replace')}"
    )
    pyz_subs = _extract_subcommands_from_help(pyz_result.stdout.decode(errors="replace"))

    assert editable_subs, "editable --help returned no subcommands (parser issue)"
    assert pyz_subs, "pyz --help returned no subcommands (build or parse issue)"

    missing_in_pyz = editable_subs - pyz_subs
    assert not missing_in_pyz, (
        f"Subcommands present in editable but absent in pyz: {sorted(missing_in_pyz)}\n"
        f"Editable ({len(editable_subs)}): {sorted(editable_subs)}\n"
        f"Pyz ({len(pyz_subs)}): {sorted(pyz_subs)}"
    )
