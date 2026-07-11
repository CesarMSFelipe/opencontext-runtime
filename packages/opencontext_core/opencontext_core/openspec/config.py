"""OpenSpecConfig — governance model for openspec/config.yaml.

``extra='forbid'`` rejects unknown keys so config drift fails loud at load.
``load_optional`` returns ``None`` when the file is absent — callers decide
whether absence is fatal.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, field_validator

from opencontext_core.compat import coerce_yaml_off


class TDDSection(BaseModel):
    """TDD enforcement configuration."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["off", "lite", "strict"] = "strict"
    """strict = RED-first enforced; lite = test-required but not RED-first; off = advisory."""

    @field_validator("mode", mode="before")
    @classmethod
    def _coerce_yaml_off(cls, value: Any) -> Any:
        # YAML "Norway problem": a hand-authored ``mode: off`` in openspec/config.yaml
        # parses as ``False``; coerce it back so config load does not crash.
        return coerce_yaml_off(value)


class QualityGatesSection(BaseModel):
    """Per-gate toggles. All default to enabled."""

    model_config = ConfigDict(extra="forbid")

    requirements: bool = True
    tasks: bool = True
    evidence: bool = True


class OpenSpecConfig(BaseModel):
    """Top-level openspec config model. ``extra='forbid'`` is strict."""

    model_config = ConfigDict(extra="forbid")

    tdd: TDDSection = TDDSection()
    quality_gates: QualityGatesSection = QualityGatesSection()

    @classmethod
    def load_optional(cls, path: str | Path) -> OpenSpecConfig | None:
        """Load config from ``path`` if it exists, else return ``None``.

        Raises ``ValidationError`` if the file exists but is malformed or
        contains unknown keys.
        """
        p = Path(path)
        if not p.exists():
            return None
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return cls.model_validate(data)
