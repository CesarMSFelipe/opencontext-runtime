"""Extension manifest model — schema for community workflow extensions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExtensionManifest(BaseModel):
    """Validated manifest for an OpenContext workflow extension."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Extension identifier (kebab-case).")
    version: str = Field(description="SemVer string, e.g. '1.0.0'.")
    description: str = Field(default="", description="Short description.")
    author: str = Field(default="", description="Author or organization name.")
    tags: list[str] = Field(default_factory=list, description="Searchable tags.")
    requires_version: str = Field(
        default="",
        description="Minimum opencontext-core version required.",
    )

    @field_validator("name")
    @classmethod
    def name_must_be_kebab(cls, v: str) -> str:
        if not v or not all(c.isalnum() or c == "-" for c in v):
            msg = f"Extension name must be kebab-case alphanumeric: {v!r}"
            raise ValueError(msg)
        return v

    @field_validator("version")
    @classmethod
    def version_must_be_semver(cls, v: str) -> str:
        parts = v.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            msg = f"Extension version must be SemVer (X.Y.Z): {v!r}"
            raise ValueError(msg)
        return v

    @classmethod
    def from_yaml(cls, path: Path | str) -> ExtensionManifest:
        """Load and validate an extension manifest from a YAML file."""
        import yaml

        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExtensionManifest:
        """Construct and validate a manifest from a dict."""
        return cls.model_validate(data)
