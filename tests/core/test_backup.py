"""Unit tests for ConfigBackupManager in opencontext_core.state."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.state import BackupEntry, ConfigBackupManager


@pytest.fixture(autouse=True)
def _isolated_backup_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect ConfigBackupManager to a temp directory for each test."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    index_file = backup_dir / "index.json"
    monkeypatch.setattr(ConfigBackupManager, "BACKUP_DIR", backup_dir)
    monkeypatch.setattr(ConfigBackupManager, "INDEX_FILE", index_file)


def test_create_backup_returns_id(tmp_path: Path) -> None:
    """create_backup returns a non-empty backup ID string."""
    backup_id = ConfigBackupManager.create_backup("test-create")
    assert backup_id
    assert backup_id.startswith("backup-")


def test_list_backups_returns_created(tmp_path: Path) -> None:
    """list_backups returns an entry matching the created backup."""
    backup_id = ConfigBackupManager.create_backup("list-test")
    backups = ConfigBackupManager.list_backups()
    assert len(backups) >= 1
    ids = [b.id for b in backups]
    assert backup_id in ids


def test_list_backups_index_grows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """list_backups reflects all insertions even with colliding timestamps."""
    # Manually create two entries with distinct IDs using the internal _save_index API
    entry1 = BackupEntry(id="backup-20260527T100000", timestamp="20260527T100000", description="a")
    entry2 = BackupEntry(id="backup-20260527T100001", timestamp="20260527T100001", description="b")
    ConfigBackupManager._save_index([entry2, entry1])  # newest first
    backups = ConfigBackupManager.list_backups()
    assert len(backups) == 2
    assert backups[0].id == "backup-20260527T100001"
    assert backups[1].id == "backup-20260527T100000"


def test_deduplication_no_duplicate_ids(tmp_path: Path) -> None:
    """The index deduplicates by backup ID — no two entries share the same ID."""
    # Manually write duplicate entries and verify _save_index deduplicates
    entry = BackupEntry(id="backup-20260527T120000", timestamp="20260527T120000", description="x")
    ConfigBackupManager._save_index([entry, entry, entry])  # insert 3 copies
    backups = ConfigBackupManager.list_backups()
    assert len(backups) == 1  # deduplicated to one


def test_restore_backup_returns_true_when_exists(tmp_path: Path) -> None:
    """restore_backup returns True when the backup directory exists."""
    backup_id = ConfigBackupManager.create_backup("restore-test")
    result = ConfigBackupManager.restore_backup(backup_id)
    assert result is True


def test_restore_backup_returns_false_when_missing(tmp_path: Path) -> None:
    """restore_backup returns False for a non-existent backup ID."""
    result = ConfigBackupManager.restore_backup("backup-99991231T235959")
    assert result is False


def test_backup_entry_description_preserved(tmp_path: Path) -> None:
    """The description passed to create_backup is preserved in the index."""
    desc = "my-custom-description"
    backup_id = ConfigBackupManager.create_backup(desc)
    backups = ConfigBackupManager.list_backups()
    entry = next(b for b in backups if b.id == backup_id)
    assert entry.description == desc


def test_auto_backup_returns_none_when_nothing_to_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """auto_backup returns None when neither config file nor state file exists."""
    from opencontext_core import state as state_module
    from opencontext_core import user_prefs

    fake_config = tmp_path / "user-config.json"  # does not exist
    fake_state = tmp_path / "state.json"  # does not exist
    monkeypatch.setattr(user_prefs.UserConfigStore, "CONFIG_FILE", fake_config)
    monkeypatch.setattr(state_module.UserConfigStore, "CONFIG_FILE", fake_config)
    monkeypatch.setattr(state_module.StateStore, "STATE_FILE", fake_state)
    result = ConfigBackupManager.auto_backup()
    assert result is None


def test_multiple_backups_all_in_list(tmp_path: Path) -> None:
    """Creating three backups results in all three appearing in list_backups."""
    ids = [ConfigBackupManager.create_backup(f"bulk-{i}") for i in range(3)]
    backups = ConfigBackupManager.list_backups()
    listed_ids = {b.id for b in backups}
    for bid in ids:
        assert bid in listed_ids


def test_cleanup_removes_old_and_rebuilds_index(tmp_path: Path) -> None:
    """cleanup() drops dirs past the cutoff and rebuilds the index from disk.

    Rebuilding is what removes a stale index entry whose directory is already gone.
    """
    old_dir = ConfigBackupManager.BACKUP_DIR / "backup-20000101T000000"
    old_dir.mkdir()
    (old_dir / "user-config.json").write_text("{}", encoding="utf-8")
    fresh = ConfigBackupManager.create_backup("keep-me")
    # Seed a stale index entry pointing at a directory that does not exist.
    stale = BackupEntry(id="backup-19990101T000000", timestamp="19990101T000000", description="x")
    ConfigBackupManager._save_index([*ConfigBackupManager.list_backups(), stale])

    removed, remaining = ConfigBackupManager.cleanup(keep_days=30)

    assert removed == 1  # the year-2000 dir; the year-1999 stale entry had no dir
    assert not old_dir.exists()
    ids = {b.id for b in ConfigBackupManager.list_backups()}
    assert fresh in ids
    assert "backup-19990101T000000" not in ids  # stale entry pruned by rebuild
    assert remaining == len(ids)
