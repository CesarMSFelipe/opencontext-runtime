"""Installation state tracking and backup/rollback system.

Tracks what components are installed, their versions, and provides
auto-backup before configuration changes.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from opencontext_core.user_prefs import UserConfigStore

# ── Installation State ─────────────────────────────────────────────────────


@dataclass
class ComponentState:
    """State of a single installed component."""

    id: str
    name: str
    version: str = "0.1.0"
    enabled: bool = True
    installed_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class InstallationState:
    """Tracks what's installed, versions, and timestamps."""

    # Components
    components: dict[str, ComponentState] = field(default_factory=dict)

    # Last operations
    last_sync: str = ""
    last_update_check: str = ""
    last_verified: str = ""

    # Plugin tracking
    plugins: dict[str, ComponentState] = field(default_factory=dict)

    # Agent configs
    configured_agents: list[str] = field(default_factory=list)

    # Version of the state schema
    schema_version: int = 1


# ── State Store ────────────────────────────────────────────────────────────


class StateStore:
    """Persistent store for installation state."""

    STATE_FILE = UserConfigStore.CONFIG_DIR / "state.json"

    @classmethod
    def ensure_dir(cls) -> None:
        UserConfigStore.CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def load(cls) -> InstallationState:
        """Load state from disk."""

        cls.ensure_dir()
        if cls.STATE_FILE.exists():
            try:
                data = json.loads(cls.STATE_FILE.read_text(encoding="utf-8"))
                # Reconstruct component states
                components = {}
                for cid, cdata in data.get("components", {}).items():
                    components[cid] = ComponentState(**cdata)
                plugins = {}
                for pid, pdata in data.get("plugins", {}).items():
                    plugins[pid] = ComponentState(**pdata)
                return InstallationState(
                    components=components,
                    plugins=plugins,
                    last_sync=data.get("last_sync", ""),
                    last_update_check=data.get("last_update_check", ""),
                    last_verified=data.get("last_verified", ""),
                    configured_agents=data.get("configured_agents", []),
                    schema_version=data.get("schema_version", 1),
                )
            except (json.JSONDecodeError, TypeError, KeyError):
                pass
        return InstallationState()

    @classmethod
    def save(cls, state: InstallationState) -> None:
        """Save state to disk."""

        cls.ensure_dir()
        data = {
            "components": {k: asdict(v) for k, v in state.components.items()},
            "plugins": {k: asdict(v) for k, v in state.plugins.items()},
            "last_sync": state.last_sync,
            "last_update_check": state.last_update_check,
            "last_verified": state.last_verified,
            "configured_agents": state.configured_agents,
            "schema_version": state.schema_version,
        }
        cls.STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def mark_component_installed(cls, component_id: str, name: str) -> None:
        """Mark a component as installed."""

        state = cls.load()
        now = datetime.now().isoformat()
        existing = state.components.get(component_id)
        if existing:
            existing.enabled = True
            existing.updated_at = now
        else:
            state.components[component_id] = ComponentState(
                id=component_id,
                name=name,
                installed_at=now,
                updated_at=now,
            )
        cls.save(state)

    @classmethod
    def mark_synced(cls) -> None:
        """Mark last sync time."""

        state = cls.load()
        state.last_sync = datetime.now().isoformat()
        cls.save(state)

    @classmethod
    def mark_verified(cls) -> None:
        """Mark last verification time."""

        state = cls.load()
        state.last_verified = datetime.now().isoformat()
        cls.save(state)


# ── Backup & Rollback ──────────────────────────────────────────────────────


@dataclass
class BackupEntry:
    """A single backup entry."""

    id: str
    timestamp: str
    description: str
    files: list[str] = field(default_factory=list)


class ConfigBackupManager:
    """Manages config-level backups before changes.

    NOTE: This is for user config (~/.config/opencontext/) backups.
    For project-level backups, use backup.BackupManager (.opencontext/backups/).
    """

    BACKUP_DIR = UserConfigStore.CONFIG_DIR / "backups"
    INDEX_FILE = BACKUP_DIR / "index.json"

    @classmethod
    def ensure_dir(cls) -> None:
        cls.BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def create_backup(cls, description: str = "pre-change") -> str:
        """Create a backup of current config files.

        Returns:
            Backup ID (timestamp-based).
        """

        cls.ensure_dir()
        timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        backup_id = f"backup-{timestamp}"
        backup_dir = cls.BACKUP_DIR / backup_id
        backup_dir.mkdir(exist_ok=True)

        files_backed_up: list[str] = []

        config_file = UserConfigStore.CONFIG_FILE
        if config_file.exists():
            shutil.copy2(str(config_file), str(backup_dir / "user-config.json"))
            files_backed_up.append("user-config.json")

        state_file = StateStore.STATE_FILE
        if state_file.exists():
            shutil.copy2(str(state_file), str(backup_dir / "state.json"))
            files_backed_up.append("state.json")

        # Update index
        index = cls._load_index()
        entry = BackupEntry(
            id=backup_id,
            timestamp=timestamp,
            description=description,
            files=files_backed_up,
        )
        index.insert(0, entry)  # newest first
        cls._save_index(index)

        return backup_id

    @classmethod
    def list_backups(cls) -> list[BackupEntry]:
        """List all backups, newest first."""

        return cls._load_index()

    @classmethod
    def restore_backup(cls, backup_id: str) -> bool:
        """Restore files from a backup.

        Returns:
            True if successful.
        """

        cls.ensure_dir()
        backup_dir = cls.BACKUP_DIR / backup_id
        if not backup_dir.exists():
            return False

        # Restore user config
        user_config_backup = backup_dir / "user-config.json"
        if user_config_backup.exists():
            shutil.copy2(str(user_config_backup), str(UserConfigStore.CONFIG_FILE))

        # Restore state
        state_backup = backup_dir / "state.json"
        if state_backup.exists():
            shutil.copy2(str(state_backup), str(StateStore.STATE_FILE))

        return True

    @classmethod
    def auto_backup(cls) -> str | None:
        """Auto-backup before changes. Only backs up if config exists.

        Returns:
            Backup ID or None if no backup needed.
        """

        if not UserConfigStore.CONFIG_FILE.exists() and not StateStore.STATE_FILE.exists():
            return None
        return cls.create_backup(description="auto-pre-change")

    @classmethod
    def _load_index(cls) -> list[BackupEntry]:
        """Load backup index."""

        cls.ensure_dir()
        if cls.INDEX_FILE.exists():
            try:
                data = json.loads(cls.INDEX_FILE.read_text(encoding="utf-8"))
                return [BackupEntry(**entry) for entry in data]
            except (json.JSONDecodeError, TypeError):
                pass
        return []

    @classmethod
    def _save_index(cls, index: list[BackupEntry]) -> None:
        """Save backup index, deduplicating by backup ID."""

        cls.ensure_dir()
        seen: set[str] = set()
        deduped: list[BackupEntry] = []
        for entry in index:
            if entry.id not in seen:
                seen.add(entry.id)
                deduped.append(entry)
        data = [asdict(entry) for entry in deduped]
        cls.INDEX_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
