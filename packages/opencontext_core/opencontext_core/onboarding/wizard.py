"""Interactive TUI onboarding wizard for first-time setup.

Guides new users through project initialization with Rich-based
interactive prompts. Falls back to non-interactive mode when
stdout is not a TTY or CI is detected.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt

from opencontext_core.config import SecurityMode
from opencontext_core.onboarding.service import (
    OnboardingOptions,
    OnboardingResult,
    OnboardingService,
)

console = Console()

# Config templates the wizard can apply. ``air_gapped`` mirrors the
# SecurityMode enum value exactly (no hyphen) so the written config loads.
_TEMPLATE_CHOICES = ("generic", "enterprise", "air_gapped")


class OnboardingWizard:
    """Interactive TUI wizard for project onboarding.

    Wraps OnboardingService with Rich-based interactive steps.
    Auto-detects non-interactive environments and falls back to defaults.
    """

    WELCOME_ART = """
[bold cyan]╔══════════════════════════════════════════════════════╗
║          OpenContext — Context Engineering           ║
║            Runtime for LLM Applications              ║
╚══════════════════════════════════════════════════════╝[/]
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
        """Valid security-mode choices, derived from the SecurityMode enum.

        Deriving from the enum guarantees the wizard can never emit a value
        that fails to load (the previous ``cross_project`` / ``open`` choices
        were not enum members and produced unloadable configs).
        """
        return [mode.value for mode in SecurityMode]

    @staticmethod
    def template_choices() -> list[str]:
        """Valid config-template choices (enum-aligned, no hyphenated names)."""
        return list(_TEMPLATE_CHOICES)

    def run(self, **overrides: Any) -> OnboardingResult:
        """Run the full onboarding wizard.

        Accepts keyword overrides for non-interactive mode:
        - template: str
        - security_mode: str
        - tdd: str (ask|strict|off)
        - agents: list[str]
        - non_interactive: bool (force non-interactive)
        """
        force_non_interactive = overrides.pop("non_interactive", False)
        if force_non_interactive:
            self._interactive = False

        self._show_welcome()

        template = overrides.get("template") or self._choose_template()

        security_mode = overrides.get("security_mode") or self._choose_security_mode()

        # Step 4: TDD mode
        tdd = overrides.get("tdd") or self._choose_tdd_mode()

        # Step 5: Active agents
        agents = overrides.get("agents") or self._choose_agents()

        # Build options
        options = OnboardingOptions(
            root=self.root,
            template=template,
            security_mode=security_mode,
            tdd_mode=tdd,
            active_clients=agents,
            setup_mcp=False,
            force_agent_files=True,
        )

        # Step 6: Index and summarize
        result = self._run_onboarding(options)
        self._show_summary(result)

        return result

    # ------------------------------------------------------------------
    # Interactive detection
    # ------------------------------------------------------------------

    @staticmethod
    def _is_interactive() -> bool:
        """Detect if we're in an interactive terminal."""
        ci = os.environ.get("CI", "").strip().lower()
        if ci in ("true", "1"):
            return False
        return sys.stdout.isatty() and sys.stdin.isatty()

    # ------------------------------------------------------------------
    # Step implementations
    # ------------------------------------------------------------------

    def _show_welcome(self) -> None:
        """Step 1: Display welcome screen."""
        if self._interactive:
            console.clear()
        welcome = Panel(
            self.WELCOME_ART
            + f"\n[bold]Project:[/] {self.root}\n"
            + "\nThis wizard will help you set up OpenContext for your project in 5 steps:\n"
            + "[cyan]1.[/] Choose a configuration template\n"
            + "[cyan]2.[/] Set your security mode\n"
            + "[cyan]3.[/] Choose TDD (Test-Driven Development) mode\n"
            + "[cyan]4.[/] Select active AI coding agents\n"
            + "[cyan]5.[/] Index your project and review the results\n",
            title="Welcome",
            border_style="cyan",
            padding=(1, 2),
        )
        console.print(welcome)

        if self._interactive:
            Prompt.ask("[dim]Press Enter to continue[/]", default="")

    def _choose_template(self) -> str:
        """Step 2: Choose a configuration template."""
        if not self._interactive:
            return "generic"

        help_panel = Panel(
            "[bold]Template presets[/]\n\n"
            "[cyan]Generic (default)[/]  — Standard project, recommended for most users\n"
            "[cyan]Enterprise[/]         — Strict security, all external providers blocked\n"
            "[cyan]Air-gapped[/]         — No external access, no semantic cache, max isolation",
            title="Template Options",
            border_style="blue",
            padding=(1, 1),
        )
        console.print(help_panel)

        return Prompt.ask(
            "Choose a template",
            choices=self.template_choices(),
            default="generic",
        )

    def _choose_security_mode(self) -> str:
        """Step 3: Choose security mode."""
        if not self._interactive:
            return SecurityMode.PRIVATE_PROJECT.value

        help_panel = Panel(
            "[bold]Security modes[/]\n\n"
            "[cyan]developer[/]        — Local dev posture, fewest restrictions\n"
            "[cyan]private_project[/]  — Redaction on, external providers off (default)\n"
            "[cyan]enterprise[/]       — Team sharing with governance\n"
            "[cyan]air_gapped[/]       — Completely offline, no external access",
            title="Security Modes",
            border_style="blue",
            padding=(1, 1),
        )
        console.print(help_panel)

        return Prompt.ask(
            "Choose security mode",
            choices=self.security_mode_choices(),
            default=SecurityMode.PRIVATE_PROJECT.value,
        )

    def _choose_tdd_mode(self) -> str:
        """Step 4: Choose TDD mode."""
        if not self._interactive:
            return "ask"

        help_panel = Panel(
            "[bold]TDD (Test-Driven Development) modes[/]\n\n"
            "[cyan]Ask me[/]   — Prompt before each TDD decision (default)\n"
            "[cyan]Strict[/]   — Always require a failing test before production code\n"
            "[cyan]Off[/]      — No TDD enforcement, code-first workflow",
            title="TDD Modes",
            border_style="blue",
            padding=(1, 1),
        )
        console.print(help_panel)

        return Prompt.ask(
            "Choose TDD mode",
            choices=["ask", "strict", "off"],
            default="ask",
        )

    def _choose_agents(self) -> list[str]:
        """Step 5: Choose active AI coding agents."""
        if not self._interactive:
            return ["opencode"]

        known_agents = [
            ("opencode", True),
            ("claude", False),
            ("cursor", False),
            ("codex", False),
            ("windsurf", False),
            ("copilot", False),
            ("kilo-code", False),
            ("gemini-cli", False),
            ("aider", False),
        ]

        help_panel = Panel(
            "[bold]Select AI coding agents to configure[/]\n\n"
            "OpenContext will generate instruction files for each selected agent.\n"
            "[dim]Use arrow keys or type comma-separated names[/]",
            title="Agent Selection",
            border_style="blue",
            padding=(1, 1),
        )
        console.print(help_panel)

        # Build comma-separated list of choices
        choices_str = ", ".join(f"[cyan]{name}[/]" for name, _selected in known_agents)
        console.print(f"Available agents: {choices_str}")
        console.print()

        agent_input = Prompt.ask(
            "Enter agent names (comma-separated)",
            default="opencode",
        )
        selected = [a.strip() for a in agent_input.split(",") if a.strip()]
        return selected if selected else ["opencode"]

    def _run_onboarding(self, options: OnboardingOptions) -> OnboardingResult:
        """Execute the onboarding pipeline with progress indicator."""
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
        """Display the final setup summary."""
        summary = Panel(
            "\n".join(
                [
                    "[bold green]✓ Setup complete![/]\n",
                    "[cyan]Configuration[/]",
                    f"  Config:      {result.config_path}",
                    f"  SDD context:  {result.sdd_context_path}",
                    f"  Harness:      {result.harness_config_path}",
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
