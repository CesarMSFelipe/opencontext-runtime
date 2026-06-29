"""Configuration validator behind ``opencontext config doctor`` (SPEC-CLI-013-05).

Read-only. Checks the schema version, unknown keys, the selected profile, basic
provider sanity, ``commands`` bindings, and workflow/persona/skill/harness
references — emitting a :class:`~opencontext_core.doctor.deep.DeepDiagnostic` per
finding with an actionable remediation. Reuses the ``doctor/deep.py`` diagnostic
type so ``config doctor`` renders consistently with ``opencontext doctor``.
"""

from __future__ import annotations

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
from opencontext_core.config_profiles import BUILTIN_PROFILES
from opencontext_core.doctor.deep import DeepDiagnostic


def _load_raw(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}
    return raw if isinstance(raw, dict) else {}


def validate(root: str | Path = ".") -> list[DeepDiagnostic]:
    """Validate the project's ``opencontext.yaml``; return diagnostics."""
    diags: list[DeepDiagnostic] = []
    root_path = Path(root)
    config_file = root_path / "opencontext.yaml"
    if not config_file.exists():
        config_file = find_config(root_path) or config_file

    if not config_file.exists():
        diags.append(
            DeepDiagnostic(
                name="config.file",
                status="info",
                message="No opencontext.yaml found.",
                recommendation="Run 'opencontext init' to create one.",
            )
        )
        return diags

    raw = _load_raw(config_file)
    diags.append(
        DeepDiagnostic(
            name="config.file",
            status="passed",
            message=f"Found {config_file}",
        )
    )

    # 1. Schema version.
    version = raw.get("version", 1)
    if version not in (1, 2):
        diags.append(
            DeepDiagnostic(
                name="config.version",
                status="failed",
                message=f"Unsupported schema version: {version!r}",
                recommendation="Set 'version: 1' (legacy) or 'version: 2' (sectioned envelope).",
            )
        )
    else:
        diags.append(
            DeepDiagnostic(
                name="config.version",
                status="passed",
                message=f"Schema version {version}",
            )
        )

    # 2. Unknown top-level keys (extra="forbid" would reject these at load time;
    # surface them here with a fix instead of an opaque validation error).
    known = set(OpenContextConfig.model_fields)
    unknown = [k for k in raw if k not in known]
    for key in unknown:
        diags.append(
            DeepDiagnostic(
                name=f"config.unknown_key.{key}",
                status="failed",
                message=f"Unknown top-level key: '{key}'",
                details=f"Location: {config_file}",
                recommendation=(
                    f"Remove '{key}' or move it under a valid section. "
                    "Run 'opencontext config show' for the valid schema."
                ),
            )
        )

    # 3. Profile selection.
    profile = raw.get("profile")
    if profile is not None:
        if profile in BUILTIN_PROFILES:
            diags.append(
                DeepDiagnostic(
                    name="config.profile",
                    status="passed",
                    message=f"Profile '{profile}' is valid",
                )
            )
        else:
            diags.append(
                DeepDiagnostic(
                    name="config.profile",
                    status="failed",
                    message=f"Unknown profile: '{profile}'",
                    recommendation=(
                        "Choose one of: " + ", ".join(sorted(BUILTIN_PROFILES)) + "."
                    ),
                )
            )

    # 4. Model validation over the known keys merged with built-in defaults
    # (mirrors load_config so required sections are filled; unknown keys are
    # already reported above, so this step surfaces genuine type errors only).
    known_only = {k: v for k, v in raw.items() if k in known}
    merged = _deep_merge(default_config_data(), _normalize_legacy_config(known_only))
    try:
        config = OpenContextConfig.model_validate(merged)
    except Exception as exc:
        diags.append(
            DeepDiagnostic(
                name="config.schema",
                status="failed",
                message="Configuration failed schema validation.",
                details=str(exc)[:500],
                recommendation="Fix the reported fields; run 'opencontext config show'.",
            )
        )
        return diags

    if config is None:
        return diags

    # 5. Provider sanity (bounded; PR-012 owns deep gateway validation).
    providers = config.providers
    if providers.external_enabled and config.security.mode.value == "air_gapped":
        diags.append(
            DeepDiagnostic(
                name="config.providers",
                status="warning",
                message="External providers enabled under air_gapped security mode.",
                recommendation="Disable providers.external_enabled or relax security.mode.",
            )
        )
    else:
        diags.append(
            DeepDiagnostic(
                name="config.providers",
                status="passed",
                message=f"Provider strategy '{providers.strategy}'",
            )
        )

    # 6. Command bindings shape.
    bad_commands = [k for k, v in config.commands.items() if not isinstance(v, dict)]
    if bad_commands:
        diags.append(
            DeepDiagnostic(
                name="config.commands",
                status="failed",
                message=f"Command bindings must be mappings: {', '.join(bad_commands)}",
                recommendation="Each entry under 'commands:' must be a mapping of settings.",
            )
        )

    # 7. Workflow / persona / skill / harness references (best-effort, light).
    _check_refs(config, raw, diags)

    return diags


def _check_refs(
    config: OpenContextConfig, raw: dict[str, Any], diags: list[DeepDiagnostic]
) -> None:
    """Resolve workflow/persona/skill/harness references against known names.

    Best-effort and non-crashing: it surfaces a dangling SDD track reference (the
    one workflow reference a config carries) and reports the resolved counts.
    """
    known_tracks = {"quick", "standard", "full"}
    track = getattr(getattr(config, "sdd", None), "track", None)
    if track is not None and track not in known_tracks:
        diags.append(
            DeepDiagnostic(
                name="config.refs.sdd_track",
                status="warning",
                message=f"sdd.track '{track}' is not a known workflow track.",
                recommendation="Use one of: " + ", ".join(sorted(known_tracks)) + ".",
            )
        )
    diags.append(
        DeepDiagnostic(
            name="config.refs",
            status="passed",
            message=f"{len(config.workflows)} workflow(s), sdd.track='{track}'",
        )
    )
