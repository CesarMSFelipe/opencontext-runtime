"""Mirror runtime-affecting user preferences into the project's opencontext.yaml.

The runtime reads ``opencontext.yaml``, not the user-prefs file, so a setting
changed via ``config set`` or the wizard would otherwise never take effect. This
keeps the two in sync for the handful of settings that actually change runtime
behavior, validating the patched config and reverting on failure so a bad value
can never corrupt the project config. Settings with no runtime mapping stay
user-prefs-only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# user-prefs dotted path -> opencontext.yaml dotted path (runtime-affecting only).
RUNTIME_PREF_TO_YAML: dict[str, str] = {
    "security_mode": "security.mode",
    "features.embeddings": "embedding.enabled",
    "features.mcp_server": "tools.mcp.enabled",
    "features.semantic_search": "cache.semantic.enabled",
    "features.knowledge_graph": "knowledge_graph.enabled",
    "features.call_graph": "knowledge_graph.track_call_sites",
    "default_provider": "models.default.provider",
    "default_model": "models.default.model",
}


def sync_pref_to_yaml(pref_key: str, value: object, *, root: str | Path = ".") -> bool:
    """Patch the yaml path mapped to ``pref_key`` with ``value``. Return True if applied.

    No-ops for unmapped keys or when no project config exists. Validates the
    result loads and reverts on failure (never corrupts the file).
    """
    yaml_path = RUNTIME_PREF_TO_YAML.get(pref_key)
    if yaml_path is None:
        return False

    from opencontext_core.config import find_config, load_config

    config_file = find_config(str(root))
    if config_file is None or not config_file.exists():
        return False

    import yaml

    original = config_file.read_text(encoding="utf-8")
    try:
        data: dict[str, Any] = yaml.safe_load(original) or {}
        cursor = data
        parts = yaml_path.split(".")
        for part in parts[:-1]:
            nxt = cursor.get(part)
            if not isinstance(nxt, dict):
                nxt = {}
                cursor[part] = nxt
            cursor = nxt
        cursor[parts[-1]] = value
        config_file.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        load_config(config_file)  # raises if the value is invalid
        return True
    except Exception:
        config_file.write_text(original, encoding="utf-8")  # revert
        return False


def _resolve_pref(prefs: Any, dotted: str) -> tuple[bool, object]:
    obj = prefs
    for part in dotted.split("."):
        if not hasattr(obj, part):
            return False, None
        obj = getattr(obj, part)
    return True, obj


def sync_runtime_prefs_to_yaml(prefs: Any, *, root: str | Path = ".") -> list[str]:
    """Sync every mapped runtime pref from ``prefs`` into opencontext.yaml.

    Returns the list of yaml paths actually applied (empty when there is no
    project config or nothing mapped resolved).
    """
    applied: list[str] = []
    for pref_key, yaml_path in RUNTIME_PREF_TO_YAML.items():
        found, value = _resolve_pref(prefs, pref_key)
        if found and sync_pref_to_yaml(pref_key, value, root=root):
            applied.append(yaml_path)
    return applied
