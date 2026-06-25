"""Uninstall CLI command — cleanly remove OpenContext's managed agent config.

The inverse of ``setup``: strips the managed instructions block and the
``opencontext`` MCP entry (plus agent-specific extras) from each agent, leaving
everything the developer authored untouched. A pre-change backup is taken, so a
removal is recoverable.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel

from opencontext_core import prompts
from opencontext_core.configurator import KNOWN_AGENTS, Configurator


def _strip_project_managed_blocks(root: object, scope: str) -> None:
    """Remove project-level managed blocks that setup added outside any single
    agent: the stack-standards block in AGENTS.md and the storage block in
    .gitignore. Preserves all user content. Best-effort, local scope only.
    """
    if scope != "local":
        return
    from pathlib import Path

    from opencontext_core.configurator.filemerge import (
        inject_managed_lines,
        inject_managed_section,
        write_text_atomic,
    )

    base = Path(str(root))
    agents = base / "AGENTS.md"
    if agents.exists():
        try:
            text = agents.read_text(encoding="utf-8")
            write_text_atomic(agents, inject_managed_section(text, "stack", ""))
        except Exception:
            pass
    gitignore = base / ".gitignore"
    if gitignore.exists():
        try:
            text = gitignore.read_text(encoding="utf-8")
            write_text_atomic(gitignore, inject_managed_lines(text, "storage", []))
        except Exception:
            pass


_PURGE_TARGETS = (
    ".opencontext",
    ".storage/opencontext",
    "opencontext.yaml",
    "harness.yaml",
    ".mcp.json",
)


def _purge_project_artifacts(root: object) -> list[str]:
    """Delete OpenContext's project-local artifacts. Best-effort; returns what
    was removed. Only paths under ``root`` are touched.
    """
    import shutil
    from pathlib import Path

    base = Path(str(root))
    removed: list[str] = []
    for name in _PURGE_TARGETS:
        target = base / name
        if not target.exists():
            continue
        try:
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            removed.append(name)
        except Exception:
            pass
    storage = base / ".storage"
    if storage.is_dir() and not any(storage.iterdir()):
        try:
            storage.rmdir()
            removed.append(".storage")
        except Exception:
            pass
    return removed


console = Console()


def add_uninstall_parser(subparsers: Any) -> None:
    """Add the ``uninstall`` command parser."""
    parser = subparsers.add_parser(
        "uninstall",
        help="Remove OpenContext's managed config from your AI agent(s).",
        description=(
            "Remove OpenContext from existing AI coding agents (the inverse of setup).\n\n"
            "  opencontext uninstall                 Remove from every configured agent\n"
            "  opencontext uninstall claude-code      Remove from one agent\n"
            "  opencontext uninstall --all            Remove from every known agent\n"
            "  opencontext uninstall --dry-run        Show what would be removed\n\n"
            "Only OpenContext's managed instructions block and MCP entry are removed; "
            "your own content is left intact and a backup is taken first."
        ),
    )
    parser.add_argument("agents", nargs="*", metavar="AGENT", help="Agent id(s) to remove from.")
    parser.add_argument(
        "--all", dest="all_agents", action="store_true", help="Remove from every known agent."
    )
    parser.add_argument(
        "--scope", choices=["global", "local"], default="local", help="Where config was written."
    )
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation.")
    parser.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview the removal without changing anything."
    )
    parser.add_argument("--root", default=".", help="Project root (for project-scoped agents).")
    parser.add_argument(
        "--purge",
        action="store_true",
        help="Also delete project artifacts (.opencontext/, .storage/, *.yaml configs).",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Remove all traces: ledger-tracked files, known artifacts, oc-*.md glob sweep.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Scan for remaining OpenContext traces and report pass/fail (no files removed).",
    )


def _run_full_uninstall(root: object, scope: str, json_output: bool) -> None:
    """Execute the --full uninstall: deconfigure, ledger delete, purge, glob sweep."""
    from pathlib import Path

    base = Path(str(root))
    report: dict[str, Any] = {"status": "full_uninstall", "removed": []}

    # 1. Deconfigure all detected agents
    configurator = Configurator(project_root=root)
    agents = configurator.detect_installed() or list(KNOWN_AGENTS)
    valid = [a for a in agents if a in set(KNOWN_AGENTS)]
    if valid:
        dec = configurator.deconfigure(valid, scope=scope)
        report["deconfigure"] = dec

    # 2. Delete ledger-tracked paths that exist under root
    try:
        from opencontext_core.install_manager import InstallationManager

        mgr = InstallationManager()
        state = mgr._load_state()
        if state and state.files:
            for fp in state.files:
                p = Path(fp)
                try:
                    if p.is_relative_to(base) and p.exists():
                        p.unlink()
                        report["removed"].append(str(p))
                except Exception:
                    pass
    except Exception:
        pass

    # 3. Purge known project artifacts
    purged = _purge_project_artifacts(root)
    report["purged"] = purged

    # 4. Glob sweep oc-*.md under known persona/command dirs
    for pattern in (".claude/agents/oc-*.md", ".claude/commands/oc-*.md"):
        for p in base.glob(pattern):
            try:
                p.unlink()
                report["removed"].append(str(p))
            except Exception:
                pass

    # 5. Clear ledger
    try:
        from opencontext_core.install_manager import InstallationManager

        InstallationManager().clear_state()
        report["state_cleared"] = True
    except Exception:
        pass

    # 6. Verify traces
    residue = verify_no_traces(root)
    report["verify"] = {"passed": len(residue) == 0, "residue": residue}

    if json_output:
        print(json.dumps(report, indent=2))
        return
    console.print(
        Panel.fit(
            "[bold green]Full uninstall complete[/bold green]",
            border_style="green",
        )
    )
    if report.get("purged"):
        console.print(f"  [dim]purged: {', '.join(report['purged'])}[/]")
    if residue:
        console.print("[yellow]Traces remain:[/]")
        for p in residue:
            console.print(f"  [dim]{p}[/]")
    else:
        console.print("[green]verify passed[/]: no traces remain.")


def verify_no_traces(root: object) -> list[str]:
    """Scan known locations for OpenContext residue; return list of remaining traces."""
    from pathlib import Path

    base = Path(str(root))
    residue: list[str] = []

    for name in (".opencontext", ".storage/opencontext"):
        p = base / name
        if p.exists():
            residue.append(str(p))

    for name in ("opencontext.yaml", "harness.yaml", ".mcp.json"):
        p = base / name
        if p.exists():
            residue.append(str(p))

    for pattern in (".claude/agents/oc-*.md", ".claude/commands/oc-*.md"):
        residue.extend(str(p) for p in base.glob(pattern))

    for fname in ("AGENTS.md", "CLAUDE.md", "GEMINI.md", "QWEN.md"):
        p = base / fname
        if p.exists():
            try:
                if "opencontext" in p.read_text(encoding="utf-8").lower():
                    residue.append(str(p))
            except OSError:
                pass

    return residue


def verify_no_global_traces(agents: list[str]) -> list[str]:
    """Check global agent config dirs for OpenContext residue.

    Returns list of paths with residue. MUST NOT delete any files — report only.
    """
    import re

    _OC_PATTERN = re.compile(
        r"opencontext|oc-orchestrator|oc-explorer|oc-requirements", re.IGNORECASE
    )

    def _contains_oc(path: Path) -> bool:
        try:
            return bool(_OC_PATTERN.search(path.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            return False

    residue: list[str] = []
    home = Path.home()

    # Claude Code global agents dir
    claude_global_agents = home / ".claude" / "agents"
    if claude_global_agents.exists():
        for child in claude_global_agents.glob("oc-*.md"):
            if child.is_file():
                residue.append(str(child))

    # Claude Code hidden delegates dir
    claude_delegates = home / ".claude" / "agents" / ".opencontext-delegates"
    if claude_delegates.exists():
        for child in claude_delegates.glob("oc-*.md"):
            if child.is_file():
                residue.append(str(child))

    # Claude Code settings.json
    claude_settings = home / ".claude" / "settings.json"
    if claude_settings.exists() and _contains_oc(claude_settings):
        residue.append(str(claude_settings))

    return residue


def handle_uninstall(args: Any) -> None:
    """Remove OpenContext's managed config from the requested agents."""
    from opencontext_cli.main import _resolve_flag

    scope = getattr(args, "scope", "local")
    dry_run = _resolve_flag(getattr(args, "dry_run", False), "OPENCONTEXT_DRY_RUN")
    json_output = _resolve_flag(getattr(args, "json", False), "OPENCONTEXT_JSON")
    yes = _resolve_flag(getattr(args, "yes", False), "OPENCONTEXT_YES")
    root = getattr(args, "root", ".")

    # --verify: read-only trace scan
    if getattr(args, "verify", False):
        residue = verify_no_traces(root)
        global_residue = verify_no_global_traces([])
        passed = len(residue) == 0  # global_residue is report-only, not a failure
        if json_output:
            print(
                json.dumps(
                    {"passed": passed, "residue": residue, "global_residue": global_residue},
                    indent=2,
                )
            )
        else:
            if passed:
                console.print("[green]verify passed[/]: no OpenContext traces found.")
            else:
                if residue:
                    console.print("[yellow]verify failed[/]: project traces remain:")
                    for p in residue:
                        console.print(f"  [dim]{p}[/]")
                if global_residue:
                    console.print(
                        "[yellow]verify[/]: global agent config residue (report only, not purged):"
                    )
                    for p in global_residue:
                        console.print(f"  [dim]{p}[/]")
                if residue or global_residue:
                    console.print(
                        "[dim]Run 'opencontext uninstall --full --yes' to clean up.[/]"
                    )
        sys.exit(0 if passed else 1)

    # --full: complete trace removal
    if getattr(args, "full", False):
        if dry_run:
            # Dry-run never requires --yes; just print the plan and exit 0.
            targets = [
                *_PURGE_TARGETS,
                ".claude/agents/oc-*.md",
                ".claude/commands/oc-*.md",
            ]
            if json_output:
                print(json.dumps({"dry_run": True, "would_remove": targets}, indent=2))
            else:
                console.print("[bold yellow]Dry run — nothing removed.[/]")
                console.print("Would remove:")
                for t in targets:
                    console.print(f"  [dim]{t}[/]")
            return
        if not yes and not sys.stdin.isatty():
            sys.stderr.write("--full requires --yes in non-interactive mode.\n")
            sys.exit(1)
        if not yes:
            console.print(
                "[red]--full will delete all OpenContext traces under the project root.[/]"
            )
            if not __import__("opencontext_core.prompts", fromlist=["confirm"]).confirm(
                "Proceed?", default=False
            ):
                console.print("[yellow]Full uninstall cancelled.[/]")
                return
        _run_full_uninstall(root, scope, json_output)
        return

    configurator = Configurator(project_root=getattr(args, "root", "."))

    requested = _parse_agents(getattr(args, "agents", None))
    if getattr(args, "all_agents", False):
        agents = list(KNOWN_AGENTS)
    elif requested:
        agents = requested
    else:
        agents = configurator.detect_installed()

    valid = [a for a in agents if a in set(KNOWN_AGENTS)]
    unknown = [a for a in agents if a not in set(KNOWN_AGENTS)]

    if not valid:
        if json_output:
            print(json.dumps({"status": "no_agents", "agents_removed": 0, "skipped": unknown}))
        else:
            console.print("[yellow]No configured agents to remove.[/]")
        return

    if dry_run:
        report = configurator.deconfigure(valid, scope=scope, dry_run=True)
        if json_output:
            print(json.dumps(report, indent=2))
        else:
            console.print("[bold yellow]Dry run — nothing removed.[/]")
            for result in report["results"]:
                console.print(f"  [bold]{result['agent']}[/]")
                for action in result.get("plan", []):
                    if isinstance(action, dict):
                        verb = action.get("action", "change")
                        path = action.get("path", "")
                        console.print(f"    [dim]{verb} {path}[/]")
                    else:
                        console.print(f"    [dim]{action}[/]")
            if _resolve_flag(getattr(args, "purge", False), "OPENCONTEXT_PURGE"):
                console.print(f"  [dim]would purge: {', '.join(_PURGE_TARGETS)}[/]")
        return

    # Destructive: require explicit confirmation unless --yes (or non-interactive
    # JSON). Never proceed silently on a non-TTY without --yes.
    if not yes and not json_output:
        if not sys.stdin.isatty():
            console.print("[yellow]Refusing non-interactive uninstall; pass --yes.[/]")
            return
        console.print(f"About to remove OpenContext from: [bold]{', '.join(valid)}[/]")
        if _resolve_flag(getattr(args, "purge", False), "OPENCONTEXT_PURGE"):
            console.print(
                "[red]--purge will DELETE[/] "
                f"[bold]{', '.join(_PURGE_TARGETS)}[/] under the project root."
            )
        if not prompts.confirm("Proceed?", default=False):
            console.print("[yellow]Uninstall cancelled.[/]")
            return

    report = configurator.deconfigure(valid, scope=scope)
    if unknown:
        report["skipped"] = unknown
    _strip_project_managed_blocks(getattr(args, "root", "."), scope)

    # Full uninstall: clear the global install ledger so a later reinstall re-runs
    # global setup instead of short-circuiting on "already installed".
    full_uninstall = getattr(args, "all_agents", False) or not requested
    if full_uninstall:
        try:
            from opencontext_core.install_manager import InstallationManager

            if InstallationManager().clear_state():
                report["state_cleared"] = True
        except Exception:
            pass

    if _resolve_flag(getattr(args, "purge", False), "OPENCONTEXT_PURGE") and scope == "local":
        report["purged"] = _purge_project_artifacts(getattr(args, "root", "."))

    if json_output:
        print(json.dumps(report, indent=2))
        return
    removed_n = report["agents_removed"]
    console.print(
        Panel.fit(
            f"[bold green]Removed OpenContext from {removed_n} agent(s)[/bold green]",
            border_style="green",
        )
    )
    for result in report.get("results", []):
        console.print(f"  [bold]{result['agent']}[/]")
        for file_path in result.get("files", []):
            console.print(f"    [dim]{file_path}[/]")
    for agent in unknown:
        console.print(f"  [yellow]- {agent} (unknown, skipped)[/]")
    if report.get("state_cleared"):
        console.print("  [dim]global install state cleared (reinstall will re-run setup)[/]")
    if report.get("purged"):
        console.print(f"  [dim]purged: {', '.join(report['purged'])}[/]")


def _parse_agents(values: list[str] | None) -> list[str]:
    if not values:
        return []
    agents: list[str] = []
    for raw in values:
        for item in raw.split(","):
            normalized = item.strip()
            if normalized and normalized not in agents:
                agents.append(normalized)
    return agents
