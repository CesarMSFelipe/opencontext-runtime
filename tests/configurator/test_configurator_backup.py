"""Reversible safety for configuration: pre-change backup, dry-run, rollback, restore.

All filesystem access is redirected to a tmp dir via a monkeypatched ``Path.home``
so nothing here touches the repository or the real home directory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencontext_core.configurator.backup import (
    BackupStore,
    list_backups,
    restore,
)
from opencontext_core.configurator.service import Configurator


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``Path.home`` at a throwaway directory for the whole test."""

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


def _backups_root(home: Path) -> Path:
    return home / ".opencontext" / "backups"


# --- pre-change backup -------------------------------------------------------


def test_backup_created_before_a_real_change(home: Path) -> None:
    report = Configurator(project_root=home).configure(["claude-code"], scope="global")

    entry = report["results"][0]
    backup_id = entry["backup_id"]
    assert backup_id is not None

    backup_dir = _backups_root(home) / backup_id
    manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["id"] == backup_id
    assert manifest["agents"] == ["claude-code"]
    assert manifest["source"] == "configure"
    assert "created_at" in manifest
    # The files that were about to change are recorded.
    recorded = {f["path"] for f in manifest["files"]}
    assert str(home / ".claude" / "CLAUDE.md") in recorded


def test_backup_snapshots_prior_content_and_did_not_exist(home: Path) -> None:
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True)
    (claude_dir / "CLAUDE.md").write_text("# Mine\n\nKeep this.\n", encoding="utf-8")

    report = Configurator(project_root=home).configure(["claude-code"], scope="global")
    backup_id = report["results"][0]["backup_id"]
    manifest = json.loads(
        (_backups_root(home) / backup_id / "manifest.json").read_text(encoding="utf-8")
    )

    by_path = {f["path"]: f for f in manifest["files"]}
    md_entry = by_path[str(claude_dir / "CLAUDE.md")]
    assert md_entry["existed"] is True

    mcp_entry = by_path[str(claude_dir / "mcp.json")]
    assert mcp_entry["existed"] is False


def test_backup_skipped_when_nothing_changes(home: Path) -> None:
    cfg = Configurator(project_root=home)
    cfg.configure(["claude-code"], scope="global")

    backups_after_first = list_backups()
    assert len(backups_after_first) == 1

    # Second run is fully idempotent; no new snapshot should be taken.
    second = cfg.configure(["claude-code"], scope="global")
    assert second["results"][0]["backup_id"] is None
    assert len(list_backups()) == 1


# --- dry-run -----------------------------------------------------------------


def test_dry_run_writes_nothing_but_reports_plan(home: Path) -> None:
    report = Configurator(project_root=home).configure(
        ["claude-code"], scope="global", dry_run=True
    )

    assert report["dry_run"] is True
    entry = report["results"][0]
    assert entry["status"] == "planned"

    planned = {p["path"]: p["action"] for p in entry["plan"]}
    assert planned[str(home / ".claude" / "CLAUDE.md")] == "create"
    assert planned[str(home / ".claude" / "mcp.json")] == "create"

    # Nothing was written, including no backup directory.
    assert not (home / ".claude").exists()
    assert not _backups_root(home).exists()


def test_dry_run_reports_modify_for_existing_files(home: Path) -> None:
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True)
    (claude_dir / "CLAUDE.md").write_text("# Mine\n", encoding="utf-8")

    report = Configurator(project_root=home).configure(
        ["claude-code"], scope="global", dry_run=True
    )
    plan = {p["path"]: p["action"] for p in report["results"][0]["plan"]}
    assert plan[str(claude_dir / "CLAUDE.md")] == "modify"
    # Untouched on disk.
    assert (claude_dir / "CLAUDE.md").read_text(encoding="utf-8") == "# Mine\n"


# --- rollback on failure -----------------------------------------------------


def test_mid_write_failure_rolls_back_leaving_user_content_intact(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True)
    original = "# Mine\n\nKeep this.\n"
    (claude_dir / "CLAUDE.md").write_text(original, encoding="utf-8")

    # Force the extras step to blow up *after* MCP + instructions are written.
    def boom(self: Configurator, adapter: object) -> list[str]:
        raise RuntimeError("disk full")

    monkeypatch.setattr(Configurator, "_write_extras", boom)

    cfg = Configurator(project_root=home)
    with pytest.raises(RuntimeError, match="disk full"):
        cfg.configure_one("claude-code", scope="global")

    # The instructions file is restored to exactly the user's content...
    assert (claude_dir / "CLAUDE.md").read_text(encoding="utf-8") == original
    # ...and the file that did not exist before is gone again.
    assert not (claude_dir / "mcp.json").exists()


def test_failure_in_configure_propagates_and_restores(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(self: Configurator, adapter: object) -> list[str]:
        raise RuntimeError("boom")

    monkeypatch.setattr(Configurator, "_write_extras", boom)

    with pytest.raises(RuntimeError):
        Configurator(project_root=home).configure(["claude-code"], scope="global")

    # Nothing left behind from the partial write.
    assert not (home / ".claude" / "mcp.json").exists()
    assert not (home / ".claude" / "CLAUDE.md").exists()


# --- restore API -------------------------------------------------------------


def test_restore_returns_files_to_prior_state(home: Path) -> None:
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True)
    original = "# Mine\n\nKeep this.\n"
    (claude_dir / "CLAUDE.md").write_text(original, encoding="utf-8")

    report = Configurator(project_root=home).configure(["claude-code"], scope="global")
    backup_id = report["results"][0]["backup_id"]

    # Sanity: configuration actually changed things.
    assert (claude_dir / "mcp.json").exists()
    assert (claude_dir / "CLAUDE.md").read_text(encoding="utf-8") != original

    result = restore(backup_id)
    assert result["status"] == "restored"

    # The modified file is back to the user's content...
    assert (claude_dir / "CLAUDE.md").read_text(encoding="utf-8") == original
    # ...and the previously-absent file was removed again.
    assert not (claude_dir / "mcp.json").exists()


def test_restore_latest(home: Path) -> None:
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True)
    (claude_dir / "CLAUDE.md").write_text("# Mine\n", encoding="utf-8")

    Configurator(project_root=home).configure(["claude-code"], scope="global")
    result = restore("latest")
    assert result["status"] == "restored"
    assert (claude_dir / "CLAUDE.md").read_text(encoding="utf-8") == "# Mine\n"
    assert not (claude_dir / "mcp.json").exists()


def test_list_backups_newest_first(home: Path) -> None:
    cfg = Configurator(project_root=home)
    cfg.configure(["claude-code"], scope="global")
    cfg.configure(["codex"], scope="global")

    backups = list_backups()
    assert len(backups) == 2
    # Newest first.
    assert backups[0].created_at >= backups[1].created_at
    agents = {a for b in backups for a in b.agents}
    assert agents == {"claude-code", "codex"}


def test_restore_unknown_id_is_error(home: Path) -> None:
    _backups_root(home).mkdir(parents=True)
    result = restore("does-not-exist")
    assert result["status"] == "error"


def test_restore_rejects_paths_outside_home(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Hand-craft a malicious manifest that points outside $HOME.
    store = BackupStore()
    backup_id = "evil"
    backup_dir = store.root / backup_id
    backup_dir.mkdir(parents=True)
    outside = home.parent / "outside.txt"
    manifest = {
        "id": backup_id,
        "created_at": "2026-01-01T00:00:00",
        "agents": ["claude-code"],
        "source": "configure",
        "files": [{"path": str(outside), "existed": False}],
    }
    (backup_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="outside"):
        restore(backup_id)


def test_dry_run_then_real_configure_matches_plan(home: Path) -> None:
    cfg = Configurator(project_root=home)
    planned = cfg.configure(["claude-code"], scope="global", dry_run=True)
    planned_paths = {p["path"] for p in planned["results"][0]["plan"]}

    real = cfg.configure(["claude-code"], scope="global")
    real_files = set(real["results"][0]["files"])
    assert planned_paths == real_files
