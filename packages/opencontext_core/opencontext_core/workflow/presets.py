"""Workflow preset system — 3-tier preset resolution and composition."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml as _yaml
except ImportError:
    _yaml = None  # type: ignore[assignment]


@dataclass
class Preset:
    """A named configuration preset that can be applied to a base config."""

    name: str
    description: str = ""
    base: dict[str, Any] = field(default_factory=dict)
    strategy: str = "replace"  # replace | prepend | append | wrap


BUILTIN_PRESETS: dict[str, Preset] = {
    "strict-tdd": Preset(
        name="strict-tdd",
        description="Enforce strict TDD mode across all SDD phases.",
        base={"sdd": {"tdd_mode": "strict"}},
        strategy="replace",
    ),
    "air-gapped": Preset(
        name="air-gapped",
        description="Disable external providers and semantic cache.",
        base={"security": {"mode": "air_gapped", "external_providers_enabled": False}},
        strategy="replace",
    ),
    "cheap": Preset(
        name="cheap",
        description="Use budget model profile to minimize token usage.",
        base={"sdd": {"sdd_model_profile": "cheap"}},
        strategy="replace",
    ),
    "premium": Preset(
        name="premium",
        description="Use premium model profile for highest quality outputs.",
        base={"sdd": {"sdd_model_profile": "premium"}},
        strategy="replace",
    ),
    "fast": Preset(
        name="fast",
        description="Low-latency mode: cheap model, reduced token budget, skip heavy compression.",
        base={
            "sdd": {"sdd_model_profile": "cheap"},
            "context": {"max_input_tokens": 2000},
            "output": {"max_output_tokens": 600},
        },
        strategy="replace",
    ),
    "deep": Preset(
        name="deep",
        description="Maximum quality: premium model, large token budget, all features enabled.",
        base={
            "sdd": {"sdd_model_profile": "premium"},
            "context": {"max_input_tokens": 8000},
            "output": {"max_output_tokens": 2000},
        },
        strategy="replace",
    ),
    "privacy": Preset(
        name="privacy",
        description=(
            "Maximum privacy: air-gapped, no external providers, aggressive secret redaction."
        ),
        base={
            "security": {
                "mode": "air_gapped",
                "external_providers_enabled": False,
                "fail_closed": True,
            },
            "providers": {"external_enabled": False},
        },
        strategy="replace",
    ),
}


def find_presets(root: str | Path = ".") -> list[Preset]:
    """Discover presets from 4 tiers: project, extensions, shared, and built-in core.

    Search order (highest to lowest priority):
    1. <root>/.opencontext/presets/*.yaml           (project overrides)
    2. <root>/.opencontext/extensions/*/presets/    (installed extensions)
    3. openspec/presets/*.yaml                      (shared presets)
    4. Built-in core presets
    """
    presets: dict[str, Preset] = {}

    search_dirs: list[Path] = [
        Path(root) / ".opencontext" / "presets",
    ]

    # Include presets from every installed extension
    extensions_base = Path(root) / ".opencontext" / "extensions"
    if extensions_base.exists():
        for ext_dir in sorted(extensions_base.iterdir()):
            ext_presets = ext_dir / "presets"
            if ext_presets.is_dir():
                search_dirs.append(ext_presets)

    search_dirs.append(Path("openspec") / "presets")

    yaml_mod: Any = _yaml
    if yaml_mod is None:
        import yaml as _yaml_anon

        yaml_mod = _yaml_anon
    for preset_dir in search_dirs:
        if not preset_dir.exists():
            continue
        for f in sorted(preset_dir.glob("*.yaml")):
            try:
                data = yaml_mod.safe_load(f.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    continue
                name = str(data.get("name", f.stem))
                presets.setdefault(
                    name,
                    Preset(
                        name=name,
                        description=str(data.get("description", "")),
                        base=data.get("base", {}),
                        strategy=str(data.get("strategy", "replace")),
                    ),
                )
            except Exception:
                pass

    for name, preset in BUILTIN_PRESETS.items():
        presets.setdefault(name, preset)

    return list(presets.values())


def load_preset(name: str, root: str | Path = ".") -> Preset | None:
    """Load a specific preset by name. Returns None if not found."""
    for preset in find_presets(root):
        if preset.name == name:
            return preset
    return None


def compose(base: dict[str, Any], preset: Preset) -> dict[str, Any]:
    """Apply a preset to a base config dict using the preset's strategy.

    Strategies:
    - replace: update base with preset.base keys (default)
    - prepend: for list values, prepend preset list before base list
    - append:  for list values, append preset list after base list
    - wrap:    alias for replace (deep merge not yet supported)
    """
    result = copy.deepcopy(base)

    if preset.strategy in ("replace", "wrap"):
        _deep_merge(result, preset.base)
    elif preset.strategy == "prepend":
        for k, v in preset.base.items():
            if k in result and isinstance(result[k], list) and isinstance(v, list):
                result[k] = list(v) + list(result[k])
            else:
                result[k] = v
    elif preset.strategy == "append":
        for k, v in preset.base.items():
            if k in result and isinstance(result[k], list) and isinstance(v, list):
                result[k] = list(result[k]) + list(v)
            else:
                result[k] = v
    else:
        _deep_merge(result, preset.base)

    return result


def _deep_merge(target: dict[str, Any], source: dict[str, Any]) -> None:
    """Recursively merge source into target in-place."""
    for k, v in source.items():
        if k in target and isinstance(target[k], dict) and isinstance(v, dict):
            _deep_merge(target[k], v)
        else:
            target[k] = v
