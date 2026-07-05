"""PR-AHE-008 setup-output tests for Claude Code, Codex, OpenCode.

Spec 8.17: generated files must match the current product surface and the
scope reporting must be honest. This file pins the setup output contract
end-to-end: what files each host writes under --scope local, what the
report claims, and what the dry-run plan says.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.configurator.service import Configurator


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    proj.mkdir()
    return proj


# --------------------------------------------------------------------------- #
# Claude Code (8.17)
# --------------------------------------------------------------------------- #


def test_setup_claude_code_local_emits_local_and_global_split(home: Path, project: Path) -> None:
    """Claude Code writes a project-root .mcp.json plus global CLAUDE.md/settings."""
    report = Configurator(project_root=project).configure(["claude-code"], scope="local")
    result = report["results"][0]

    # Project-local: the canonical AGENTS.md-honoring file does not apply to
    # claude-code (it uses CLAUDE.md, not project AGENTS.md), but the
    # project-root .mcp.json is a per-repo MCP file claude-code needs.
    assert any(Path(p).name == ".mcp.json" for p in result["local_files_written"])
    # Global: claude-code writes CLAUDE.md and settings.json under ~/.claude.
    global_posix = {Path(p).as_posix() for p in result["global_files_written"]}
    assert any(".claude/CLAUDE.md" in p for p in global_posix)
    assert any(".claude/settings.json" in p for p in global_posix)
    # The report MUST explain the global writes (Host-Constrained Local).
    assert result["global_write_reason"].startswith("Host-constrained local setup")
    # backup_id is present (real run, not dry-run).
    assert result["backup_id"]


def test_setup_claude_code_dry_run_matches_real_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec 8.11: dry-run file set equals real-run file set for Claude Code.

    Two separate home dirs are used so the real run cannot pollute the
    dry-run view with already-written global files (which would short-circuit
    the plan to "nothing to do").
    """
    real_home = tmp_path / "real_home"
    dry_home = tmp_path / "dry_home"
    real_home.mkdir()
    dry_home.mkdir()
    real_project = real_home / "proj"
    dry_project = dry_home / "proj"
    real_project.mkdir()
    dry_project.mkdir()

    # Real run
    monkeypatch.setattr(Path, "home", lambda: real_home)
    real = Configurator(project_root=real_project).configure(
        ["claude-code"], scope="local", dry_run=False
    )
    # Dry run on a fresh home
    monkeypatch.setattr(Path, "home", lambda: dry_home)
    dry = Configurator(project_root=dry_project).configure(
        ["claude-code"], scope="local", dry_run=True
    )

    real_paths = {p for p in real["results"][0]["local_files_written"]}
    real_paths.update(p for p in real["results"][0]["global_files_written"])
    dry_paths = {entry["path"] for entry in dry["results"][0]["plan"]}

    # Compare by path-tail (suffix), so home dir + project root basename
    # differences do not leak into the parity check. Each planned file is
    # uniquely identified by its absolute-path tail, which is what the
    # install ledger/restore will key on anyway.
    def _tail(paths: set[str]) -> set[str]:
        out: set[str] = set()
        for p in paths:
            tail = Path(p).name
            parent = Path(p).parent.name
            out.add(f"{parent}/{tail}" if parent else tail)
        return out

    assert _tail(dry_paths) == _tail(real_paths), (
        f"dry-run plan {dry_paths} must equal real-run file set {real_paths}"
    )


def test_setup_claude_code_dry_run_json_has_per_file_action(home: Path, project: Path) -> None:
    """Spec 8.11: dry-run JSON includes per-file plan from Configurator."""
    report = Configurator(project_root=project).configure(
        ["claude-code"], scope="local", dry_run=True
    )
    result = report["results"][0]
    actions = {entry["action"] for entry in result["plan"]}
    # A fresh project root means every planned file is `create`.
    assert "create" in actions


# --------------------------------------------------------------------------- #
# Codex (8.17)
# --------------------------------------------------------------------------- #


def test_setup_codex_local_writes_project_agents_md(home: Path, project: Path) -> None:
    """Codex honors AGENTS.md (project) and writes a global mcp config."""
    report = Configurator(project_root=project).configure(["codex"], scope="local")
    result = report["results"][0]

    assert (project / "AGENTS.md").as_posix() in [
        Path(p).as_posix() for p in result["local_files_written"]
    ]
    global_posix = {Path(p).as_posix() for p in result["global_files_written"]}
    assert any(".codex/config.toml" in p for p in global_posix)
    assert result["global_write_reason"].startswith("Host-constrained local setup")


def test_setup_codex_dry_run_matches_real_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec 8.11: dry-run parity for Codex."""
    real_home = tmp_path / "real_home"
    dry_home = tmp_path / "dry_home"
    real_home.mkdir()
    dry_home.mkdir()
    real_project = real_home / "proj"
    dry_project = dry_home / "proj"
    real_project.mkdir()
    dry_project.mkdir()

    monkeypatch.setattr(Path, "home", lambda: real_home)
    real = Configurator(project_root=real_project).configure(
        ["codex"], scope="local", dry_run=False
    )
    monkeypatch.setattr(Path, "home", lambda: dry_home)
    dry = Configurator(project_root=dry_project).configure(["codex"], scope="local", dry_run=True)
    real_paths = set(real["results"][0]["local_files_written"])
    real_paths.update(real["results"][0]["global_files_written"])
    dry_paths = {entry["path"] for entry in dry["results"][0]["plan"]}

    def _tail(paths: set[str]) -> set[str]:
        out: set[str] = set()
        for p in paths:
            tail = Path(p).name
            parent = Path(p).parent.name
            out.add(f"{parent}/{tail}" if parent else tail)
        return out

    assert _tail(dry_paths) == _tail(real_paths)


# --------------------------------------------------------------------------- #
# OpenCode (8.17)
# --------------------------------------------------------------------------- #


def test_setup_opencode_local_writes_project_agents_md(home: Path, project: Path) -> None:
    """OpenCode honors AGENTS.md and writes global mcp.json + personas."""
    report = Configurator(project_root=project).configure(["opencode"], scope="local")
    result = report["results"][0]

    assert (project / "AGENTS.md").as_posix() in [
        Path(p).as_posix() for p in result["local_files_written"]
    ]
    global_posix = {Path(p).as_posix() for p in result["global_files_written"]}
    assert any(p.endswith(".config/opencode/opencode.json") for p in global_posix)
    # Global personas live under ~/.config/opencode/agents/.
    assert any(".config/opencode/agents" in p for p in global_posix)
    assert result["global_write_reason"].startswith("Host-constrained local setup")
    # Spec 8.14: the dead sdd-orchestrator.json must not be written.
    assert not any(p.endswith("sdd-orchestrator.json") for p in global_posix)


def test_setup_opencode_dry_run_matches_real_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec 8.11: dry-run parity for OpenCode."""
    real_home = tmp_path / "real_home"
    dry_home = tmp_path / "dry_home"
    real_home.mkdir()
    dry_home.mkdir()
    real_project = real_home / "proj"
    dry_project = dry_home / "proj"
    real_project.mkdir()
    dry_project.mkdir()

    monkeypatch.setattr(Path, "home", lambda: real_home)
    real = Configurator(project_root=real_project).configure(
        ["opencode"], scope="local", dry_run=False
    )
    monkeypatch.setattr(Path, "home", lambda: dry_home)
    dry = Configurator(project_root=dry_project).configure(
        ["opencode"], scope="local", dry_run=True
    )
    real_paths = set(real["results"][0]["local_files_written"])
    real_paths.update(real["results"][0]["global_files_written"])
    dry_paths = {entry["path"] for entry in dry["results"][0]["plan"]}

    def _tail(paths: set[str]) -> set[str]:
        out: set[str] = set()
        for p in paths:
            tail = Path(p).name
            parent = Path(p).parent.name
            out.add(f"{parent}/{tail}" if parent else tail)
        return out

    assert _tail(dry_paths) == _tail(real_paths), (
        f"dry-run plan {dry_paths} must equal real-run file set {real_paths}"
    )


def test_setup_opencode_dry_run_does_not_emit_dead_format(home: Path, project: Path) -> None:
    """Spec 8.14: dry-run also drops the dead sdd-orchestrator.json / wildcards."""
    report = Configurator(project_root=project).configure(["opencode"], scope="local", dry_run=True)
    planned = {entry["path"] for entry in report["results"][0]["plan"]}
    assert not any(p.endswith("sdd-orchestrator.json") for p in planned)


# --------------------------------------------------------------------------- #
# JSON shape contract (8.10)
# --------------------------------------------------------------------------- #


def test_setup_json_classifies_local_vs_global_writes(home: Path, project: Path) -> None:
    """Spec 8.10: classified local_files_written / global_files_written / reason."""
    report = Configurator(project_root=project).configure(["opencode"], scope="local")
    # Top-level status: configured (not dry-run).
    assert report["status"] == "configured"
    assert report["dry_run"] is False
    # Per-agent result carries the classified lists.
    result = report["results"][0]
    assert isinstance(result["local_files_written"], list)
    assert isinstance(result["global_files_written"], list)
    # Reason is non-empty whenever there are global writes.
    if result["global_files_written"]:
        assert result["global_write_reason"]


def test_setup_json_dry_run_exposes_per_file_plan(home: Path, project: Path) -> None:
    """Spec 8.11: dry-run JSON returns the per-file plan from Configurator."""
    report = Configurator(project_root=project).configure(["opencode"], scope="local", dry_run=True)
    result = report["results"][0]
    # The plan entries have a `path` and an `action` (create|modify|unchanged).
    assert "plan" in result
    for entry in result["plan"]:
        assert "path" in entry
        assert "action" in entry
        assert entry["action"] in ("create", "modify", "unchanged")


def test_setup_json_no_legacy_wildcard_in_any_field(home: Path, project: Path) -> None:
    """Spec 8.15: mcp__opencontext__* wildcard must not appear in any reported file."""
    report = Configurator(project_root=project).configure(["opencode"], scope="local")
    for result in report["results"]:
        for path in result["local_files_written"] + result["global_files_written"]:
            assert "mcp__opencontext__*" not in path, (
                f"wildcard tool name leaked into reported file path: {path}"
            )
