"""SDD Profile management for per-phase model assignment.

Allows assigning different AI models to different SDD phases based on cost,
capability, or speed requirements.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from opencontext_core.config import SDDConfig


@dataclass
class SDDProfile:
    """A named SDD profile with per-phase model assignments."""

    name: str
    description: str = ""
    model_assignments: dict[str, str] = field(default_factory=dict)
    # Override specific config values
    artifact_store_mode: str = "engram"
    delivery_strategy: str = "plan_only"
    chain_strategy: str = "stacked_to_main"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""

        return {
            "name": self.name,
            "description": self.description,
            "model_assignments": self.model_assignments,
            "artifact_store_mode": self.artifact_store_mode,
            "delivery_strategy": self.delivery_strategy,
            "chain_strategy": self.chain_strategy,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SDDProfile:
        """Deserialize from dict."""

        return cls(
            name=data["name"],
            description=data.get("description", ""),
            model_assignments=data.get("model_assignments", {}),
            artifact_store_mode=data.get("artifact_store_mode", "engram"),
            delivery_strategy=data.get("delivery_strategy", "plan_only"),
            chain_strategy=data.get("chain_strategy", "stacked_to_main"),
        )


class SDDProfileManager:
    """Manages SDD profiles for per-phase model assignment.

    Profiles are stored in ~/.config/opencontext/profiles/ and can be
    activated per-project or globally.
    """

    DEFAULT_PROFILES: ClassVar[dict[str, SDDProfile]] = {
        "default": SDDProfile(
            name="default",
            description="Use default model for all phases",
            model_assignments={
                "explore": "default",
                "propose": "default",
                "spec": "default",
                "design": "default",
                "tasks": "default",
                "apply": "default",
                "verify": "default",
                "archive": "default",
            },
        ),
        "cheap": SDDProfile(
            name="cheap",
            description="Use fast/cheap models for exploration, premium for design",
            model_assignments={
                "explore": "openrouter/qwen/qwen3-30b-a3b:free",
                "propose": "openrouter/qwen/qwen3-30b-a3b:free",
                "spec": "openrouter/qwen/qwen3-30b-a3b:free",
                "design": "anthropic/claude-sonnet-4-20250514",
                "tasks": "openrouter/qwen/qwen3-30b-a3b:free",
                "apply": "openrouter/qwen/qwen3-30b-a3b:free",
                "verify": "anthropic/claude-sonnet-4-20250514",
                "archive": "openrouter/qwen/qwen3-30b-a3b:free",
            },
        ),
        "premium": SDDProfile(
            name="premium",
            description="Use strongest models for all phases",
            model_assignments={
                "explore": "anthropic/claude-opus-4",
                "propose": "anthropic/claude-opus-4",
                "spec": "anthropic/claude-opus-4",
                "design": "anthropic/claude-opus-4",
                "tasks": "anthropic/claude-sonnet-4-20250514",
                "apply": "anthropic/claude-sonnet-4-20250514",
                "verify": "anthropic/claude-opus-4",
                "archive": "anthropic/claude-sonnet-4-20250514",
            },
        ),
        "hybrid": SDDProfile(
            name="hybrid",
            description="Mix of cheap and premium models",
            model_assignments={
                "explore": "openrouter/qwen/qwen3-30b-a3b:free",
                "propose": "openrouter/qwen/qwen3-30b-a3b:free",
                "spec": "anthropic/claude-sonnet-4-20250514",
                "design": "anthropic/claude-opus-4",
                "tasks": "anthropic/claude-sonnet-4-20250514",
                "apply": "anthropic/claude-sonnet-4-20250514",
                "verify": "anthropic/claude-opus-4",
                "archive": "openrouter/qwen/qwen3-30b-a3b:free",
            },
        ),
    }

    def __init__(self, profiles_dir: str | Path | None = None) -> None:
        if profiles_dir is None:
            profiles_dir = Path.home() / ".config" / "opencontext" / "profiles"
        self.profiles_dir = Path(profiles_dir)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

        # Ensure default profiles exist
        self._ensure_defaults()

    def _ensure_defaults(self) -> None:
        """Create default profiles if they don't exist."""

        for name, profile in self.DEFAULT_PROFILES.items():
            path = self.profiles_dir / f"{name}.json"
            if not path.exists():
                path.write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")

    def list_profiles(self) -> list[dict[str, Any]]:
        """List all available profiles."""

        profiles = []
        for path in sorted(self.profiles_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                profiles.append(
                    {
                        "name": data.get("name", path.stem),
                        "description": data.get("description", ""),
                        "path": str(path),
                    }
                )
            except (json.JSONDecodeError, OSError):
                continue
        return profiles

    def get_profile(self, name: str) -> SDDProfile | None:
        """Get a profile by name."""

        path = self.profiles_dir / f"{name}.json"
        if not path.exists():
            # Check built-in defaults
            if name in self.DEFAULT_PROFILES:
                return self.DEFAULT_PROFILES[name]
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return SDDProfile.from_dict(data)
        except (json.JSONDecodeError, OSError):
            return None

    def create_profile(
        self,
        name: str,
        description: str = "",
        model_assignments: dict[str, str] | None = None,
    ) -> SDDProfile:
        """Create a new profile."""

        profile = SDDProfile(
            name=name,
            description=description,
            model_assignments=model_assignments or {},
        )
        path = self.profiles_dir / f"{name}.json"
        path.write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")
        return profile

    def delete_profile(self, name: str) -> bool:
        """Delete a profile."""

        path = self.profiles_dir / f"{name}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def apply_profile(self, name: str, config: SDDConfig) -> SDDConfig:
        """Apply a profile to an SDDConfig.

        Returns a new config with the profile's model assignments.
        """

        profile = self.get_profile(name)
        if profile is None:
            return config

        # Create new config with profile overrides
        new_config = config.model_copy(deep=True)
        new_config.model_assignments.update(profile.model_assignments)
        return new_config

    def get_model_for_phase(self, profile_name: str, phase: str) -> str:
        """Get the model assignment for a specific phase."""

        profile = self.get_profile(profile_name)
        if profile is None:
            return "default"
        return profile.model_assignments.get(phase, "default")
