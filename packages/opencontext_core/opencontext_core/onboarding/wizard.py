"""Interactive TUI onboarding wizard for first-time setup.

Uses InquirerPy for arrow-key selectors and checkboxes when available,
falls back to Rich text prompts otherwise. Falls back to non-interactive
mode when stdout is not a TTY or CI is detected.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from opencontext_core import prompts
from opencontext_core.config import SecurityMode
from opencontext_core.dx.console_styles import show_logo
from opencontext_core.onboarding.checklist import DxChecklist, run_checklist
from opencontext_core.onboarding.metrics import DxMetrics
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


class InteractiveOnboardingWizard:
    """Interactive TUI wizard for project onboarding.

    Wraps OnboardingService with InquirerPy-based interactive steps.
    Auto-detects non-interactive environments and falls back to defaults.

    .. deprecated::
        Use :class:`OnboardingWizard` (the curated 4-step first-run journey).
        This TUI class is kept for backward compatibility and powers the
        ``opencontext init`` interactive flow until 1.x.
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


# ===========================================================================
# PR-R2-D — Curated 4-step first-run wizard
# ===========================================================================
# Spec: openspec/changes/opencontext-1-0-convergence/specs/developer-experience-onboarding/spec.md
#
# The legacy ``InteractiveOnboardingWizard`` above drives the InquirerPy TUI
# flow. The new ``OnboardingWizard`` below is the programmatic, opinionated
# 4-step journey (detect_stack → configure → index → verify) that the
# developer-experience spec mandates for ``opencontext status --onboarding``
# and any non-interactive first-run path. The two coexist: the TUI class
# delegates to the legacy OnboardingService for backward compatibility; the
# new wizard composes the same service but exposes step-by-step records so
# callers can resume from any step and so the metrics dashboard (PR-R2-G) can
# consume a single canonical record.


class WizardStep(Enum):
    """The four steps of the curated first-run journey (PR-R2-D, REQ-dx-onb-001)."""

    DETECT_STACK = "detect_stack"
    CONFIGURE = "configure"
    INDEX = "index"
    VERIFY = "verify"


@dataclass(frozen=True)
class StackDetection:
    """Result of :meth:`OnboardingWizard.detect_stack`."""

    language: str = "unknown"
    framework: str | None = None
    package_manager: str | None = None
    entrypoints: tuple[str, ...] = ()


@dataclass
class StepRecord:
    """Per-step execution record: status, summary, duration.

    The wizard stores one of these per ``WizardStep`` so callers can
    introspect progress (``opencontext status --onboarding``) and the metrics
    dashboard (PR-R2-G) can chart per-step durations.
    """

    step: WizardStep
    status: str = "pending"  # one of: pending | ok | failed | skipped
    summary: str = ""
    duration_seconds: float = 0.0
    error: str | None = None


@dataclass(frozen=True)
class WizardReport:
    """Final report emitted by :func:`run_onboarding` and :meth:`OnboardingWizard.verify`."""

    root: Path
    config_exists: bool
    checklist_score: int
    checklist: DxChecklist
    metrics: DxMetrics
    step_records: dict[WizardStep, StepRecord] = field(default_factory=dict)
    result: OnboardingResult | None = None


# ---------------------------------------------------------------------------
# Stack detection heuristics
# ---------------------------------------------------------------------------

_PYTHON_MARKERS = ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")
_NODE_MARKERS = ("package.json",)
_GO_MARKERS = ("go.mod",)
_RUST_MARKERS = ("Cargo.toml",)


def _detect_language(root: Path) -> str:
    if any((root / m).exists() for m in _PYTHON_MARKERS):
        return "python"
    if any((root / m).exists() for m in _NODE_MARKERS):
        return "javascript"
    if any((root / m).exists() for m in _GO_MARKERS):
        return "go"
    if any((root / m).exists() for m in _RUST_MARKERS):
        return "rust"
    return "unknown"


def _detect_entrypoints(root: Path, language: str) -> tuple[str, ...]:
    if language == "python":
        return tuple(sorted(p.name for p in root.glob("*.py")))
    if language == "javascript":
        names = []
        for name in ("index.js", "index.ts", "main.js", "main.ts"):
            if (root / name).exists():
                names.append(name)
        return tuple(names)
    return ()


def _detect_package_manager(root: Path, language: str) -> str | None:
    if language == "javascript":
        if (root / "package-lock.json").exists():
            return "npm"
        if (root / "yarn.lock").exists():
            return "yarn"
        if (root / "pnpm-lock.yaml").exists():
            return "pnpm"
    if language == "python":
        if (root / "uv.lock").exists():
            return "uv"
        if (root / "poetry.lock").exists():
            return "poetry"
        if (root / "Pipfile").exists():
            return "pipenv"
    return None


# ---------------------------------------------------------------------------
# OnboardingWizard
# ---------------------------------------------------------------------------


class OnboardingWizard:
    """Curated 4-step first-run wizard (PR-R2-D, REQ-dx-onb-001).

    Steps: ``DETECT_STACK → CONFIGURE → INDEX → VERIFY``. Each step is a
    public method so callers can resume from any step, and the per-step
    ``StepRecord`` is the contract ``opencontext status --onboarding``
    consumes. Composes the existing ``OnboardingService`` for the heavy
    lifting (config / agents / harness / MCP) so the wizard never duplicates
    that logic.
    """

    DEFAULT_TEMPLATE = "generic"
    DEFAULT_SECURITY_MODE = "private_project"

    steps: tuple[WizardStep, ...] = (
        WizardStep.DETECT_STACK,
        WizardStep.CONFIGURE,
        WizardStep.INDEX,
        WizardStep.VERIFY,
    )

    def __init__(self, root: str | Path = ".") -> None:
        self.root = Path(root).resolve()
        self.step_records: dict[WizardStep, StepRecord] = {
            step: StepRecord(step=step) for step in self.steps
        }
        self._stack: StackDetection | None = None
        self._result: OnboardingResult | None = None

    # ------------------------------------------------------------------
    # Step 1: detect_stack
    # ------------------------------------------------------------------

    def detect_stack(self) -> StackDetection:
        """Identify the project's language + entrypoints.

        Best-effort heuristics. Returns ``language='unknown'`` for empty
        projects so downstream steps still run.
        """
        record = self.step_records[WizardStep.DETECT_STACK]
        start = time.monotonic()
        try:
            language = _detect_language(self.root)
            entrypoints = _detect_entrypoints(self.root, language)
            package_manager = _detect_package_manager(self.root, language)
            self._stack = StackDetection(
                language=language,
                package_manager=package_manager,
                entrypoints=entrypoints,
            )
            record.status = "ok"
            record.summary = f"language={language} entrypoints={len(entrypoints)}"
            return self._stack
        except Exception as exc:  # pragma: no cover - defensive
            record.status = "failed"
            record.error = str(exc)
            self._stack = StackDetection()
            return self._stack
        finally:
            record.duration_seconds = time.monotonic() - start

    # ------------------------------------------------------------------
    # Step 2: configure
    # ------------------------------------------------------------------

    def configure(
        self,
        *,
        template: str = DEFAULT_TEMPLATE,
        security_mode: str = DEFAULT_SECURITY_MODE,
        active_clients: Iterable[str] | None = None,
    ) -> OnboardingResult | None:
        """Run the configure step (writes config / prefs / harness / agents).

        Returns the ``OnboardingResult`` on success, ``None`` on failure
        (the failure is also recorded on the step record).
        """
        record = self.step_records[WizardStep.CONFIGURE]
        start = time.monotonic()
        try:
            clients: list[str] = list(active_clients) if active_clients is not None else []
            options = OnboardingOptions(
                root=self.root,
                template=template,
                security_mode=security_mode,
                active_clients=clients,
                force_agent_files=True,
            )
            result = OnboardingService().run(options)
            self._result = result
            record.status = "ok"
            record.summary = (
                f"template={template} security_mode={security_mode} "
                f"clients={','.join(result.active_clients) or '(none)'}"
            )
            return result
        except Exception as exc:
            record.status = "failed"
            record.error = str(exc)
            return None
        finally:
            record.duration_seconds = time.monotonic() - start

    # ------------------------------------------------------------------
    # Step 3: index
    # ------------------------------------------------------------------

    def index(self) -> OnboardingResult:
        """Return the ``OnboardingResult`` produced by the configure step.

        Indexing is part of the configure step's service call (no separate
        pass) so this is a thin read-through that records the step duration.
        Raises ``RuntimeError`` if configure has not run yet — calling index
        without a configure means the project has no opencontext.yaml to
        verify, which is the wrong order.
        """
        record = self.step_records[WizardStep.INDEX]
        start = time.monotonic()
        try:
            if self._result is None:
                raise RuntimeError("index() called before configure(); run configure() first")
            record.status = "ok"
            record.summary = (
                f"files={self._result.indexed_files} symbols={self._result.indexed_symbols}"
            )
            return self._result
        except Exception as exc:
            record.status = "failed"
            record.error = str(exc)
            raise
        finally:
            record.duration_seconds = time.monotonic() - start

    # ------------------------------------------------------------------
    # Step 4: verify
    # ------------------------------------------------------------------

    def verify(self) -> WizardReport:
        """Run the readiness checklist and emit the final ``WizardReport``.

        Always produces a report — even on partial journeys — so callers can
        surface a clear checklist + fix hints instead of a crash trace.
        """
        record = self.step_records[WizardStep.VERIFY]
        start = time.monotonic()
        try:
            checklist = run_checklist(self.root)
            config_exists = (self.root / "opencontext.yaml").exists()
            time_to_first = sum(r.duration_seconds for r in self.step_records.values())
            metrics = DxMetrics.from_result(
                self._result or _empty_result(self.root),
                time_to_first_context_seconds=time_to_first,
                first_run_completed=(
                    config_exists and all(r.status == "ok" for r in self.step_records.values())
                ),
            )
            report = WizardReport(
                root=self.root,
                config_exists=config_exists,
                checklist_score=checklist.score,
                checklist=checklist,
                metrics=metrics,
                step_records=dict(self.step_records),
                result=self._result,
            )
            record.status = "ok" if config_exists else "failed"
            record.summary = (
                f"score={checklist.score} passed={checklist.passed} failed={checklist.failed}"
            )
            if not config_exists:
                record.error = "opencontext.yaml missing after configure"
            return report
        except Exception as exc:
            record.status = "failed"
            record.error = str(exc)
            # Always emit a report — partial state is more useful than a crash.
            checklist = run_checklist(self.root)
            return WizardReport(
                root=self.root,
                config_exists=False,
                checklist_score=checklist.score,
                checklist=checklist,
                metrics=DxMetrics(),
                step_records=dict(self.step_records),
                result=self._result,
            )
        finally:
            record.duration_seconds = time.monotonic() - start

    # ------------------------------------------------------------------
    # Resume / entry point
    # ------------------------------------------------------------------

    def run_from(self, step: WizardStep) -> WizardReport | OnboardingResult:
        """Run the journey starting at ``step`` (skipping earlier steps).

        Steps that have already completed are left untouched in
        ``step_records``. Raises ``ValueError`` for non-``WizardStep`` values
        — guards against typo'd callers (``run_from('INDEX')`` would
        silently no-op).
        """
        if not isinstance(step, WizardStep):
            raise ValueError(f"run_from requires a WizardStep, got {step!r}")
        order = list(self.steps)
        if step not in order:
            raise ValueError(f"unknown wizard step: {step!r}")

        # Walk backwards through earlier steps; if any earlier step is not
        # ``ok``, run it first so later steps have the inputs they need.
        idx = order.index(step)
        for earlier in order[:idx]:
            if self.step_records[earlier].status == "ok":
                continue
            self._dispatch(earlier)

        result: WizardReport | OnboardingResult = self._dispatch(step)
        return result

    def _dispatch(self, step: WizardStep) -> Any:
        """Internal: execute one step method by enum value."""
        if step is WizardStep.DETECT_STACK:
            return self.detect_stack()
        if step is WizardStep.CONFIGURE:
            return self.configure()
        if step is WizardStep.INDEX:
            return self.index()
        if step is WizardStep.VERIFY:
            return self.verify()
        raise ValueError(f"unhandled step: {step!r}")  # pragma: no cover


def _empty_result(root: Path) -> OnboardingResult:
    """Stub result used when verify runs before configure (e.g. on failures)."""
    return OnboardingResult(root=str(root))


def run_onboarding(
    root: str | Path = ".",
    *,
    template: str = OnboardingWizard.DEFAULT_TEMPLATE,
    security_mode: str = OnboardingWizard.DEFAULT_SECURITY_MODE,
    active_clients: Iterable[str] | None = None,
) -> WizardReport:
    """Top-level entry point: run the full 4-step curated journey.

    Returns a :class:`WizardReport` even when individual steps fail — the
    caller decides how to surface the failure (CLI prints the fix hints,
    ``opencontext status --onboarding`` shows the score).
    """
    wizard = OnboardingWizard(root=root)
    wizard.detect_stack()
    wizard.configure(
        template=template,
        security_mode=security_mode,
        active_clients=active_clients,
    )
    # ``index`` only needs to run if configure succeeded — otherwise it
    # raises and we let ``verify`` report the partial state.
    try:
        wizard.index()
    except RuntimeError:
        pass
    return wizard.verify()


__all__ = [
    "InteractiveOnboardingWizard",
    "OnboardingWizard",
    "StackDetection",
    "StepRecord",
    "WizardReport",
    "WizardStep",
    "run_onboarding",
]
