"""Unified rules loader: discovery, layering, override recording, evidence.

The loader is the single rule-discovery entry point for the runtime. It reuses
the existing parse logic in :class:`opencontext_core.dx.agent_hints.AgentHintsManager`
(it does **not** introduce a third parser) and consolidates the discovery
surfaces of both legacy modules
(:class:`~opencontext_core.dx.agent_hints.AgentHintsManager` and
:func:`opencontext_core.dx.instructions.import_instructions`).

Resolution happens in three configurable layers — ``global`` (user/home scope),
``project`` (repository root), and ``change`` (current SDD change scope) — with a
more specific layer overriding a less specific one for the same rule key. The
overridden value is recorded (never silently dropped) so both provenance and the
override are observable. Each resolved rule is convertible to an
:class:`~opencontext_core.retrieval.contracts.EvidenceItem` with
``source_type="rule"`` so it flows through the verified-context spine and the
:class:`~opencontext_core.safety.firewall.ContextFirewall`.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from opencontext_core.context.budgeting import estimate_tokens
from opencontext_core.dx.agent_hints import AgentHint, AgentHintsFile, AgentHintsManager
from opencontext_core.models.context import (
    ContextItem,
    ContextPriority,
    DataClassification,
)
from opencontext_core.retrieval.contracts import (
    EvidenceItem,
    FreshnessStatus,
    RetrievalSurface,
)

# Layer identifiers, ordered least- to most-specific.
GLOBAL_LAYER = "global"
PROJECT_LAYER = "project"
CHANGE_LAYER = "change"
VALID_LAYERS: tuple[str, ...] = (GLOBAL_LAYER, PROJECT_LAYER, CHANGE_LAYER)

# Discovery surfaces consolidated from both legacy modules plus the
# ``.opencontext/rules`` directory. ``AGENTS.md`` / ``CLAUDE.md`` are matched by
# both legacy modules today; they appear exactly once here and dedup-by-file
# guarantees a single physical file is never represented twice.
_FLAT_SOURCES: tuple[str, ...] = (
    ".opencontexthints",
    "AGENTS.md",
    "CLAUDE.md",
    ".cursor/rules/opencontext.mdc",
    ".windsurf/rules/opencontext.md",
    ".clinerules",
    ".roorules",
    ".github/copilot-instructions.md",
)
# Directory globs whose every ``*.md`` file is a rule source.
_DIR_SOURCES: tuple[tuple[str, str], ...] = (
    (".opencontext/rules", "*.md"),
    (".cursor/rules", "*.mdc"),
    (".windsurf/rules", "*.md"),
)

_KEY_VALUE_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*=")


@dataclass(frozen=True)
class RulesConfig:
    """Validated configuration for rule discovery and layering.

    Kept inside the rules package (not the global config model) so layer
    enablement and precedence are controllable without coupling discovery to a
    config-file load. ``enabled_layers`` selects which layers participate;
    ``precedence`` orders them least- to most-specific (the last entry wins).
    """

    enabled_layers: tuple[str, ...] = VALID_LAYERS
    precedence: tuple[str, ...] = VALID_LAYERS
    max_section_tokens: int = 2000

    def __post_init__(self) -> None:
        for layer in self.precedence:
            if layer not in VALID_LAYERS:
                raise ValueError(
                    f"unknown rules layer in precedence: {layer!r}; valid layers are {VALID_LAYERS}"
                )
        for layer in self.enabled_layers:
            if layer not in VALID_LAYERS:
                raise ValueError(
                    f"unknown rules layer in enabled_layers: {layer!r}; "
                    f"valid layers are {VALID_LAYERS}"
                )
        if len(set(self.precedence)) != len(self.precedence):
            raise ValueError("rules precedence must not contain duplicate layers")


@dataclass(frozen=True)
class ResolvedRule:
    """A single resolved rule with full provenance."""

    key: str
    category: str
    content: str
    layer: str
    source_file: Path
    priority: int = 0


@dataclass(frozen=True)
class SkippedRule:
    """A rule source skipped because it could not be read or parsed."""

    source_file: Path
    reason: str


@dataclass
class ResolvedRules:
    """Outcome of layered rule resolution."""

    applied: list[ResolvedRule] = field(default_factory=list)
    overridden: list[ResolvedRule] = field(default_factory=list)
    skipped: list[SkippedRule] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.applied


class RulesLoader:
    """Single discovery + resolution + evidence-conversion entry point."""

    def __init__(self, config: RulesConfig | None = None) -> None:
        self._config = config or RulesConfig()
        # Reuse the existing parser; do not reimplement section parsing.
        self._parser = AgentHintsManager(".")

    # -- discovery ---------------------------------------------------------

    def _discover_layer_files(self, root: Path | None) -> list[Path]:
        """Discover all rule files under ``root``, deduplicated by physical path."""

        if root is None:
            return []
        seen: set[Path] = set()
        found: list[Path] = []
        for rel in _FLAT_SOURCES:
            path = root / rel
            if path.is_file():
                resolved = self._physical(path)
                if resolved not in seen:
                    seen.add(resolved)
                    found.append(path)
        for rel_dir, pattern in _DIR_SOURCES:
            directory = root / rel_dir
            if directory.is_dir():
                for path in sorted(directory.glob(pattern)):
                    if path.is_file():
                        resolved = self._physical(path)
                        if resolved not in seen:
                            seen.add(resolved)
                            found.append(path)
        return found

    @staticmethod
    def _physical(path: Path) -> Path:
        try:
            return path.resolve()
        except OSError:
            return path.absolute()

    # -- resolution --------------------------------------------------------

    def resolve(
        self,
        *,
        project_root: Path,
        global_root: Path | None = None,
        change_root: Path | None = None,
    ) -> ResolvedRules:
        """Discover and resolve rules across enabled layers.

        Layers are merged following ``config.precedence`` (least- to
        most-specific). When two layers define a rule for the same
        ``(category, key)``, the higher-precedence value wins and the loser is
        recorded as overridden. A single physical file is never represented
        twice, even if matched by multiple legacy discovery surfaces.
        """

        layer_roots: dict[str, Path | None] = {
            GLOBAL_LAYER: global_root,
            PROJECT_LAYER: project_root,
            CHANGE_LAYER: change_root,
        }

        result = ResolvedRules()
        # winners maps (category, key) -> ResolvedRule currently winning.
        winners: dict[tuple[str, str], ResolvedRule] = {}
        # Track physical files already consumed so a file shared across layer
        # roots (e.g. same path) is parsed once.
        consumed: set[Path] = set()

        precedence_rank = {layer: rank for rank, layer in enumerate(self._config.precedence)}

        for layer in self._config.precedence:
            if layer not in self._config.enabled_layers:
                continue
            root = layer_roots.get(layer)
            for path in self._discover_layer_files(root):
                physical = self._physical(path)
                if physical in consumed:
                    continue
                consumed.add(physical)
                parsed, skip_reason = self._parse(path)
                if parsed is None:
                    result.skipped.append(
                        SkippedRule(source_file=path, reason=skip_reason or "parse_failed")
                    )
                    continue
                for rule in self._rules_from_parsed(parsed, layer=layer, source_file=path):
                    map_key = (rule.category, rule.key)
                    incumbent = winners.get(map_key)
                    if incumbent is None:
                        winners[map_key] = rule
                        continue
                    # Higher precedence rank wins (later in precedence list).
                    if precedence_rank[rule.layer] >= precedence_rank[incumbent.layer]:
                        winners[map_key] = rule
                        result.overridden.append(incumbent)
                    else:
                        result.overridden.append(rule)

        result.applied = sorted(
            winners.values(),
            key=lambda r: (precedence_rank.get(r.layer, 0), r.category, r.priority, r.content),
        )
        return result

    def _parse(self, path: Path) -> tuple[AgentHintsFile | None, str | None]:
        """Reuse AgentHintsManager parsing; treat unknown formats as line rules."""

        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return None, "not_utf8_text"
        except OSError as exc:
            return None, f"unreadable:{type(exc).__name__}"

        filename = path.name
        try:
            if filename == ".opencontexthints":
                return self._parser._parse_opencontexthints(content, str(path)), None
            if filename in {"AGENTS.md", "CLAUDE.md"}:
                return self._parser._parse_agents_md(content, str(path)), None
            if filename.endswith((".mdc", ".md")):
                return self._parser._parse_rules_md(content, str(path)), None
            # .clinerules / .roorules / copilot-instructions and friends:
            # reuse the simple line-rule parser rather than writing a new one.
            return self._parser._parse_rules_md(content, str(path)), None
        except Exception as exc:  # pragma: no cover - defensive, parse is total
            return None, f"parse_error:{type(exc).__name__}"

    @staticmethod
    def _rules_from_parsed(
        parsed: AgentHintsFile, *, layer: str, source_file: Path
    ) -> list[ResolvedRule]:
        rules: list[ResolvedRule] = []
        buckets: list[tuple[str, list[AgentHint]]] = [
            ("conventions", parsed.conventions),
            ("architecture", parsed.architecture),
            ("workflows", parsed.workflows),
            ("patterns", parsed.patterns),
            ("warnings", parsed.warnings),
        ]
        for category, hints in buckets:
            for hint in hints:
                content = hint.content.strip()
                if not content:
                    continue
                rules.append(
                    ResolvedRule(
                        key=_rule_key(content),
                        category=category,
                        content=content,
                        layer=layer,
                        source_file=source_file,
                        priority=hint.priority,
                    )
                )
        return rules

    # -- evidence conversion ----------------------------------------------

    def to_evidence(self, resolved: ResolvedRules, *, project_root: Path) -> list[EvidenceItem]:
        """Convert applied (winning) rules into trust-tagged evidence items."""

        evidence: list[EvidenceItem] = []
        for rule in resolved.applied:
            display = _relative(rule.source_file, project_root)
            evidence.append(
                EvidenceItem(
                    id=_rule_evidence_id(rule, display),
                    content=rule.content,
                    source=f"{display}#{rule.category}",
                    source_type="rule",
                    provenance={
                        "file": display,
                        "layer": rule.layer,
                        "category": rule.category,
                        "priority": "P1",
                    },
                    confidence=0.95,
                    freshness=FreshnessStatus.CURRENT,
                    surface=RetrievalSurface.RUNTIME,
                    tokens=estimate_tokens(rule.content),
                    protected=False,
                    classification=DataClassification.INTERNAL,
                )
            )
        return evidence

    @staticmethod
    def evidence_to_context_items(evidence: list[EvidenceItem]) -> list[ContextItem]:
        """Render rule evidence as context items for firewall export checks."""

        items: list[ContextItem] = []
        for item in evidence:
            items.append(
                ContextItem(
                    id=item.id,
                    content=item.content,
                    source=item.source,
                    source_type=item.source_type,
                    priority=ContextPriority.P1,
                    tokens=item.tokens,
                    score=item.confidence,
                    metadata=dict(item.provenance),
                    classification=item.classification,
                    trusted=True,
                    source_trust=item.confidence,
                )
            )
        return items


def _rule_key(content: str) -> str:
    """Derive a stable override key from a rule's content.

    ``foo=bar`` style rules key on the left-hand side so a project value can
    override a global one for the same setting. Free-text rules key on the
    normalized content so identical text dedups but distinct guidance does not.
    """

    match = _KEY_VALUE_RE.match(content)
    if match:
        return match.group(1).lower()
    return " ".join(content.lower().split())


def _rule_evidence_id(rule: ResolvedRule, display: str) -> str:
    digest = hashlib.sha256(
        "|".join([rule.layer, rule.category, display, rule.content]).encode("utf-8")
    ).hexdigest()[:12]
    return f"rule-{rule.layer}-{digest}"


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except (ValueError, OSError):
        return str(path)
