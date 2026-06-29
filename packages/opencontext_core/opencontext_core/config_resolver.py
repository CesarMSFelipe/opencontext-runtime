"""Seven-level configuration resolver (PR-013, SPEC-CLI-013-03).

Resolves the effective :class:`OpenContextConfig` by layering, in order (later
wins):

1. built-in defaults        (``default_config_data``)
2. profile defaults         (``config_profiles.get_profile``)
3. global user config        (``~/.opencontext/config.yaml``, if present)
4. project config            (the project ``opencontext.yaml``)
5. environment variables     (``OPENCONTEXT_*``)
6. CLI / MCP request overrides
7. runtime policy decisions

Returns ``(config, provenance)`` where ``provenance`` records, per top-level
key, which layer last set it — so a run can explain *why* a value is what it is
and an env override is auditable.

This module composes ``config.py``'s ``_deep_merge`` /
``_normalize_legacy_config`` rather than re-implementing them, keeping
``load_config`` a pure file→model step.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from opencontext_core.config import (
    OpenContextConfig,
    _deep_merge,
    _normalize_legacy_config,
    default_config_data,
    find_config,
)
from opencontext_core.config_profiles import BUILTIN_PROFILES, DEFAULT_PROFILE

# Ordered layer names (lowest precedence first). Public so callers/tests can
# assert ordering without hard-coding strings.
LAYERS: tuple[str, ...] = (
    "defaults",
    "profile",
    "global",
    "project",
    "env",
    "overrides",
    "policy",
)

# Environment-variable → dotted-config-path mapping. Kept small and explicit;
# the most load-bearing knob is the profile selector.
_ENV_MAP: dict[str, str] = {
    "OPENCONTEXT_PROFILE": "profile",
    "OPENCONTEXT_SECURITY_MODE": "security.mode",
    "OPENCONTEXT_PROVIDER_STRATEGY": "providers.strategy",
    "OPENCONTEXT_UI_LANGUAGE": "ui_language",
}


@dataclass
class ResolutionProvenance:
    """Records which layer set each top-level config key, plus profile origin."""

    by_key: dict[str, str] = field(default_factory=dict)
    profile: str = DEFAULT_PROFILE
    profile_layer: str = "defaults"

    def layer_of(self, key: str) -> str:
        """Return the winning layer for *key* (``"defaults"`` if unseen)."""
        return self.by_key.get(key, "defaults")


@dataclass
class ResolvedConfig:
    """The resolved config plus its provenance and the merged raw dict."""

    config: OpenContextConfig
    provenance: ResolutionProvenance
    profile: str
    data: dict[str, Any]


def _set_dotted(target: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    node = target
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value


def _env_overrides(env: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for var, dotted in _ENV_MAP.items():
        if var in env and env[var] != "":
            _set_dotted(out, dotted, env[var])
    return out


def _load_yaml(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}
    return raw if isinstance(raw, dict) else {}


def _global_config_path() -> Path:
    return Path.home() / ".opencontext" / "config.yaml"


def _pick_profile(layers: list[tuple[str, dict[str, Any]]]) -> tuple[str, str]:
    """Return ``(profile_name, winning_layer)`` from the non-profile layers.

    Scans from highest precedence to lowest so an env/override/policy ``profile``
    beats a project-file ``profile`` (the SPEC-CLI-013-03 scenario).
    """
    for name, data in reversed(layers):
        if name == "profile":
            continue
        candidate = data.get("profile")
        if isinstance(candidate, str) and candidate:
            return candidate, name
    return DEFAULT_PROFILE, "defaults"


def resolve(
    project_path: str | Path | None = None,
    *,
    env: dict[str, str] | None = None,
    cli_overrides: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
    global_config: dict[str, Any] | None = None,
) -> ResolvedConfig:
    """Resolve the effective config over the seven documented layers."""
    env = dict(os.environ if env is None else env)
    cli_overrides = dict(cli_overrides or {})
    policy = dict(policy or {})

    project_file: Path | None = None
    if project_path is not None:
        candidate = Path(project_path)
        if candidate.is_dir():
            project_file = candidate / "opencontext.yaml"
            if not project_file.exists():
                project_file = find_config(candidate)
        else:
            project_file = candidate
    else:
        project_file = find_config(Path.cwd())

    project_raw = _normalize_legacy_config(_load_yaml(project_file))
    global_raw = global_config if global_config is not None else _load_yaml(_global_config_path())
    env_raw = _env_overrides(env)

    # First pass (without profile) to determine the effective profile selection,
    # honouring precedence (overrides/policy/env beat project).
    selection_layers: list[tuple[str, dict[str, Any]]] = [
        ("global", global_raw),
        ("project", project_raw),
        ("env", env_raw),
        ("overrides", cli_overrides),
        ("policy", policy),
    ]
    profile_name, profile_layer = _pick_profile(selection_layers)
    if profile_name not in BUILTIN_PROFILES:
        # Unknown profile: fall back to default but keep the requested name in
        # provenance so config_doctor can flag it.
        profile_overlay: dict[str, Any] = {}
    else:
        from opencontext_core.config_profiles import get_profile

        profile_overlay = get_profile(profile_name)

    # ``profile`` is a real OpenContextConfig field, so the effective profile name
    # is carried into the merged config (the selected overlay is layer 2).
    ordered: list[tuple[str, dict[str, Any]]] = [
        ("defaults", {**default_config_data(), "profile": profile_name}),
        ("profile", profile_overlay),
        ("global", global_raw),
        ("project", project_raw),
        ("env", env_raw),
        ("overrides", cli_overrides),
        ("policy", policy),
    ]

    provenance = ResolutionProvenance(profile=profile_name, profile_layer=profile_layer)
    merged: dict[str, Any] = {}
    for layer_name, data in ordered:
        if not data:
            continue
        for key in data:
            provenance.by_key[key] = layer_name
        merged = _deep_merge(merged, data)

    config = OpenContextConfig.model_validate(merged)
    return ResolvedConfig(
        config=config, provenance=provenance, profile=profile_name, data=merged
    )


def resolve_config_path(root: str | Path, explicit: str | Path | None = None) -> Path:
    """Resolve THE single config path every entry point loads (B2 / ADR-A2).

    Precedence (highest first):

    1. explicit ``--config <path>``
    2. ``<root>/opencontext.yaml`` — the canonical location ``install`` writes
    3. parent-directory search from *root* (:func:`find_config`)
    4. canonical ``<root>/opencontext.yaml`` as the built-in-defaults fallback
       (the path does not exist; the loader falls back to defaults)

    Always returns a path so callers can pass it straight to
    ``load_config_or_defaults(path, auto_detect=False)`` — the loader treats a
    non-existent path as the zero-config (built-in defaults) case. ``install``
    and ``run`` MUST share this function so the writer and reader can never
    diverge (the B2/AVH-012 defect). Use :func:`missing_config_hint` to render an
    actionable message when the resolved path does not exist.
    """
    if explicit:
        return Path(explicit)
    root_path = Path(root)
    canonical = root_path / "opencontext.yaml"
    if canonical.exists():
        return canonical
    found = find_config(root_path)
    if found is not None:
        return found
    return canonical


def missing_config_hint(root: str | Path) -> str:
    """Actionable message naming the expected path when no config resolves (B2)."""
    canonical = Path(root) / "opencontext.yaml"
    return (
        f"No OpenContext config found (expected {canonical}). "
        "Run 'opencontext init' to create one, or pass --config <path>."
    )
