"""Interactive TUI onboarding wizard for first-time setup.

Uses InquirerPy for arrow-key selectors and checkboxes when available,
falls back to Rich text prompts otherwise. Falls back to non-interactive
mode when stdout is not a TTY or CI is detected.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from opencontext_core import prompts
from opencontext_core.config import SecurityMode
from opencontext_core.dx.console_styles import show_logo
from opencontext_core.onboarding.service import (
    OnboardingOptions,
    OnboardingResult,
    OnboardingService,
)

console = Console()

_TEMPLATE_CHOICES = ("generic", "enterprise", "air_gapped")


# ---------------------------------------------------------------------------
# Wizard
# ---------------------------------------------------------------------------


class OnboardingWizard:
    """Interactive TUI wizard for project onboarding.

    Wraps OnboardingService with InquirerPy-based interactive steps.
    Auto-detects non-interactive environments and falls back to defaults.
    """

    def __init__(self, root: str | Path = ".") -> None:
        self.root = Path(root).resolve()
        self._interactive = self._is_interactive()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_interactive(self) -> bool:
        """Whether the wizard can use interactive prompts."""
        return self._interactive

    @staticmethod
    def security_mode_choices() -> list[str]:
        """Valid security-mode choices, derived from the SecurityMode enum."""
        return [mode.value for mode in SecurityMode]

    @staticmethod
    def template_choices() -> list[str]:
        """Valid config-template choices."""
        return list(_TEMPLATE_CHOICES)

    def run(self, **overrides: Any) -> OnboardingResult:
        """Run the full onboarding wizard."""
        force_non_interactive = overrides.pop("non_interactive", False)
        if force_non_interactive:
            self._interactive = False

        self._show_welcome()

        template = overrides.get("template") or self._choose_template()
        security_mode = overrides.get("security_mode") or self._choose_security_mode()
        tdd = overrides.get("tdd") or self._choose_tdd_mode()
        agents = overrides.get("agents") or self._choose_agents()
        memory_provider = overrides.get("memory_provider") or self._choose_memory_provider()

        options = OnboardingOptions(
            root=self.root,
            template=template,
            security_mode=security_mode,
            tdd_mode=tdd,
            active_clients=agents,
            memory_provider=memory_provider,
            setup_mcp=False,
            force_agent_files=True,
        )

        result = self._run_onboarding(options)
        self._show_summary(result)
        return result

    # ------------------------------------------------------------------
    # Interactive detection
    # ------------------------------------------------------------------

    @staticmethod
    def _is_interactive() -> bool:
        ci = os.environ.get("CI", "").strip().lower()
        if ci in ("true", "1"):
            return False
        return sys.stdout.isatty() and sys.stdin.isatty()

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------

    def _show_welcome(self) -> None:
        if self._interactive:
            console.clear()
        show_logo()
        welcome = Panel(
            f"[bold]Project:[/] {self.root}\n"
            + "\nThis wizard will guide you through 4 steps:\n"
            + "[cyan]1.[/] Configuration template\n"
            + "[cyan]2.[/] Security mode\n"
            + "[cyan]3.[/] TDD mode\n"
            + "[cyan]4.[/] AI coding agents to configure\n",
            title="OpenContext Setup",
            border_style="cyan",
            padding=(1, 2),
        )
        console.print(welcome)

        if self._interactive:
            prompts.pause("Press Enter to start")

    def _choose_template(self) -> str:
        if not self._interactive:
            return "generic"

        console.print()
        console.rule("[bold cyan]Step 1 / 4 — Configuration Template[/]")
        console.print()

        choices = [
            {
                "value": "generic",
                "name": "Generic (default)  — Standard project, recommended for most users",
            },
            {
                "value": "enterprise",
                "name": "Enterprise         — Strict security, all external providers blocked",
            },
            {
                "value": "air_gapped",
                "name": "Air-gapped         — No external access, no semantic cache, max isolation",
            },
        ]
        return str(prompts.select("Choose a configuration template", choices, default="generic"))

    def _choose_security_mode(self) -> str:
        if not self._interactive:
            return SecurityMode.PRIVATE_PROJECT.value

        console.print()
        console.rule("[bold cyan]Step 2 / 4 — Security Mode[/]")
        console.print()

        choices = [
            {
                "value": SecurityMode.PRIVATE_PROJECT.value,
                "name": "private_project  — Redaction on, external providers off (recommended)",
            },
            {
                "value": "developer",
                "name": "developer        — Local dev posture, fewest restrictions",
            },
            {
                "value": "enterprise",
                "name": "enterprise       — Team sharing with governance",
            },
            {
                "value": "air_gapped",
                "name": "air_gapped       — Completely offline, no external access",
            },
        ]
        return str(
            prompts.select(
                "Choose security mode",
                choices,
                default=SecurityMode.PRIVATE_PROJECT.value,
            )
        )

    def _choose_tdd_mode(self) -> str:
        if not self._interactive:
            return "ask"

        console.print()
        console.rule("[bold cyan]Step 3 / 4 — TDD Mode[/]")
        console.print()

        choices = [
            {
                "value": "ask",
                "name": "Ask me   — Prompt before each TDD decision (default)",
            },
            {
                "value": "strict",
                "name": "Strict   — Always require a failing test before production code",
            },
            {
                "value": "off",
                "name": "Off      — No TDD enforcement, code-first workflow",
            },
        ]
        return str(prompts.select("Choose TDD mode", choices, default="ask"))

    def _choose_agents(self) -> list[str]:
        # Detect the agent CLIs actually present on this host (Claude Code, OpenCode,
        # ...) so both paths default to the user's real agents, not a fixed list.
        from opencontext_core.onboarding.service import default_active_clients

        if not self._interactive:
            # Non-interactive (CI / piped): configure every detected agent directly,
            # so a default wizard run wires the user's real agent. Opencode fallback.
            return default_active_clients()

        console.print()
        console.rule("[bold cyan]Step 4 / 4 — AI Coding Agents[/]")
        console.print(
            "[dim]OpenContext will write MCP config and agent persona files for each selection.[/]\n"  # noqa: E501
        )

        choices = [
            {"value": "opencode", "name": "OpenCode      — opencode.ai (Tab personas, MCP)"},
            {"value": "claude-code", "name": "Claude Code   — Anthropic CLI (.claude/agents)"},
            {"value": "cursor", "name": "Cursor        — .cursor/mcp.json"},
            {"value": "windsurf", "name": "Windsurf      — .windsurf/mcp.json"},
            {"value": "kilo-code", "name": "Kilo Code     — VS Code extension"},
            {"value": "gemini-cli", "name": "Gemini CLI    — Google AI CLI"},
            {"value": "codex", "name": "Codex         — OpenAI Codex CLI"},
            {"value": "aider", "name": "Aider         — aider.chat CLI"},
            {"value": "cline", "name": "Cline         — VS Code Cline extension"},
            {"value": "roo", "name": "Roo           — Roo-Code extension"},
            {"value": "continue", "name": "Continue      — continue.dev extension"},
        ]
        # Pre-check the agents actually installed on this host so the common case is
        # one keypress; offered choices stay the full list. Opencode if none detected.
        offered = {c["value"] for c in choices}
        preselected = [c for c in default_active_clients() if c in offered] or ["opencode"]
        return prompts.checkbox(
            "Select agents to configure",
            choices,
            defaults=preselected,
            require_one=True,
        )

    def _choose_memory_provider(self) -> str:
        """Offer Engram coexistence only when an install is detected.

        Default is OpenContext's own memory (``local``). If a co-resident Engram is
        present, ask whether to couple with it (episodic/semantic -> Engram, the
        rest -> OpenContext) — an explicit opt-in, never a silent default.
        """
        if not self._interactive:
            return "local"

        from opencontext_core.memory.engram_bridge import detect_engram

        if not detect_engram():
            return "local"  # nothing to offer — use OpenContext's own memory

        console.print()
        console.rule("[bold cyan]Memory — Engram detected[/]")
        console.print(
            "[dim]You already have Engram. OpenContext can keep using it for episodic "
            "& semantic memory and layer its own engine on top, or use only its own.[/]\n"
        )
        choices = [
            {
                "value": "engram",
                "name": "Couple with Engram  — episodic & semantic → Engram, the rest → "
                "OpenContext (augments capabilities)",
            },
            {
                "value": "local",
                "name": "OpenContext only    — full local engine (layers, decay, "
                "reinforce, supersede, hybrid recall)",
            },
        ]
        # Default to local so Engram coupling is an explicit opt-in (matching the
        # docstring), not what you get by pressing Enter.
        return str(prompts.select("Memory backend", choices, default="local"))

    def _run_onboarding(self, options: OnboardingOptions) -> OnboardingResult:
        service = OnboardingService()
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("[green]Setting up project...", total=None)
            try:
                result = service.run(options)
            except Exception as exc:
                console.print(f"\n[red]Setup failed: {exc}[/]")
                raise
        return result

    def _show_summary(self, result: OnboardingResult) -> None:
        summary = Panel(
            "\n".join(
                [
                    "[bold green]✓ Setup complete![/]\n",
                    "[cyan]Configuration[/]",
                    f"  Config:        {result.config_path}",
                    f"  SDD context:   {result.sdd_context_path}",
                    f"  Harness:       {result.harness_config_path}",
                    "",
                    "[cyan]Indexing[/]",
                    f"  Files indexed: {result.indexed_files}",
                    f"  Symbols found: {result.indexed_symbols}",
                    f"  KG nodes:      {result.knowledge_graph_nodes}",
                    f"  KG edges:      {result.knowledge_graph_edges}",
                    "",
                    "[cyan]Agent files[/]",
                ]
                + ([f"  {f}" for f in result.generated_agent_files] or ["  (none)"])
                + [
                    "",
                    "[bold]Next steps:[/]",
                    "  • Run [cyan]opencontext doctor[/] to verify your setup",
                    "  • Run [cyan]opencontext index .[/] to re-index if needed",
                    '  • Run [cyan]opencontext pack . --query "explain"[/] to test context',
                ]
            ),
            title="Setup Summary",
            border_style="green",
            padding=(1, 2),
        )
        console.print(summary)

        if result.warnings:
            console.print("\n[yellow]Warnings:[/]")
            for w in result.warnings:
                console.print(f"  [yellow]![/] {w}")

        console.print("\n[dim]Run `opencontext doctor` to verify everything is working.[/]")
