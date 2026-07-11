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

ORCHESTRATOR_TYPES = ("opencontext", "multi-phase", "subagent-native", "solo-compact")


@dataclass
class ClientOrchestratorProfile:
    """Per-client SDD orchestration strategy and token-saving rules."""

    client: str
    orchestrator_type: str
    phase_instructions: dict[str, str] = field(default_factory=dict)
    kg_lookup_first: bool = True
    compact_pack_cmd: str = 'opencontext pack . --query "{task}" --max-tokens {budget} --mode plan'
    delegation_hint: str = ""
    tdd_integration: str = ""

    def phase_instruction(self, phase: str) -> str:
        return self.phase_instructions.get(phase, "")

    def to_dict(self) -> dict[str, Any]:
        return {
            "client": self.client,
            "orchestrator_type": self.orchestrator_type,
            "phase_instructions": self.phase_instructions,
            "kg_lookup_first": self.kg_lookup_first,
            "compact_pack_cmd": self.compact_pack_cmd,
            "delegation_hint": self.delegation_hint,
            "tdd_integration": self.tdd_integration,
        }


def _multi_phase_instructions(budget: int = 3000) -> dict[str, str]:
    return {
        "explore": (
            f'Query the knowledge graph with `opencontext kg query "<task>"` first. '
            f'Then run `opencontext pack . --query "<task>" --max-tokens {budget} --mode plan`. '
            "Never read broad file sets before this step."
        ),
        "propose": (
            "Summarise findings in ≤150 tokens. State what will change and why. "
            "Ask if TDD applies if mode is 'ask'."
        ),
        "spec": (
            f"Load `.opencontext/sdd/context.json`. Use `opencontext pack . --max-tokens {budget} "
            "--mode spec` for relevant symbols only. Write acceptance criteria as a list."
        ),
        "design": (
            "Reference only the symbols impacted via `opencontext impact`. "
            "Keep the design under the phase token budget."
        ),
        "tasks": (
            "Break work into atomic file-level tasks. Each task must fit in one apply cycle."
        ),
        "apply": (
            "Read `.opencontext/sdd/context.json` for TDD mode. "
            "If strict or ask-and-confirmed: write failing test first, then implementation. "
            'Run `opencontext pack . --query "<changed symbol>" --mode diff` before editing.'
        ),
        "verify": (
            "Run focused tests first (from `context.json` test_capabilities), "
            "then lint, then type checks. Record pass/fail with trace id."
        ),
        "archive": (
            "Persist decisions, omitted context reasons, and verification evidence "
            "to memory via `opencontext memory v2 save`."
        ),
    }


def _subagent_native_instructions(budget: int = 3000) -> dict[str, str]:
    return {
        "explore": (
            f"Spawn a background research agent with context from `opencontext pack . "
            f'--query "<task>" --max-tokens {budget} --mode plan`. '
            "Coordinator must not read raw files directly."
        ),
        "propose": (
            "Collect research-agent summary (≤200 tokens). "
            "Coordinator proposes change; sub-agent confirms scope."
        ),
        "spec": (
            "Spawn spec sub-agent with `.opencontext/sdd/context.json` + affected symbols pack. "
            "Sub-agent writes spec; coordinator reviews."
        ),
        "design": (
            "Spawn design sub-agent with impact graph from `opencontext impact`. "
            "Keep coordinator thread lightweight: plan only."
        ),
        "tasks": (
            "Assign each task to a disjoint file-ownership sub-agent. "
            "Sub-agents receive compact packs, not raw history."
        ),
        "apply": (
            "Each sub-agent runs apply for its file set with TDD mode from `context.json`. "
            "Coordinator monitors; does not re-read implemented files."
        ),
        "verify": (
            "Spawn independent review sub-agent for security, regressions, and spec-drift. "
            "Run test capabilities from `context.json`."
        ),
        "archive": (
            "Coordinator archives all sub-agent outputs to memory. "
            "Use `opencontext memory v2 save` with full trace id."
        ),
    }


def _solo_compact_instructions(budget: int = 3000) -> dict[str, str]:
    return {
        "explore": (
            f'Run `opencontext pack . --query "<task>" --max-tokens {budget} --mode plan` '
            "once. Use that pack as the only project context for this session."
        ),
        "propose": (
            "State the change in ≤100 tokens using only information from the context pack."
        ),
        "spec": (
            "Add acceptance criteria inline. Do not re-read project files. "
            "Reference symbols by name from the pack."
        ),
        "design": (
            "Minimal design note inline with spec. "
            "No additional file reads unless a symbol is missing from the pack."
        ),
        "tasks": "List file-level edits. One task per file.",
        "apply": (
            "Apply all tasks in order. "
            "If TDD mode is strict or ask-and-confirmed: write failing test first. "
            "Do not reload context between tasks."
        ),
        "verify": (
            "Run test capabilities from `.opencontext/sdd/context.json`. Report pass/fail inline."
        ),
        "archive": (
            "Save a one-paragraph session summary to memory with "
            "`opencontext memory v2 save --title <slug> --content <summary>`."
        ),
    }


def _opencontext_instructions(budget: int = 3000) -> dict[str, str]:
    return {
        "explore": (
            f'Use `opencontext pack . --query "<task>" --max-tokens {budget} --mode plan` '
            "before broad file reads. Answer with the smallest useful evidence set."
        ),
        "propose": (
            "State intent, scope, risks, and whether apply can continue automatically. "
            "Keep it direct."
        ),
        "spec": (
            "Write acceptance criteria with MUST/SHOULD language. "
            "Use project-local SDD artifact mode from `context.json`."
        ),
        "design": (
            "Design only the changed path. Include affected files, decisions, and rollback."
        ),
        "tasks": (
            "Break work into ordered, testable file-level tasks. Ask only on risk or ambiguity."
        ),
        "apply": (
            "Follow `context.json` TDD mode. In strict mode: failing test first, then code. "
            "Use OpenContext packs for missing context."
        ),
        "verify": ("Run focused tests first, then lint/type checks. Report commands and outcomes."),
        "archive": (
            "Persist decisions, verification evidence, and next steps to the configured "
            "artifact/memory mode."
        ),
    }


CLIENT_ORCHESTRATOR_PROFILES: dict[str, ClientOrchestratorProfile] = {
    "opencode": ClientOrchestratorProfile(
        client="opencode",
        orchestrator_type="opencontext",
        phase_instructions=_opencontext_instructions(),
        kg_lookup_first=True,
        delegation_hint=(
            "OpenCode consumes AGENTS.md plus MCP configuration; keep OpenContext "
            "rules authoritative and use compact context packs."
        ),
        tdd_integration=(
            "OpenContext TDD rules apply. In ask mode, prompt before apply; "
            "in strict mode, enforce test-first automatically."
        ),
    ),
    "kilo-code": ClientOrchestratorProfile(
        client="kilo-code",
        orchestrator_type="opencontext",
        phase_instructions=_opencontext_instructions(),
        kg_lookup_first=True,
        delegation_hint=(
            "Kilo Code shares the OpenCode instruction style. "
            "Uses AGENTS.md plus MCP configuration with OpenContext rules."
        ),
        tdd_integration=(
            "OpenContext TDD rules apply. Kilo Code asks per-change in ask mode "
            "and enforces test-first in strict mode."
        ),
    ),
    "cursor": ClientOrchestratorProfile(
        client="cursor",
        orchestrator_type="subagent-native",
        phase_instructions=_subagent_native_instructions(),
        kg_lookup_first=True,
        compact_pack_cmd='opencontext pack . --query "{task}" --max-tokens {budget} --mode plan',
        delegation_hint=(
            "Cursor supports background agents. "
            "Spawn one agent per SDD phase with a compact context pack, not raw history. "
            "Rule file: `.cursor/rules/opencontext.mdc` (alwaysApply: true)."
        ),
        tdd_integration=(
            "Cursor rule enforces TDD via .cursor/rules/opencontext.mdc. "
            "In 'ask' mode, the rule instructs the agent to prompt before apply."
        ),
    ),
    "kiro-ide": ClientOrchestratorProfile(
        client="kiro-ide",
        orchestrator_type="subagent-native",
        phase_instructions=_subagent_native_instructions(),
        kg_lookup_first=True,
        delegation_hint=(
            "Kiro uses native spec workflows in `.kiro/specs/<change>/`. "
            "Map SDD spec/design phases to Kiro spec files. "
            "Coordinator delegates to Kiro's built-in spec agent."
        ),
        tdd_integration=(
            "Kiro steering file at `.kiro/steering/opencontext.md` enforces TDD. "
            "Integration reads `context.json` for test_capabilities."
        ),
    ),
    "codex": ClientOrchestratorProfile(
        client="codex",
        orchestrator_type="opencontext",
        phase_instructions=_opencontext_instructions(),
        kg_lookup_first=True,
        compact_pack_cmd='opencontext pack . --query "{task}" --max-tokens {budget} --mode plan',
        delegation_hint=(
            "Codex uses the OpenContext profile in a single coordinator thread. "
            "Use compact context packs per phase and avoid sub-agent delegation unless configured."
        ),
        tdd_integration=(
            "OpenContext AGENTS.md TDD rules apply. Codex asks before apply in ask mode "
            "and enforces test-first in strict mode."
        ),
    ),
    "windsurf": ClientOrchestratorProfile(
        client="windsurf",
        orchestrator_type="solo-compact",
        phase_instructions=_solo_compact_instructions(),
        kg_lookup_first=True,
        delegation_hint=(
            "Windsurf uses workspace-scoped rules in `.windsurf/rules/opencontext.md`. "
            "Single-agent solo-compact mode; rule is shareable across team."
        ),
        tdd_integration=(
            "Windsurf rule enforces TDD inline. "
            "No sub-agent delegation; all phases run sequentially in one agent."
        ),
    ),
    "claude-code": ClientOrchestratorProfile(
        client="claude-code",
        orchestrator_type="solo-compact",
        phase_instructions=_solo_compact_instructions(),
        kg_lookup_first=True,
        delegation_hint=(
            "Claude Code uses CLAUDE.md. Keep it concise. "
            "Use context packs for every task; never dump raw file trees."
        ),
        tdd_integration=(
            "CLAUDE.md TDD rules apply. "
            "Claude Code will confirm TDD approach before apply in 'ask' mode."
        ),
    ),
    "gemini-cli": ClientOrchestratorProfile(
        client="gemini-cli",
        orchestrator_type="solo-compact",
        phase_instructions=_solo_compact_instructions(),
        kg_lookup_first=True,
        delegation_hint=(
            "Gemini CLI uses GEMINI.md. Solo-compact mode. Compact context pack once per task."
        ),
        tdd_integration="GEMINI.md TDD rules apply. Ask mode: prompt before apply.",
    ),
    "vscode-copilot": ClientOrchestratorProfile(
        client="vscode-copilot",
        orchestrator_type="solo-compact",
        phase_instructions=_solo_compact_instructions(),
        kg_lookup_first=True,
        delegation_hint=(
            "VS Code Copilot uses `.github/copilot-instructions.md`. "
            "Solo-compact mode. Instructions apply to chat and coding-agent runs."
        ),
        tdd_integration="Copilot instructions enforce TDD. Ask mode per apply.",
    ),
    # P1.5 additions
    "aider": ClientOrchestratorProfile(
        client="aider",
        orchestrator_type="solo-compact",
        phase_instructions=_solo_compact_instructions(),
        kg_lookup_first=True,
        delegation_hint=(
            "Aider uses .aider.conf.yml and CONVENTIONS.md. "
            "Solo-compact mode. Uses git patches for all changes."
        ),
        tdd_integration="Aider CONVENTIONS.md enforces TDD. Will ask before apply in 'ask' mode.",
    ),
    "cline": ClientOrchestratorProfile(
        client="cline",
        orchestrator_type="multi-phase",
        phase_instructions=_multi_phase_instructions(),
        kg_lookup_first=True,
        delegation_hint=(
            "Cline uses CLAUDE.md or custom instructions. "
            "Multi-phase mode delegates exploration to sub-agents."
        ),
        tdd_integration="Cline asks before apply in 'ask' mode. Supports test-first.",
    ),
    "roo": ClientOrchestratorProfile(
        client="roo",
        orchestrator_type="multi-phase",
        phase_instructions=_multi_phase_instructions(),
        kg_lookup_first=True,
        delegation_hint=(
            "Roo uses ROO.md or .roo/ instructions. "
            "Multi-phase mode with built-in sub-agent support."
        ),
        tdd_integration="Roo supports TDD via instruction files. Ask mode supported.",
    ),
    "goose": ClientOrchestratorProfile(
        client="goose",
        orchestrator_type="solo-compact",
        phase_instructions=_solo_compact_instructions(),
        kg_lookup_first=True,
        delegation_hint=(
            "Goose uses GOOSE.md. Solo-compact mode. "
            "Compact context packs are essential for this agent."
        ),
        tdd_integration="Goose supports TDD when configured in GOOSE.md.",
    ),
    "copilot-cli": ClientOrchestratorProfile(
        client="copilot-cli",
        orchestrator_type="solo-compact",
        phase_instructions=_solo_compact_instructions(),
        kg_lookup_first=True,
        delegation_hint=(
            "GitHub Copilot CLI uses .github/copilot-instructions.md. "
            "Solo-compact mode. Integrates with terminal and editor."
        ),
        tdd_integration="Copilot CLI reads instructions file for TDD rules.",
    ),
    "continue": ClientOrchestratorProfile(
        client="continue",
        orchestrator_type="multi-phase",
        phase_instructions=_multi_phase_instructions(),
        kg_lookup_first=True,
        delegation_hint=(
            "Continue uses .continuerc.json. Multi-phase mode with built-in context management."
        ),
        tdd_integration="Continue supports TDD via configuration. Ask mode per phase.",
    ),
    "openhands": ClientOrchestratorProfile(
        client="openhands",
        orchestrator_type="multi-phase",
        phase_instructions=_multi_phase_instructions(),
        kg_lookup_first=True,
        delegation_hint=(
            "OpenHands (formerly OpenDevin) uses custom agent instructions. "
            "Multi-phase mode with file-based coordination."
        ),
        tdd_integration="OpenHands TDD is configured via agent instructions.",
    ),
}


def get_client_orchestrator_profile(client: str) -> ClientOrchestratorProfile:
    """Return the orchestrator profile for a client, falling back to solo-compact."""

    if client in CLIENT_ORCHESTRATOR_PROFILES:
        return CLIENT_ORCHESTRATOR_PROFILES[client]
    return ClientOrchestratorProfile(
        client=client,
        orchestrator_type="solo-compact",
        phase_instructions=_solo_compact_instructions(),
        kg_lookup_first=True,
    )


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
