"""Effective-config explanation behind ``opencontext config explain`` (plan §6).

Builds the machine-readable payload ``{effective_config, sources, conflicts,
deprecated_keys, unknown_keys, validation}`` on top of the layered resolver
(:mod:`opencontext_core.config_resolver`). Per dotted key, ``sources`` names the
winning layer, the file that supplied it (when file-based) and a best-effort
line number. Secret-looking values are masked before anything is returned.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from opencontext_core.config import OpenContextConfig, _normalize_legacy_config
from opencontext_core.config_doctor import find_deprecated_keys
from opencontext_core.config_resolver import (
    _global_config_path,
    dotted_leaves,
    resolve,
    resolve_org_config_file,
    resolve_project_config_file,
)
from opencontext_core.errors import ConfigurationError

SECRET_MASK = "***"

# A leaf key with a credential-shaped final segment never prints its value.
# Deliberately anchored so budget knobs like ``max_input_tokens`` stay visible.
_SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|access[_-]?key|private[_-]?key|secret|password|passwd|credential"
    r"|(?:^|[_-])token$|(?:^|[_-])key$)",
    re.IGNORECASE,
)


def is_secret_key(dotted: str) -> bool:
    """True when the final segment of *dotted* looks like a credential."""
    return bool(_SECRET_KEY_RE.search(dotted.rsplit(".", 1)[-1]))


# Pydantic embeds the offending raw value as ``input_value=<repr>, input_type=...``
# in its validation message. When that value (or its config key) is a credential,
# the CONFIG_INVALID envelope would echo the secret verbatim.
_INPUT_VALUE_RE = re.compile(r"input_value=(?P<value>.*?)(?=, input_type=|$)", re.MULTILINE)

# A bare token with a classic secret prefix (short keys the full scanner's
# length thresholds would miss, e.g. a 16-character ``sk-`` value).
_SECRET_VALUE_PREFIX_RE = re.compile(r"^(?:sk|rk|pk)[-_][A-Za-z0-9_\-]{6,}", re.IGNORECASE)

# Quoted keys inside a dict repr (``{'api_key': '...'}``) echoed as input_value.
_QUOTED_KEY_RE = re.compile(r"['\"]([A-Za-z0-9_\-]+)['\"]\s*:")

# A pydantic error-location line: an unindented dotted key path.
_LOC_LINE_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]*$")


def redact_secret_input_values(message: str) -> str:
    """Mask pydantic ``input_value=...`` payloads that look credential-shaped.

    CONFIG_INVALID envelopes (and the human stderr path) embed pydantic's
    validation message verbatim. When the offending key path matches
    :func:`is_secret_key` or the echoed value itself looks like a secret, the
    payload is replaced with :data:`SECRET_MASK`; the rest of the message stays
    intact so the error remains actionable.
    """

    def _replace(match: re.Match[str]) -> str:
        value = match.group("value")
        if _input_value_looks_secret(value) or _loc_is_secret(message[: match.start()]):
            return f"input_value={SECRET_MASK}"
        return match.group(0)

    return _INPUT_VALUE_RE.sub(_replace, message)


def _input_value_looks_secret(value: str) -> bool:
    """True when an echoed ``input_value`` payload looks credential-shaped."""
    stripped = value.strip().strip("'\"")
    if _SECRET_VALUE_PREFIX_RE.match(stripped):
        return True
    if any(is_secret_key(m.group(1)) for m in _QUOTED_KEY_RE.finditer(value)):
        return True
    try:
        from opencontext_core.safety.secrets import SecretScanner

        return bool(SecretScanner().scan(value))
    except Exception:
        return False


def _loc_is_secret(preceding: str) -> bool:
    """True when the nearest pydantic error-location line names a secret key."""
    for line in reversed(preceding.splitlines()):
        candidate = line.strip()
        if not candidate:
            continue
        if line[:1].isspace():
            continue  # indented detail lines; the loc line is unindented
        return bool(_LOC_LINE_RE.match(candidate) and is_secret_key(candidate))
    return False


def _mask_tree(data: Any, prefix: str = "") -> Any:
    """Return a copy of *data* with secret-keyed values replaced by the mask."""
    if not isinstance(data, dict):
        return data
    masked: dict[str, Any] = {}
    for key, value in data.items():
        dotted = f"{prefix}{key}"
        if is_secret_key(dotted):
            masked[key] = SECRET_MASK
        else:
            masked[key] = _mask_tree(value, f"{dotted}.")
    return masked


def _line_of_key(lines: list[str], dotted: str) -> int | None:
    """Best-effort 1-based line of the key's final segment in a YAML source."""
    segment = dotted.rsplit(".", 1)[-1]
    pattern = re.compile(rf"^\s*-?\s*['\"]?{re.escape(segment)}['\"]?\s*:")
    for number, line in enumerate(lines, start=1):
        if pattern.match(line):
            return number
    return None


def _load_yaml_strict(path: Path) -> dict[str, Any]:
    """Parse *path* or raise :class:`ConfigurationError` (envelope at CLI layer)."""
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ConfigurationError(f"Configuration root must be a mapping: {path}")
    return loaded


def explain(
    project_path: str | Path | None = None,
    *,
    env: dict[str, str] | None = None,
    cli_overrides: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
    global_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Explain the effective config: value, source layer, file, and line per key.

    Raises :class:`ConfigurationError` for an unparseable config or one that
    fails schema validation; unknown/deprecated keys degrade to warnings so the
    rest of the resolution stays explainable.
    """
    project_file = resolve_project_config_file(project_path)
    raw_project: dict[str, Any] = {}
    project_lines: list[str] = []
    if project_file is not None and project_file.exists():
        project_lines = project_file.read_text(encoding="utf-8").splitlines()
        raw_project = _load_yaml_strict(project_file)

    deprecated = find_deprecated_keys(raw_project)
    normalized = _normalize_legacy_config(raw_project)
    known = set(OpenContextConfig.model_fields)
    unknown = sorted(k for k in normalized if k not in known)
    known_only = {k: v for k, v in normalized.items() if k in known}

    global_path = _global_config_path()
    global_lines: list[str] = []
    if global_config is None:
        if global_path.exists():
            global_lines = global_path.read_text(encoding="utf-8").splitlines()
            raw_global = _load_yaml_strict(global_path)
        else:
            raw_global = {}
    else:
        raw_global = dict(global_config)
    global_known = {k: v for k, v in raw_global.items() if k in known}

    effective_env = dict(os.environ if env is None else env)
    org_path = resolve_org_config_file(effective_env, raw_global)
    org_lines: list[str] = []
    raw_org: dict[str, Any] = {}
    if org_path is not None and org_path.exists():
        org_lines = org_path.read_text(encoding="utf-8").splitlines()
        raw_org = _load_yaml_strict(org_path)
    org_known = {k: v for k, v in raw_org.items() if k in known}

    try:
        resolved = resolve(
            project_path,
            env=env,
            cli_overrides=cli_overrides,
            policy=policy,
            global_config=global_known,
            project_config=known_only,
            org_config=org_known,
        )
    except ConfigurationError:
        raise
    except Exception as exc:  # pydantic ValidationError and friends
        raise ConfigurationError(f"Invalid OpenContext configuration: {exc}") from exc

    effective = _mask_tree(resolved.config.model_dump(mode="json"))

    sources: dict[str, dict[str, Any]] = {}
    for dotted, value in dotted_leaves(effective):
        layer = resolved.provenance.dotted_layer_of(dotted)
        entry: dict[str, Any] = {"value": value, "source": layer, "path": None, "line": None}
        if layer == "project" and project_lines:
            entry["path"] = str(project_file)
            entry["line"] = _line_of_key(project_lines, dotted)
        elif layer == "global" and global_lines:
            entry["path"] = str(global_path)
            entry["line"] = _line_of_key(global_lines, dotted)
        elif layer == "org" and org_lines:
            entry["path"] = str(org_path)
            entry["line"] = _line_of_key(org_lines, dotted)
        sources[dotted] = entry

    conflicts: list[dict[str, Any]] = []
    for dotted, layers in resolved.provenance.dotted_key_layers.items():
        explicit: list[str] = []
        for layer in layers:
            if layer != "defaults" and layer not in explicit:
                explicit.append(layer)
        if len(explicit) >= 2:
            conflicts.append({"key": dotted, "winner": explicit[-1], "losers": explicit[:-1]})
    conflicts.sort(key=lambda c: str(c["key"]))

    status = "warning" if unknown or deprecated else "passed"
    return {
        "effective_config": effective,
        "sources": sources,
        "conflicts": conflicts,
        "deprecated_keys": deprecated,
        "unknown_keys": unknown,
        "validation": {"status": status},
        "profile": resolved.profile,
    }
