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

from opencontext_cli.output import eprint
from opencontext_core import prompts
from opencontext_core.configurator import KNOWN_AGENTS, Configurator
from opencontext_core.configurator.constants import MCP_LABEL
from opencontext_core.configurator.mcp_strategy import McpShape
from opencontext_core.dx.console_styles import console
from opencontext_core.dx.wizard_frame import WizardStep, render_frame

# Detail cards for the interactive uninstall steps — the shared wizard frame
# renders these in the config-TUI info-pane format.
_UNINSTALL_WIZARD_STEPS: dict[str, WizardStep] = {
    "scope": WizardStep(
        title="Uninstall scope",
        effect="Chooses what is removed: this project's wiring, HOME state, or both.",
        recommended="workspace — keeps global config for other projects.",
        risk="full removes all traces, including HOME-level OpenContext state.",
        cli="opencontext uninstall --scope <workspace|global> | --full",
    ),
    "confirm": WizardStep(
        title="Confirm removal",
        effect="Strips the managed config and MCP entries for the selected scope.",
        recommended="Preview first with --dry-run.",
        risk="Destructive; --purge additionally deletes local state directories.",
        cli="opencontext uninstall --yes [--dry-run]",
    ),
}


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
            stripped = inject_managed_section(text, "stack", "")
            if stripped.strip():
                write_text_atomic(agents, stripped)
            elif stripped != text:
                agents.unlink()  # file held only our managed block — install created it
        except Exception:
            pass
    gitignore = base / ".gitignore"
    if gitignore.exists():
        try:
            text = gitignore.read_text(encoding="utf-8")
            stripped = inject_managed_lines(text, "storage", [])
            if stripped.strip():
                write_text_atomic(gitignore, stripped)
            elif stripped != text:
                gitignore.unlink()  # file held only our managed block — install created it
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

    In-repo state dirs (``.storage/opencontext``, ``.opencontext``) are always
    removed when present — ``--purge`` is an explicit cleanup pass. The XDG
    user-mode state directory for this project is additionally removed when the
    ownership manifest matches the given root (``is_owned()`` gate).
    """
    import shutil
    from pathlib import Path

    from opencontext_core.paths import StorageMode, is_owned, resolve_storage_path

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

    # Also remove the XDG user-mode state directory for this project if owned.
    try:
        _xdg_path = resolve_storage_path(base, StorageMode.user)
        if _xdg_path.exists() and is_owned(_xdg_path):
            shutil.rmtree(_xdg_path)
            removed.append(str(_xdg_path))
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
        "--scope",
        choices=["workspace", "global", "all", "local"],  # local = legacy alias for workspace
        default=None,  # None = not given; a TTY offers a selector, otherwise 'workspace'
        help=(
            "Purge scope: 'workspace' (project state), 'global' (HOME OC state), "
            "'all' (both). Legacy alias 'local' maps to 'workspace'. Default: workspace."
        ),
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
    parser.add_argument(
        "--global-state",
        action="store_true",
        help=(
            "With --full, also remove OpenContext HOME state "
            "(.config/opencontext, .opencontext/backups)."
        ),
    )


def _global_state_targets() -> list[Path]:
    home = Path.home()
    return [
        home / ".config" / "opencontext",
        home / ".opencontext" / "backups",
    ]


def resolve_uninstall_scope(args: Any) -> str:
    """Return the effective purge scope from parsed args.

    Resolution order (highest → lowest precedence):
      1. --full without explicit scope → 'all' (covers both tiers)
      2. --scope <value> → normalise alias 'local' → 'workspace'
      3. default → 'workspace'

    The scope returned is always one of: 'workspace', 'global', 'all'.
    """
    raw_scope = getattr(args, "scope", "workspace") or "workspace"
    # Normalise legacy alias.
    if raw_scope == "local":
        raw_scope = "workspace"
    # --full implies scope=all when no more-specific scope was given.
    if getattr(args, "full", False) and raw_scope == "workspace":
        return "all"
    return raw_scope


def _purge_global_state() -> list[str]:
    """Delete OpenContext HOME state. Best-effort and scoped to known OC dirs.

    NOTE: a system-level Engram provisioned by ``install --install-engram`` (pipx/npm)
    is intentionally NOT reversed here — that is a separate system install the user
    owns, so uninstall never touches it. Only OpenContext's own HOME state is removed.
    """
    import shutil

    removed: list[str] = []
    for target in _global_state_targets():
        if not target.exists():
            continue
        try:
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            removed.append(str(target))
        except Exception:
            pass

    for parent in (Path.home() / ".config", Path.home() / ".opencontext"):
        try:
            parent.rmdir()
        except OSError:
            pass
    return removed


def _run_full_uninstall(
    root: str | Path, scope: str, json_output: bool, *, global_state: bool = False
) -> None:
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

    # 3. Clear ledger BEFORE purging. InstallationManager() eagerly recreates
    #    .opencontext/{agent-configs,backups} in its constructor, so it must run
    #    before the purge — otherwise the purge runs first and the constructor
    #    resurrects .opencontext, leaving residue that fails verify.
    try:
        from opencontext_core.install_manager import InstallationManager

        InstallationManager().clear_state()
        report["state_cleared"] = True
    except Exception:
        pass

    # 4. Glob sweep oc-*.md under known persona/command dirs
    for pattern in (".claude/agents/oc-*.md", ".claude/commands/oc-*.md"):
        for p in base.glob(pattern):
            try:
                p.unlink()
                report["removed"].append(str(p))
            except Exception:
                pass

    # 4b. Remove .claude/agents and .claude/commands if empty after sweep.
    # rmdir only removes empty dirs; OSError is silently ignored when non-empty
    # or absent so user content is always left intact.
    for _claude_subdir in (base / ".claude" / "agents", base / ".claude" / "commands"):
        try:
            _claude_subdir.rmdir()
        except OSError:
            pass

    # 4c. Remove the parent .claude/ dir if now empty (e.g. both subdirs were
    # the only children). Non-empty parent (user content present) is left intact.
    try:
        (base / ".claude").rmdir()
    except OSError:
        pass

    # 5. Purge known project artifacts — MUST be the last filesystem mutation so
    #    nothing recreates .opencontext after it is removed.
    purged = _purge_project_artifacts(root)
    report["purged"] = purged

    # 5b. Strip project-level managed blocks (.gitignore storage block, AGENTS.md
    #     stack block). Full uninstall always targets the project root, so force
    #     "local" scope regardless of the agent-config scope.
    _strip_project_managed_blocks(root, "local")

    # 6. Verify traces. With --global-state, purge HOME state first, then scan both
    #    project and global so the report is honest (a later --verify must agree).
    if global_state:
        report["global_removed"] = _purge_global_state()
    residue = verify_no_traces(root)
    global_residue = verify_no_global_traces([]) if global_state else []
    if global_state:
        report["global_residue"] = global_residue
    all_residue = [*residue, *global_residue]
    report["verify"] = {"passed": len(all_residue) == 0, "residue": residue}

    if json_output:
        print(json.dumps(report, indent=2))
        return
    console.header("Full Uninstall")
    console.panel("[bold green]Full uninstall complete[/bold green]", style="success", fit=True)
    if report.get("purged"):
        console.dim(f"  purged: {', '.join(report['purged'])}")
    if report.get("global_removed"):
        console.dim(f"  global removed: {', '.join(report['global_removed'])}")
    if all_residue:
        console.warning("Traces remain:")
        for trace in all_residue:
            console.dim(f"  {trace}")
    else:
        console.success("verify passed: no traces remain.")


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

    # The .gitignore managed storage block must be stripped by --full.
    gitignore = base / ".gitignore"
    if gitignore.exists():
        try:
            if "opencontext:storage" in gitignore.read_text(encoding="utf-8"):
                residue.append(str(gitignore))
        except OSError:
            pass

    return residue


def _mcp_config_has_oc(path: Path, shape: McpShape) -> bool:
    """Parse a (home) MCP config and report whether the opencontext server remains.

    A text/regex scan misses the home MCP entry: the server is a nested object keyed
    ``opencontext`` with a generic ``command``/``args``, so only parsing the declared
    shape reliably detects it. Returns ``False`` on a missing or unparseable file.
    """
    if not path.exists():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    try:
        if shape in (McpShape.JSON_MCP_SERVERS, McpShape.JSON_SERVERS):
            data = json.loads(text)
            key = "mcpServers" if shape is McpShape.JSON_MCP_SERVERS else "servers"
            servers = data.get(key) if isinstance(data, dict) else None
            return isinstance(servers, dict) and MCP_LABEL in servers
        if shape is McpShape.YAML_MCP_SERVERS:
            import yaml

            data = yaml.safe_load(text)
            servers = data.get("mcpServers") if isinstance(data, dict) else None
            return isinstance(servers, dict) and MCP_LABEL in servers
        if shape is McpShape.TOML_MCP_SERVERS:
            import tomllib

            data = tomllib.loads(text)
            servers = data.get("mcp_servers") if isinstance(data, dict) else None
            return isinstance(servers, dict) and MCP_LABEL in servers
    except Exception:
        return False
    return False


def verify_no_global_traces(agents: list[str]) -> list[str]:
    """Check global (HOME) agent config + OpenContext state for residue.

    Returns paths with residue. MUST NOT delete anything — report only. Detects each
    installed agent's home MCP config still advertising an ``opencontext`` server
    (parsed per shape), each agent's home persona dir for ``oc-*.md``, Claude Code's
    settings.json allow-list, and OpenContext HOME state (``~/.config/opencontext``,
    ``~/.opencontext/backups``). When ``agents`` is empty, installed agents are detected.
    """
    import re

    from opencontext_core.configurator import constants
    from opencontext_core.configurator.adapter import get_adapter

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

    detected = agents or Configurator().detect_installed()
    for agent_id in detected:
        try:
            adapter = get_adapter(agent_id)
        except Exception:
            continue
        # Home MCP config still carrying the opencontext server (invisible to regex).
        if _mcp_config_has_oc(adapter.mcp_config_path, adapter.mcp_shape):
            residue.append(str(adapter.mcp_config_path))
        # Home persona dir (e.g. ~/.config/opencode/agents/oc-*.md).
        subdir = constants.global_agents_subdir(agent_id)
        if subdir:
            persona_dir = adapter.config_dir / subdir
            if persona_dir.exists():
                residue.extend(str(p) for p in persona_dir.glob("oc-*.md") if p.is_file())

    # Claude Code global agents dir
    claude_global_agents = home / ".claude" / "agents"
    if claude_global_agents.exists():
        for child in claude_global_agents.glob("oc-*.md"):
            if child.is_file():
                residue.append(str(child))

    # Claude Code hidden delegates dir
    claude_delegates = claude_global_agents / ".opencontext-delegates"
    if claude_delegates.exists():
        for child in claude_delegates.glob("oc-*.md"):
            if child.is_file():
                residue.append(str(child))

    # Claude Code settings.json
    claude_settings = home / ".claude" / "settings.json"
    if claude_settings.exists() and _contains_oc(claude_settings):
        residue.append(str(claude_settings))

    # OpenContext HOME state (config profiles + home backups).
    for state_path in _global_state_targets():
        if state_path.exists():
            residue.append(str(state_path))

    return list(dict.fromkeys(residue))


def _select_scope_interactive(args: Any) -> None:
    """Offer the scope choice the flags encode (``--scope`` / ``--full``).

    Mutates ``args`` in place: 'full' flips ``args.full`` so the normal --full
    path (scope=all) runs; otherwise the chosen scope is recorded on
    ``args.scope`` exactly as if the flag had been passed.
    """
    render_frame(1, 2, _UNINSTALL_WIZARD_STEPS["scope"])
    choice = prompts.select(
        "What should be uninstalled?",
        [
            ("workspace", "Workspace — this project's agent config and state"),
            ("global", "Global — HOME-level OpenContext state"),
            ("full", "Full — remove all traces (workspace + global)"),
        ],
        default="workspace",
    )
    if choice == "full":
        args.full = True
    else:
        args.scope = choice


def handle_uninstall(args: Any) -> None:
    """Remove OpenContext's managed config from the requested agents."""
    from opencontext_cli.main import _resolve_flag

    dry_run = _resolve_flag(getattr(args, "dry_run", False), "OPENCONTEXT_DRY_RUN")
    json_output = _resolve_flag(getattr(args, "json", False), "OPENCONTEXT_JSON")
    yes = _resolve_flag(getattr(args, "yes", False), "OPENCONTEXT_YES")
    root = getattr(args, "root", ".")

    # Bare interactive run (no scope flags, no automation flags) → offer the
    # same choice the flags encode instead of silently assuming workspace.
    # Non-TTY runs never prompt (they fall through to the existing guards).
    framed_wizard = False
    if (
        getattr(args, "scope", None) is None
        and not getattr(args, "full", False)
        and not getattr(args, "verify", False)
        and not dry_run
        and not json_output
        and not yes
        and sys.stdin.isatty()
    ):
        _select_scope_interactive(args)
        framed_wizard = True

    scope = getattr(args, "scope", None) or "workspace"

    # --verify: read-only trace scan scoped to the resolved scope.
    if getattr(args, "verify", False):
        effective_scope = resolve_uninstall_scope(args)
        residue = verify_no_traces(root) if effective_scope in ("workspace", "all") else []
        global_residue = verify_no_global_traces([]) if effective_scope in ("global", "all") else []
        passed = len(residue) == 0 and len(global_residue) == 0
        if json_output:
            print(
                json.dumps(
                    {"passed": passed, "residue": residue, "global_residue": global_residue},
                    indent=2,
                )
            )
        else:
            console.header("Uninstall Verification")
            if passed:
                console.success("verify passed: no OpenContext traces found.")
            else:
                if residue:
                    console.warning("verify failed: project traces remain:")
                    for p in residue:
                        console.dim(f"  {p}")
                if global_residue:
                    console.warning("verify failed: global traces remain:")
                    for p in global_residue:
                        console.dim(f"  {p}")
                console.dim("Run 'opencontext uninstall --full --global-state --yes' to clean up.")
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
            if getattr(args, "global_state", False):
                targets.extend(str(p) for p in _global_state_targets())
            if json_output:
                print(json.dumps({"dry_run": True, "would_remove": targets}, indent=2))
            else:
                console.header("Full Uninstall")
                console.warning("Dry run — nothing removed.")
                console.print("Would remove:")
                for t in targets:
                    console.dim(f"  {t}")
            return
        if not yes and not sys.stdin.isatty():
            eprint("--full requires --yes in non-interactive mode.")
            sys.exit(1)
        if not yes:
            if framed_wizard:
                render_frame(2, 2, _UNINSTALL_WIZARD_STEPS["confirm"].with_current("full removal"))
            console.warning("--full will delete all OpenContext traces under the project root.")
            if not prompts.confirm("Proceed?", default=False):
                console.warning("Full uninstall cancelled.")
                return
        effective_scope = resolve_uninstall_scope(args)
        _run_full_uninstall(
            root,
            scope,
            json_output,
            global_state=(
                effective_scope in ("global", "all") or getattr(args, "global_state", False)
            ),
        )
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
            console.info("No configured agents to remove.")
        return

    if dry_run:
        report = configurator.deconfigure(valid, scope=scope, dry_run=True)
        if json_output:
            print(json.dumps(report, indent=2))
        else:
            console.header("Uninstall OpenContext")
            console.warning("Dry run — nothing removed.")
            for result in report["results"]:
                console.print(f"  [bold]{result['agent']}[/]")
                for action in result.get("plan", []):
                    if isinstance(action, dict):
                        verb = action.get("action", "change")
                        path = action.get("path", "")
                        console.dim(f"    {verb} {path}")
                    else:
                        console.dim(f"    {action}")
            if _resolve_flag(getattr(args, "purge", False), "OPENCONTEXT_PURGE"):
                console.dim(f"  would purge: {', '.join(_PURGE_TARGETS)}")
        return

    # Destructive: require explicit confirmation unless --yes (or non-interactive
    # JSON). Never proceed silently on a non-TTY without --yes — exit 2 with a
    # message (same convention as `config wizard --non-interactive`).
    if not yes and not json_output:
        if not sys.stdin.isatty():
            eprint("Refusing non-interactive uninstall; pass --yes (or --dry-run to preview).")
            sys.exit(2)
        if framed_wizard:
            render_frame(2, 2, _UNINSTALL_WIZARD_STEPS["confirm"].with_current(", ".join(valid)))
        console.print(f"About to remove OpenContext from: [bold]{', '.join(valid)}[/]")
        if _resolve_flag(getattr(args, "purge", False), "OPENCONTEXT_PURGE"):
            console.warning(
                f"--purge will DELETE {', '.join(_PURGE_TARGETS)} under the project root."
            )
        if not prompts.confirm("Proceed?", default=False):
            console.warning("Uninstall cancelled.")
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
    console.header("Uninstall OpenContext")
    console.panel(
        f"[bold green]Removed OpenContext from {removed_n} agent(s)[/bold green]",
        style="success",
        fit=True,
    )
    for result in report.get("results", []):
        console.print(f"  [bold]{result['agent']}[/]")
        for file_path in result.get("files", []):
            console.dim(f"    {file_path}")
    for agent in unknown:
        console.warning(f"- {agent} (unknown, skipped)")
    if report.get("state_cleared"):
        console.dim("  global install state cleared (reinstall will re-run setup)")
    if report.get("purged"):
        console.dim(f"  purged: {', '.join(report['purged'])}")


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
