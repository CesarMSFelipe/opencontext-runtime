"""User preferences and configuration persistence.

Stores user choices from the setup wizard and allows reconfiguration.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def _default_config_dir() -> Path:
    """Platform-appropriate default config directory.

    On Windows uses %APPDATA%; on Linux/macOS uses XDG_CONFIG_HOME or ~/.config.
    The Linux/macOS convention (Path.home() / ".config" / "opencontext") stays
    consistent for existing users; only Windows diverges to APPDATA.
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        # Linux / macOS — keep existing convention: ~/.config/opencontext
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "opencontext"


@dataclass
class UserFeatures:
    """Feature toggles chosen by the user."""

    knowledge_graph: bool = True
    embeddings: bool = False
    mcp_server: bool = True
    learning_system: bool = True
    governance: bool = True
    git_integration: bool = True
    semantic_search: bool = False
    call_graph: bool = True


@dataclass
class SDDPreferences:
    """SDD/TDD workflow preferences."""

    tdd_mode: str = "ask"
    sdd_model_profile: str = "hybrid"
    orchestrator_profile: str = "multi-phase"
    token_budget_per_phase: dict[str, int] = field(
        default_factory=lambda: {
            "explore": 6000,
            "propose": 6000,
            "apply": 12000,
            "verify": 4000,
            "review": 4000,
            "archive": 2000,
        }
    )


@dataclass
class AgentPreferences:
    """Agent client preferences."""

    active_clients: list[str] = field(default_factory=lambda: ["opencode"])
    default_client: str = "opencode"
    agent_files_generated: bool = False
    mcp_configured: bool = False


@dataclass
class UserPreferences:
    """Persisted user preferences for OpenContext."""

    # Installation metadata
    version: str = "0.1.0"
    first_run: bool = True
    install_date: str = ""

    # Security
    security_mode: str = "private_project"
    data_classification: str = "internal"

    # Features
    features: UserFeatures = field(default_factory=UserFeatures)

    # SDD/TDD workflow
    sdd: SDDPreferences = field(default_factory=SDDPreferences)

    # Agent clients
    agents: AgentPreferences = field(default_factory=AgentPreferences)

    # Token budgets
    default_token_budget: int = 10000
    max_input_tokens: int = 12000
    reserve_output_tokens: int = 1500

    # Provider settings
    default_provider: str = "mock"
    default_model: str = "mock-llm"
    custom_providers: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Plugins
    enabled_plugins: list[str] = field(default_factory=list)
    installed_plugins: list[str] = field(default_factory=list)

    # Agent integrations (legacy flat map kept for backward compat)
    agent_integrations: dict[str, bool] = field(
        default_factory=lambda: {
            "opencode": True,
            "claude-code": False,
            "cursor": False,
            "windsurf": False,
            "kilo-code": False,
            "gemini-cli": False,
            "vscode-copilot": False,
            "antigravity": False,
            "kimi-code": False,
            "kiro-ide": False,
            "qwen-code": False,
            "codex": False,
            "openclaw": False,
            "pi": False,
        }
    )

    # SDD/TDD interaction defaults (legacy flat fields kept for backward compat)
    active_agent: str = "opencode"
    sdd_tdd_mode: str = "ask"
    sdd_token_budget: int = 3000
    sdd_model_profile: str = "default"
    setup_completed: bool = False

    # Paths
    custom_storage_path: str = ".storage/opencontext"
    custom_workspace_path: str = ".opencontext"

    # Learning
    learning_auto_optimize: bool = True
    learning_share_anonymous: bool = False

    # Updates
    check_updates: bool = True
    auto_update_plugins: bool = False


class UserConfigStore:
    """Persistent store for user preferences."""

    CONFIG_DIR = _default_config_dir()
    CONFIG_FILE = CONFIG_DIR / "user-config.json"

    def __init__(self) -> None:
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._preferences: UserPreferences | None = None

    def load(self) -> UserPreferences:
        """Load preferences from disk."""

        if self._preferences is not None:
            return self._preferences

        if self.CONFIG_FILE.exists():
            try:
                data = json.loads(self.CONFIG_FILE.read_text(encoding="utf-8"))
                features_data = data.pop("features", {})
                sdd_data = data.pop("sdd", {})
                agents_data = data.pop("agents", {})
                features = UserFeatures(**{k: v for k, v in features_data.items() if k in UserFeatures.__dataclass_fields__})
                sdd = SDDPreferences(**{k: v for k, v in sdd_data.items() if k in SDDPreferences.__dataclass_fields__})
                agents = AgentPreferences(**{k: v for k, v in agents_data.items() if k in AgentPreferences.__dataclass_fields__})
                known = set(UserPreferences.__dataclass_fields__) - {"features", "sdd", "agents"}
                filtered = {k: v for k, v in data.items() if k in known}
                self._preferences = UserPreferences(**filtered, features=features, sdd=sdd, agents=agents)
                return self._preferences
            except (json.JSONDecodeError, TypeError):
                pass

        self._preferences = UserPreferences()
        return self._preferences

    def save(self, preferences: UserPreferences | None = None) -> None:
        """Save preferences to disk. Creates auto-backup before overwriting."""

        if preferences is not None:
            self._preferences = preferences
        elif self._preferences is None:
            self._preferences = UserPreferences()

        # Auto-backup before overwriting existing config
        if self.CONFIG_FILE.exists():
            try:
                from opencontext_core.state import ConfigBackupManager

                ConfigBackupManager.auto_backup()
            except ImportError:
                pass

        data = asdict(self._preferences)
        self.CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def update(self, **kwargs: Any) -> None:
        """Update specific fields."""

        prefs = self.load()
        for key, value in kwargs.items():
            if hasattr(prefs, key):
                setattr(prefs, key, value)
        self.save(prefs)

    def is_first_run(self) -> bool:
        """Check if this is the first run."""

        prefs = self.load()
        return prefs.first_run

    def mark_configured(self) -> None:
        """Mark as configured (no longer first run)."""

        prefs = self.load()
        prefs.first_run = False
        from datetime import datetime

        prefs.install_date = datetime.now().isoformat()
        self.save(prefs)

    def reset(self) -> None:
        """Reset to defaults."""

        self._preferences = UserPreferences()
        self.save()
