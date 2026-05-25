"""Agent capabilities registry for OpenContext.

Maps agent client IDs to their capabilities (edit, shell, MCP, sub-agents, etc.).
Used by the harness to determine which agent is appropriate for a given phase
and by onboarding to select which instruction files to generate.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentCapabilities:
    """Declared capabilities for an AI coding agent."""

    id: str
    display_name: str
    can_edit_files: bool = False
    can_run_shell: bool = False
    supports_mcp: bool = False
    supports_diff_review: bool = False
    supports_plan_mode: bool = False
    supports_subagents: bool = False
    supports_streaming: bool = False
    supports_proposal_only: bool = False
    preferred_use_cases: list[str] = field(default_factory=list)
    instruction_files: list[str] = field(default_factory=list)
    orchestrator_type: str = "solo-compact"


AGENT_CAPABILITIES: dict[str, AgentCapabilities] = {
    "opencode": AgentCapabilities(
        id="opencode",
        display_name="OpenCode",
        can_edit_files=True,
        can_run_shell=True,
        supports_mcp=True,
        supports_diff_review=True,
        supports_plan_mode=True,
        supports_subagents=False,
        supports_streaming=True,
        preferred_use_cases=["terminal_agent", "repo_investigation", "sdd_workflow"],
        instruction_files=["AGENTS.md", "opencode.json"],
        orchestrator_type="multi-phase",
    ),
    "cursor": AgentCapabilities(
        id="cursor",
        display_name="Cursor",
        can_edit_files=True,
        can_run_shell=True,
        supports_mcp=True,
        supports_diff_review=True,
        supports_plan_mode=True,
        supports_subagents=True,
        supports_streaming=True,
        preferred_use_cases=["ide_agent", "composer", "background_agents"],
        instruction_files=[".cursor/rules/opencontext.mdc"],
        orchestrator_type="subagent-native",
    ),
    "claude-code": AgentCapabilities(
        id="claude-code",
        display_name="Claude Code",
        can_edit_files=True,
        can_run_shell=True,
        supports_mcp=True,
        supports_diff_review=True,
        supports_plan_mode=True,
        supports_subagents=False,
        supports_streaming=True,
        preferred_use_cases=["terminal_agent", "quick_edits"],
        instruction_files=["CLAUDE.md"],
        orchestrator_type="solo-compact",
    ),
    "codex": AgentCapabilities(
        id="codex",
        display_name="Codex CLI",
        can_edit_files=True,
        can_run_shell=True,
        supports_mcp=False,
        supports_diff_review=True,
        supports_plan_mode=True,
        supports_subagents=False,
        supports_streaming=True,
        preferred_use_cases=["terminal_agent", "patch_based_workflow"],
        instruction_files=["AGENTS.md"],
        orchestrator_type="solo-compact",
    ),
    "windsurf": AgentCapabilities(
        id="windsurf",
        display_name="Windsurf",
        can_edit_files=True,
        can_run_shell=True,
        supports_mcp=True,
        supports_diff_review=True,
        supports_plan_mode=False,
        supports_subagents=False,
        supports_streaming=True,
        preferred_use_cases=["ide_agent", "cascade_workflow"],
        instruction_files=[".windsurf/rules/opencontext.md"],
        orchestrator_type="solo-compact",
    ),
    "kilo-code": AgentCapabilities(
        id="kilo-code",
        display_name="Kilo Code",
        can_edit_files=True,
        can_run_shell=True,
        supports_mcp=True,
        supports_diff_review=True,
        supports_plan_mode=True,
        supports_subagents=True,
        supports_streaming=True,
        preferred_use_cases=["terminal_agent", "multi_agent_workflow"],
        instruction_files=["AGENTS.md", "opencode.json"],
        orchestrator_type="multi-phase",
    ),
    "gemini-cli": AgentCapabilities(
        id="gemini-cli",
        display_name="Gemini CLI",
        can_edit_files=True,
        can_run_shell=True,
        supports_mcp=False,
        supports_diff_review=False,
        supports_plan_mode=False,
        supports_subagents=False,
        supports_streaming=True,
        preferred_use_cases=["terminal_agent", "quick_questions"],
        instruction_files=["GEMINI.md"],
        orchestrator_type="solo-compact",
    ),
    "aider": AgentCapabilities(
        id="aider",
        display_name="Aider",
        can_edit_files=True,
        can_run_shell=False,
        supports_mcp=False,
        supports_diff_review=True,
        supports_plan_mode=False,
        supports_subagents=False,
        supports_streaming=True,
        supports_proposal_only=True,
        preferred_use_cases=["git_patch", "controlled_refactor", "pair_programming"],
        instruction_files=[".aider.conf.yml", "CONVENTIONS.md"],
        orchestrator_type="solo-compact",
    ),
    "cline": AgentCapabilities(
        id="cline",
        display_name="Cline",
        can_edit_files=True,
        can_run_shell=True,
        supports_mcp=True,
        supports_diff_review=True,
        supports_plan_mode=True,
        supports_subagents=True,
        supports_streaming=True,
        preferred_use_cases=["terminal_agent", "multi_step_tasks"],
        instruction_files=["CLAUDE.md", ".clinerules"],
        orchestrator_type="multi-phase",
    ),
    "roo": AgentCapabilities(
        id="roo",
        display_name="Roo",
        can_edit_files=True,
        can_run_shell=True,
        supports_mcp=True,
        supports_diff_review=True,
        supports_plan_mode=True,
        supports_subagents=True,
        supports_streaming=True,
        preferred_use_cases=["terminal_agent", "code_review", "multi_agent"],
        instruction_files=["ROO.md", ".roo/rules/"],
        orchestrator_type="multi-phase",
    ),
    "goose": AgentCapabilities(
        id="goose",
        display_name="Goose",
        can_edit_files=True,
        can_run_shell=True,
        supports_mcp=True,
        supports_diff_review=False,
        supports_plan_mode=False,
        supports_subagents=False,
        supports_streaming=True,
        preferred_use_cases=["terminal_agent", "automation"],
        instruction_files=["GOOSE.md"],
        orchestrator_type="solo-compact",
    ),
    "copilot-cli": AgentCapabilities(
        id="copilot-cli",
        display_name="GitHub Copilot CLI",
        can_edit_files=False,
        can_run_shell=False,
        supports_mcp=False,
        supports_diff_review=False,
        supports_plan_mode=False,
        supports_subagents=False,
        supports_streaming=True,
        preferred_use_cases=["shell_autocomplete", "explain_commands"],
        instruction_files=[".github/copilot-instructions.md"],
        orchestrator_type="solo-compact",
    ),
    "continue": AgentCapabilities(
        id="continue",
        display_name="Continue",
        can_edit_files=True,
        can_run_shell=True,
        supports_mcp=True,
        supports_diff_review=True,
        supports_plan_mode=True,
        supports_subagents=True,
        supports_streaming=True,
        preferred_use_cases=["ide_agent", "multi_model", "context_chaining"],
        instruction_files=[".continuerc.json"],
        orchestrator_type="multi-phase",
    ),
    "openhands": AgentCapabilities(
        id="openhands",
        display_name="OpenHands",
        can_edit_files=True,
        can_run_shell=True,
        supports_mcp=True,
        supports_diff_review=True,
        supports_plan_mode=True,
        supports_subagents=False,
        supports_streaming=True,
        preferred_use_cases=["terminal_agent", "sandboxed_execution", "benchmark"],
        instruction_files=["openhands/instructions.md"],
        orchestrator_type="multi-phase",
    ),
}


def get_agent_capabilities(client_id: str) -> AgentCapabilities | None:
    """Return capabilities for a client, or None if unknown."""
    return AGENT_CAPABILITIES.get(client_id)


def list_supported_agents() -> list[dict[str, str | bool]]:
    """Return a summary list of all registered agents with key capabilities."""
    return [
        {
            "id": cap.id,
            "display_name": cap.display_name,
            "orchestrator_type": cap.orchestrator_type,
            "can_edit_files": cap.can_edit_files,
            "supports_subagents": cap.supports_subagents,
            "supports_mcp": cap.supports_mcp,
        }
        for cap in AGENT_CAPABILITIES.values()
    ]
