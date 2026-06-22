"""Configuration schema + loader for the architecture & code-quality feature.

This module is the **leaf** of the ``quality.*`` package: it imports nothing
from its sibling quality modules so that ``architecture.py``, ``languages.py``,
``baseline.py``, and ``evaluator.py`` can all import *it* without a cycle.

The whole feature is **zero-config**: every field defaults, so the default
behaviour works with no ``.opencontext/quality.toml`` present at all. The config
file is read-only stdlib ``tomllib`` (Python 3.11+, already the repo target — no
new dependency). We never *write* TOML, only read it.

Mapping of the on-disk ``quality.toml`` (see the design doc) to these types::

    enabled       = true        -> QualityRules.enabled
    max_fix_loops = 3           -> QualityRules.max_fix_loops
    mode          = "ratchet"   -> QualityRules.mode (QualityMode)
    baseline      = "..."       -> QualityRules.baseline_path

    [architecture]              -> QualityRules.architecture (ArchitectureRules)
    [[architecture.layers]]     -> ArchitectureRules.layers (LayerRule, ...)
    [[architecture.boundaries]] -> ArchitectureRules.boundaries (BoundaryRule, ...)

    [languages.<lang>]          -> QualityRules.languages (LanguageRule, ...)
      profile = "strict"        -> LanguageRule.profile (StandardsProfile)
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

# Canonical config filename, relative to the project root.
QUALITY_CONFIG_FILENAME = ".opencontext/quality.toml"


class QualityConfigError(ValueError):
    """Raised when a present ``quality.toml`` is malformed.

    A *missing* file never raises (the zero-config path returns
    :data:`DEFAULT_RULES`). Only a file that exists but cannot be parsed or
    contains an invalid value raises this, with a clear, actionable message.
    The CLI surfaces it; the harness gate catches it and falls back to
    :data:`DEFAULT_RULES` while recording a skipped-reason (degrade honestly).
    """


class QualityMode(StrEnum):
    """Global enforcement posture.

    * ``off``     — no evaluation at all.
    * ``warn``    — evaluate and report, never block.
    * ``strict``  — block on any error finding / health regression.
    * ``ratchet`` — block only on *new* violations vs the baseline (default).
    """

    OFF = "off"
    WARN = "warn"
    STRICT = "strict"
    RATCHET = "ratchet"


class StandardsProfile(StrEnum):
    """Per-language strictness tier (selects the tool set in ``languages.py``)."""

    RELAXED = "relaxed"
    STANDARD = "standard"
    STRICT = "strict"


@dataclass(frozen=True)
class LayerRule:
    """A named architectural layer matched by glob patterns.

    ``paths`` are project-relative POSIX glob patterns; ``order`` lets a config
    express a coarse top-to-bottom ordering (lower depends on higher).
    """

    name: str
    paths: tuple[str, ...]  # glob patterns, project-relative POSIX
    order: int = 0


@dataclass(frozen=True)
class BoundaryRule:
    """A directed dependency rule between two layers.

    The TOML keys are ``from`` / ``to`` (Python keywords), surfaced here as
    ``from_layer`` / ``to_layer``.
    """

    from_layer: str  # toml key 'from'
    to_layer: str  # toml key 'to'
    allow: bool = False
    reason: str = ""


@dataclass(frozen=True)
class ArchitectureRules:
    """Thresholds + structural rules for the architecture analyzer.

    Every threshold defaults to a sensible value so the zero-config path is
    meaningful: cycles are never allowed, god-files are flagged, complexity is
    capped, and layers/boundaries are simply empty (no boundary checks until a
    team declares them).
    """

    max_cycles: int = 0
    no_god_files: bool = True
    god_file_in_degree: int = 8  # absolute fan-in cap (matches detect_god_nodes default)
    god_file_loc: int = 600  # LOC cap for a god-file
    max_cc: int = 25
    max_coupling: str = "B"  # letter grade A..F or numeric string
    max_depth: int = 0  # 0 = disabled (DIRECTORY nesting)
    min_duplicate_tokens: int = 40  # min shared normalized tokens before a clone is flagged
    max_nesting: int = 5  # CODE block-nesting ceiling per function (0 disables)
    layers: tuple[LayerRule, ...] = ()
    boundaries: tuple[BoundaryRule, ...] = ()


@dataclass(frozen=True)
class LanguageRule:
    """Per-language profile override (e.g. ``python`` -> ``strict``)."""

    language: str
    profile: StandardsProfile = StandardsProfile.STANDARD


@dataclass(frozen=True)
class QualityRules:
    """The fully-resolved configuration for one project.

    All fields default, so ``QualityRules()`` (== :data:`DEFAULT_RULES`) is the
    zero-config baseline used when no file exists.
    """

    enabled: bool = True  # master on/off (spec key)
    max_fix_loops: int = 2  # in-loop self-correction cap (spec key; default 2)
    mode: QualityMode = QualityMode.RATCHET  # zero-config default per spec
    baseline_path: str = ".opencontext/quality-baseline.json"
    architecture: ArchitectureRules = field(default_factory=ArchitectureRules)
    languages: tuple[LanguageRule, ...] = ()

    @property
    def is_active(self) -> bool:
        """True when the feature is enabled AND the mode is not ``off``."""
        return self.enabled and self.mode is not QualityMode.OFF


# The zero-config baseline used whenever no ``quality.toml`` exists.
DEFAULT_RULES: QualityRules = QualityRules()


def _require_mapping(value: Any, *, context: str) -> dict[str, Any]:
    """Return ``value`` as a dict or raise a clear :class:`QualityConfigError`."""
    if not isinstance(value, dict):
        raise QualityConfigError(
            f"quality.toml: expected a table for {context}, got {type(value).__name__}"
        )
    return value


def _coerce_bool(value: Any, *, key: str, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise QualityConfigError(f"quality.toml: '{key}' must be a boolean, got {value!r}")
    return value


def _coerce_int(value: Any, *, key: str, default: int) -> int:
    if value is None:
        return default
    # bool is a subclass of int; reject it explicitly so 'true' isn't read as 1.
    if isinstance(value, bool) or not isinstance(value, int):
        raise QualityConfigError(f"quality.toml: '{key}' must be an integer, got {value!r}")
    return value


def _coerce_str(value: Any, *, key: str, default: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        raise QualityConfigError(f"quality.toml: '{key}' must be a string, got {value!r}")
    return value


def _coerce_mode(value: Any) -> QualityMode:
    if value is None:
        return DEFAULT_RULES.mode
    if not isinstance(value, str):
        raise QualityConfigError(f"quality.toml: 'mode' must be a string, got {value!r}")
    try:
        return QualityMode(value.lower())
    except ValueError as exc:
        allowed = ", ".join(m.value for m in QualityMode)
        raise QualityConfigError(
            f"quality.toml: invalid mode {value!r}; expected one of: {allowed}"
        ) from exc


def _coerce_profile(value: Any, *, language: str) -> StandardsProfile:
    if value is None:
        return StandardsProfile.STANDARD
    if not isinstance(value, str):
        raise QualityConfigError(
            f"quality.toml: [languages.{language}].profile must be a string, got {value!r}"
        )
    try:
        return StandardsProfile(value.lower())
    except ValueError as exc:
        allowed = ", ".join(p.value for p in StandardsProfile)
        raise QualityConfigError(
            f"quality.toml: [languages.{language}] invalid profile {value!r}; "
            f"expected one of: {allowed}"
        ) from exc


def _coerce_paths(value: Any, *, layer_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        # A single string is accepted as a one-element list for convenience.
        return (value,)
    if not isinstance(value, (list, tuple)):
        raise QualityConfigError(
            f"quality.toml: [[architecture.layers]] '{layer_name}' paths must be a list"
        )
    paths: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise QualityConfigError(
                f"quality.toml: [[architecture.layers]] '{layer_name}' paths "
                f"must be strings, got {item!r}"
            )
        paths.append(item)
    return tuple(paths)


def _parse_layers(raw: Any) -> tuple[LayerRule, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise QualityConfigError("quality.toml: [[architecture.layers]] must be an array of tables")
    layers: list[LayerRule] = []
    for entry in raw:
        table = _require_mapping(entry, context="[[architecture.layers]]")
        name = table.get("name")
        if not isinstance(name, str) or not name:
            raise QualityConfigError(
                "quality.toml: [[architecture.layers]] requires a non-empty 'name'"
            )
        layers.append(
            LayerRule(
                name=name,
                paths=_coerce_paths(table.get("paths"), layer_name=name),
                order=_coerce_int(table.get("order"), key=f"layers.{name}.order", default=0),
            )
        )
    return tuple(layers)


def _parse_boundaries(raw: Any) -> tuple[BoundaryRule, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise QualityConfigError(
            "quality.toml: [[architecture.boundaries]] must be an array of tables"
        )
    boundaries: list[BoundaryRule] = []
    for entry in raw:
        table = _require_mapping(entry, context="[[architecture.boundaries]]")
        from_layer = table.get("from")
        to_layer = table.get("to")
        if not isinstance(from_layer, str) or not from_layer:
            raise QualityConfigError(
                "quality.toml: [[architecture.boundaries]] requires a non-empty 'from'"
            )
        if not isinstance(to_layer, str) or not to_layer:
            raise QualityConfigError(
                "quality.toml: [[architecture.boundaries]] requires a non-empty 'to'"
            )
        boundaries.append(
            BoundaryRule(
                from_layer=from_layer,
                to_layer=to_layer,
                allow=_coerce_bool(table.get("allow"), key="boundaries.allow", default=False),
                reason=_coerce_str(table.get("reason"), key="boundaries.reason", default=""),
            )
        )
    return tuple(boundaries)


def _parse_architecture(raw: Any) -> ArchitectureRules:
    if raw is None:
        return ArchitectureRules()
    table = _require_mapping(raw, context="[architecture]")
    defaults = ArchitectureRules()

    # max_coupling may be written as a letter grade ("B") or a number (e.g. 12);
    # normalize to a string so downstream parsing has one type to handle.
    raw_coupling = table.get("max_coupling")
    if raw_coupling is None:
        max_coupling = defaults.max_coupling
    elif isinstance(raw_coupling, str):
        max_coupling = raw_coupling
    elif isinstance(raw_coupling, int) and not isinstance(raw_coupling, bool):
        max_coupling = str(raw_coupling)
    else:
        raise QualityConfigError(
            f"quality.toml: [architecture] max_coupling must be a string or "
            f"integer, got {raw_coupling!r}"
        )

    return ArchitectureRules(
        max_cycles=_coerce_int(
            table.get("max_cycles"), key="architecture.max_cycles", default=defaults.max_cycles
        ),
        no_god_files=_coerce_bool(
            table.get("no_god_files"),
            key="architecture.no_god_files",
            default=defaults.no_god_files,
        ),
        god_file_in_degree=_coerce_int(
            table.get("god_file_in_degree"),
            key="architecture.god_file_in_degree",
            default=defaults.god_file_in_degree,
        ),
        god_file_loc=_coerce_int(
            table.get("god_file_loc"),
            key="architecture.god_file_loc",
            default=defaults.god_file_loc,
        ),
        max_cc=_coerce_int(table.get("max_cc"), key="architecture.max_cc", default=defaults.max_cc),
        max_coupling=max_coupling,
        max_depth=_coerce_int(
            table.get("max_depth"), key="architecture.max_depth", default=defaults.max_depth
        ),
        min_duplicate_tokens=_coerce_int(
            table.get("min_duplicate_tokens"),
            key="architecture.min_duplicate_tokens",
            default=defaults.min_duplicate_tokens,
        ),
        max_nesting=_coerce_int(
            table.get("max_nesting"), key="architecture.max_nesting", default=defaults.max_nesting
        ),
        layers=_parse_layers(table.get("layers")),
        boundaries=_parse_boundaries(table.get("boundaries")),
    )


def _parse_languages(raw: Any) -> tuple[LanguageRule, ...]:
    if raw is None:
        return ()
    table = _require_mapping(raw, context="[languages]")
    rules: list[LanguageRule] = []
    # Deterministic order: sort by language name so the resolved config is stable.
    for language in sorted(table):
        spec = _require_mapping(table[language], context=f"[languages.{language}]")
        rules.append(
            LanguageRule(
                language=language,
                profile=_coerce_profile(spec.get("profile"), language=language),
            )
        )
    return tuple(rules)


def parse_rules(data: dict[str, Any]) -> QualityRules:
    """Build :class:`QualityRules` from an already-parsed TOML mapping.

    Separated from :func:`load_rules` so the parse logic is testable without
    touching the filesystem. Unknown top-level keys are ignored (forward
    compatibility); invalid *values* raise :class:`QualityConfigError`.
    """
    data = _require_mapping(data, context="the top-level table")
    defaults = DEFAULT_RULES
    return QualityRules(
        enabled=_coerce_bool(data.get("enabled"), key="enabled", default=defaults.enabled),
        max_fix_loops=_coerce_int(
            data.get("max_fix_loops"), key="max_fix_loops", default=defaults.max_fix_loops
        ),
        mode=_coerce_mode(data.get("mode")),
        # Accept the spec's top-level 'baseline' key, mapped to baseline_path.
        baseline_path=_coerce_str(
            data.get("baseline"), key="baseline", default=defaults.baseline_path
        ),
        architecture=_parse_architecture(data.get("architecture")),
        languages=_parse_languages(data.get("languages")),
    )


def load_rules(root: Path) -> QualityRules:
    """Load ``<root>/.opencontext/quality.toml`` if present, else :data:`DEFAULT_RULES`.

    * A **missing** file returns :data:`DEFAULT_RULES` and never raises (this is
      the zero-config default path).
    * A **malformed** file (unparseable TOML or an invalid value) raises
      :class:`QualityConfigError` with a clear message. CLI callers surface it;
      the harness gate catches it and falls back to :data:`DEFAULT_RULES`,
      recording a skipped-reason so a broken config never reports a false clean.
    """
    config_path = Path(root) / QUALITY_CONFIG_FILENAME
    if not config_path.exists():
        return DEFAULT_RULES
    try:
        raw = config_path.read_bytes()
    except OSError as exc:  # pragma: no cover - unusual filesystem error
        raise QualityConfigError(f"quality.toml: cannot read {config_path}: {exc}") from exc
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise QualityConfigError(f"quality.toml: invalid TOML in {config_path}: {exc}") from exc
    return parse_rules(data)
