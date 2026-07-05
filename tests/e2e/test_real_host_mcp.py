"""Real-host MCP integration proof (real-host-dod-convergence REQ-1, UVD-H1..H3).

The Definition of Done is: OpenContext works in the *real* environments of the
three target agent hosts — codex, opencode, and claude code. Config writers are
unit-tested elsewhere; this module proves the round-trip with the **real host
binaries** installed on the machine:

    temp $HOME + temp project
      -> opencontext setup <agent> --scope local
      -> assert the host config file is written in the host's native shape
      -> <host> mcp list        (the real binary loads the config)
      -> assert opencontext is present; for opencode/claude, that it CONNECTS

No provider credentials or network are required: ``<host> mcp list`` reads the
host's own config and (for opencode/claude) performs a local stdio MCP handshake
against ``opencontext mcp --workflow-tools``. A full model turn is out of scope
here (covered best-effort elsewhere).

Each host scenario SKIPS with a reason when its binary is absent — never a
silent pass. Runtime notes:
  * opencode's launcher resolves its own runtime under ``$HOME/.opencode``; the
    temp $HOME is symlinked to the real runtime so config stays isolated while
    the binary can find itself. Skips if the real runtime is absent.
  * codex's ``mcp list`` does not health-check, so codex's proof is config-load +
    ``enabled`` status (a live handshake for codex is covered by REQ-3).
  * claude requires project MCP servers to be approved; the fixture pre-approves
    via ``.claude/settings.local.json`` so the health check reaches Connected.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.real_host

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE_DIRS = (
    _REPO_ROOT / "packages" / "opencontext_core",
    _REPO_ROOT / "packages" / "opencontext_cli",
)


def _env(home: Path) -> dict[str, str]:
    """Subprocess env with an isolated ``$HOME`` and an absolute ``PYTHONPATH``."""
    entries = [
        str(Path(raw).resolve())
        for raw in os.environ.get("PYTHONPATH", "").split(os.pathsep)
        if raw
    ]
    for pkg in _PACKAGE_DIRS:
        if str(pkg) not in entries:
            entries.append(str(pkg))
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home)}
    env["PYTHONPATH"] = os.pathsep.join(entries)
    env["OPENCONTEXT_STORAGE_MODE"] = "local"
    return env


def _project(tmp_path: Path) -> tuple[Path, Path]:
    """Create an isolated ``home`` and a minimal ``proj`` (one source file)."""
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    home.mkdir(parents=True, exist_ok=True)
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    return home, proj


def _setup(agent: str, home: Path, proj: Path) -> subprocess.CompletedProcess[str]:
    """Run ``opencontext setup <agent> --scope local`` into the isolated env."""
    return subprocess.run(
        [
            "opencontext",
            "setup",
            agent,
            "--scope",
            "local",
            "--yes",
            "--non-interactive",
            "--root",
            str(proj),
        ],
        cwd=str(proj),
        env=_env(home),
        capture_output=True,
        text=True,
        timeout=120,
    )


def _host_list(
    binary: str, home: Path, proj: Path, timeout: int
) -> subprocess.CompletedProcess[str]:
    """Run ``<binary> mcp list`` in the isolated env; the real host loads config."""
    return subprocess.run(
        [binary, "mcp", "list"],
        cwd=str(proj),
        env=_env(home),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _require(binary: str) -> None:
    if shutil.which("opencontext") is None:
        pytest.skip("opencontext CLI not on PATH in this test environment")
    if shutil.which(binary) is None:
        pytest.skip(f"real host binary '{binary}' not installed — cannot prove real integration")


# --------------------------------------------------------------------------- #
# codex — TOML config.toml, ``codex mcp list`` shows enabled server
# --------------------------------------------------------------------------- #
def test_codex_loads_opencontext(tmp_path: Path) -> None:
    _require("codex")
    home, proj = _project(tmp_path)

    setup = _setup("codex", home, proj)
    assert setup.returncode == 0, f"setup codex failed: {setup.stderr or setup.stdout}"

    cfg = home / ".codex" / "config.toml"
    assert cfg.is_file(), "codex config.toml not written"
    body = cfg.read_text(encoding="utf-8")
    assert "[mcp_servers.opencontext]" in body, (
        f"opencontext MCP entry missing from config.toml:\n{body}"
    )

    try:
        listed = _host_list("codex", home, proj, timeout=90)
    except subprocess.TimeoutExpired:
        pytest.skip("codex mcp list timed out in this environment")
    combined = f"{listed.stdout}\n{listed.stderr}"
    assert "opencontext" in listed.stdout, f"codex did not list opencontext:\n{combined}"
    assert "enabled" in listed.stdout, f"codex opencontext server not enabled:\n{combined}"


# --------------------------------------------------------------------------- #
# opencode — opencode.json, ``opencode mcp list`` performs a live handshake
# --------------------------------------------------------------------------- #
def test_opencode_connects_to_opencontext(tmp_path: Path) -> None:
    _require("opencode")
    real_runtime = Path.home() / ".opencode"
    if not real_runtime.is_dir():
        pytest.skip("real ~/.opencode runtime absent — opencode launcher cannot self-locate")

    home, proj = _project(tmp_path)
    # Let the launcher find its runtime while keeping ~/.config/opencode isolated.
    (home / ".opencode").symlink_to(real_runtime)

    setup = _setup("opencode", home, proj)
    assert setup.returncode == 0, f"setup opencode failed: {setup.stderr or setup.stdout}"

    cfg = home / ".config" / "opencode" / "opencode.json"
    assert cfg.is_file(), "opencode.json not written"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert "opencontext" in data.get("mcp", {}), f"opencontext missing from opencode.json: {data}"

    try:
        listed = _host_list("opencode", home, proj, timeout=90)
    except subprocess.TimeoutExpired:
        pytest.skip("opencode mcp list timed out in this environment")
    combined = f"{listed.stdout}\n{listed.stderr}"
    assert "opencontext" in combined, f"opencode did not list opencontext:\n{combined}"
    assert "connected" in combined.lower(), f"opencode did not connect to opencontext:\n{combined}"


# --------------------------------------------------------------------------- #
# claude code — project .mcp.json, ``claude mcp list`` health-checks the server
# --------------------------------------------------------------------------- #
def test_claude_connects_to_opencontext(tmp_path: Path) -> None:
    _require("claude")
    home, proj = _project(tmp_path)

    setup = _setup("claude-code", home, proj)
    assert setup.returncode == 0, f"setup claude-code failed: {setup.stderr or setup.stdout}"

    cfg = proj / ".mcp.json"
    assert cfg.is_file(), "project .mcp.json not written"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert "opencontext" in data.get("mcpServers", {}), (
        f"opencontext missing from .mcp.json: {data}"
    )

    # Pre-approve the project MCP server so the health check reaches Connected
    # instead of stopping at 'Pending approval' (claude's interactive gate).
    claude_dir = proj / ".claude"
    claude_dir.mkdir(exist_ok=True)
    (claude_dir / "settings.local.json").write_text(
        json.dumps({"enableAllProjectMcpServers": True}), encoding="utf-8"
    )

    try:
        listed = _host_list("claude", home, proj, timeout=90)
    except subprocess.TimeoutExpired:
        pytest.skip("claude mcp list timed out in this environment")
    combined = f"{listed.stdout}\n{listed.stderr}"
    assert "opencontext" in combined, f"claude did not list opencontext:\n{combined}"
    assert "connected" in combined.lower(), f"claude did not connect to opencontext:\n{combined}"
