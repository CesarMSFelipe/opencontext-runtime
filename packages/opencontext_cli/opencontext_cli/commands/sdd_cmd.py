"""SDD CLI commands: opencontext sdd {verb} namespace with 16 verbs.

Per openspec/changes/agentic-parity-engram-gentle/design/pr3-cli-fastapi.md:

* ``add_sdd_parser(sub)`` registers the ``sdd`` subcommand with 16 verbs.
* ``handle_sdd(args)`` dispatches each verb to its handler — phase verbs
  delegate to :func:`opencontext_sdd.runner.run_phase` when available;
  ``status`` calls :func:`opencontext_sdd.status.Resolve` directly.

LB 2026 — SDD orchestrator CLI surface.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from opencontext_cli.output import eprint
from opencontext_core.dx.console_styles import console

if TYPE_CHECKING:
    # opencontext_sdd is an optional package not installed in all environments
    # (e.g. the bare CLI pyz on a clean machine may lack it until sdd verbs are
    # invoked). This guard keeps the type annotation available to mypy without
    # triggering a top-level ImportError at CLI startup.
    from opencontext_sdd.runner import PhaseResultEnvelope

SUBCOMMANDS = [
    "init",
    "new",
    "explore",
    "propose",
    "spec",
    "design",
    "tasks",
    "apply",
    "verify",
    "review",
    "archive",
    "status",
    "continue",
    "ff",
    "onboard",
    "list",
]

# Execution/planning phase verbs that delegate to the SDD runner (a status/dispatch
# resolver). ``new`` and ``init`` are NOT here: they do real, bounded filesystem
# work (create the openspec scaffold) via dedicated handlers, not the resolver.
_PHASE_VERBS = {
    "explore",
    "propose",
    "spec",
    "design",
    "tasks",
    "apply",
    "verify",
    "archive",
}
_STATUS_VERBS = {"status", "continue", "ff", "onboard", "list"}


def add_sdd_parser(subparsers: Any) -> argparse.ArgumentParser:
    """Register the ``opencontext sdd`` subcommand with all 16 verbs.

    Returns the sdd parser for test introspection.
    """
    sdd_parser = subparsers.add_parser(
        "sdd",
        help="Spec-Driven Development workflow commands.",
        description=(
            "Manage SDD changes through the full lifecycle: init, new, explore, "
            "propose, spec, design, tasks, apply, verify, review, archive, status, "
            "continue, ff (fast-forward), onboard, list."
        ),
    )
    sdd_sub = sdd_parser.add_subparsers(dest="sdd_command", required=True)

    for verb in SUBCOMMANDS:
        p = sdd_sub.add_parser(verb, help=_verb_help(verb))
        p.add_argument("--cwd", default=".", help="Project root (default: current dir).")
        p.add_argument("--verbose", action="store_true", help="Verbose output.")

        if verb in {
            "new",
            "status",
            "continue",
            "propose",
            "spec",
            "design",
            "tasks",
            "apply",
            "verify",
            "review",
            "archive",
            "ff",
        }:
            p.add_argument("--change", default=None, help="Change name.")
            if verb in {"new", "review"}:
                # SUPPRESS: an absent positional must not overwrite --change.
                p.add_argument(
                    "change",
                    nargs="?",
                    default=argparse.SUPPRESS,
                    help="Change name (positional).",
                )

        if verb == "explore":
            p.add_argument("--topic", default=None, help="Exploration topic.")

        if verb in {"status", "review"}:
            p.add_argument(
                "--json",
                action="store_true",
                default=False,
                help="Emit structured JSON output (output is always JSON; flag is explicit).",
            )

        if verb == "apply":
            p.add_argument("--task", default=None, help="Task ID to apply (e.g. T3.1).")
            p.add_argument(
                "--execute",
                action="store_true",
                default=False,
                help=(
                    "Execute the apply phase with the shared OC Flow harness "
                    "(equivalent to `opencontext run --workflow sdd`)."
                ),
            )

    return sdd_parser  # type: ignore[no-any-return]  # subparsers typed Any; add_parser returns ArgumentParser at runtime


def handle_sdd(args: Any) -> None:
    """Dispatch ``args.sdd_command`` to the appropriate handler."""
    verb = args.sdd_command
    cwd = Path(getattr(args, "cwd", ".")).resolve()
    change = getattr(args, "change", None)
    topic = getattr(args, "topic", None)
    task = getattr(args, "task", None)
    verbose = getattr(args, "verbose", False)

    # new/init do real, bounded filesystem work (create the openspec scaffold).
    if verb == "new":
        _handle_new(change, cwd, verbose)
        return
    if verb == "init":
        _handle_init(cwd, verbose)
        return

    # review runs the honest structural review and persists its artifact.
    if verb == "review":
        _handle_review(change, cwd, verbose)
        return

    # apply --execute runs the shared harness (real edits, TDD, gates).
    if verb == "apply" and getattr(args, "execute", False):
        _handle_apply_execute(change, cwd, verbose)
        return

    # archive does real, bounded filesystem work: closes a verified change.
    if verb == "archive":
        _handle_archive(change, cwd, verbose)
        return

    # Phase verbs delegate to the SDD runner via run_phase.
    if verb in _PHASE_VERBS:
        _run_phase(verb, cwd, change, topic=topic, task=task, verbose=verbose)
        return

    # Status-family verbs
    if verb == "status":
        _handle_status(change, cwd, verbose)
        return
    if verb == "continue":
        _handle_continue(change, cwd, verbose)
        return
    if verb == "ff":
        _handle_ff(change, cwd, verbose)
        return
    if verb == "onboard":
        _handle_onboard(cwd, verbose)
        return
    if verb == "list":
        _handle_list(cwd, verbose)
        return

    _unreachable(verb)


# ---------------------------------------------------------------------------
# Handlers (thin wrappers — real logic lives in opencontext_sdd.*)
# ---------------------------------------------------------------------------


def _handle_status(change: str | None, cwd: Path, verbose: bool) -> None:
    """Resolve and print the SDD status."""
    from opencontext_sdd.status import Resolve

    status = Resolve(change or "", cwd=str(cwd))
    _print_json(status.model_dump(mode="json", exclude_none=True), verbose)


def _handle_review(change: str | None, cwd: Path, verbose: bool) -> None:
    """Run the structural review over the change's artifacts + diff.

    Persists ``review-report.json`` (canonical) plus a ``review.md`` companion
    rendered through the shared review machinery. Honest by design: without an
    executor/model the report carries static checks only — never fabricated
    model findings. A missing change exits 7 (SDD_ARTIFACTS_MISSING).
    """
    from opencontext_sdd.review import run_review

    from opencontext_cli.contracts.exit_codes import ExitCode

    envelope = run_review(change, cwd=str(cwd))
    if envelope.status == "blocked":
        payload = envelope.model_dump(mode="json", exclude_none=True)
        payload["exit_code"] = int(ExitCode.SDD_ARTIFACTS_MISSING)
        _print_json(payload, verbose)
        sys.exit(int(ExitCode.SDD_ARTIFACTS_MISSING))

    # Reuse the review machinery's merged-report renderer for the human artifact.
    report_rel = envelope.artifacts.get("review-report")
    if report_rel:
        from opencontext_cli.commands.review_cmd import merge_reports

        report_path = cwd / report_rel
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            merged = merge_reports(
                [
                    {
                        "role": "structural",
                        "findings": report.get("findings", []),
                        "summary": envelope.executive_summary,
                    }
                ]
            )
            review_md = report_path.with_name("review.md")
            review_md.write_text(merged + "\n", encoding="utf-8")
            envelope.artifacts["review"] = review_md.relative_to(cwd).as_posix()
        except (OSError, json.JSONDecodeError):
            pass  # canonical JSON artifact already persisted; companion is best-effort

    _print_json(envelope.model_dump(mode="json", exclude_none=True), verbose)


def _handle_continue(change: str | None, cwd: Path, verbose: bool) -> None:
    """Resume from the last incomplete phase (SDD-009).

    Resolves the change's disk status, prints the dispatcher markdown carrying
    ``nextRecommended``/``blockedReasons``, and — when the next step is a real
    phase — the deterministic prompt for that phase. Never emits a static,
    phase-less prompt.
    """
    from opencontext_sdd.dispatcher import RenderDispatcherMarkdown, RenderNativePhasePrompt
    from opencontext_sdd.status import Resolve

    status = Resolve(change, cwd=str(cwd))
    print(RenderDispatcherMarkdown(status))
    if status.nextRecommended in (*_PHASE_VERBS, "review"):
        tdd_mode = str(status.actionContext.get("tdd_mode", "ask"))
        print(
            RenderNativePhasePrompt(
                status.nextRecommended, change=status.changeName, tdd_mode=tdd_mode
            )
        )
    _refresh_change_manifest(cwd, status.changeName)


def _handle_ff(change: str | None, cwd: Path, verbose: bool) -> None:
    """Fast-forward: proposal → spec → design → tasks.

    Aborts the loop immediately when a phase returns a non-ok status,
    printing which phase blocked and why.
    """
    for phase in ("propose", "spec", "design", "tasks"):
        envelope = _run_phase(phase, cwd, change, verbose=verbose)
        if envelope.status not in ("ok", "partial"):
            _print_json(
                {
                    "ff_aborted": True,
                    "blocked_phase": phase,
                    "status": envelope.status,
                    "reason": envelope.executive_summary,
                    "risks": envelope.risks,
                },
                verbose,
            )
            return


def _handle_onboard(cwd: Path, verbose: bool) -> None:
    """Walk user through the SDD cycle."""
    console.header("SDD")
    console.print(f"SDD onboarding at {cwd}.")
    console.panel(
        "Run `opencontext sdd init` to bootstrap SDD context, then use the phase "
        "verbs (new, explore, propose, spec, design, tasks, apply, verify, archive) "
        "to advance through the full lifecycle.",
        title="Getting started",
    )


def _handle_list(cwd: Path, verbose: bool) -> None:
    """List active changes (the closed ``archive/`` folder is not a change)."""
    console.section("Active changes")
    changes_dir = cwd / "openspec" / "changes"
    names = (
        [
            child.name
            for child in sorted(changes_dir.iterdir())
            if child.is_dir() and child.name != "archive"
        ]
        if changes_dir.is_dir()
        else []
    )
    if names:
        for name in names:
            console.dim(f"  {name}")
    else:
        console.dim("  (no active changes)")


def _handle_new(change: str | None, cwd: Path, verbose: bool) -> None:
    """Create a new SDD change scaffold under ``openspec/changes/<change>/``.

    Previously ``sdd new`` routed through the status resolver and created nothing
    while reporting ``blocked`` — it now does the bounded, deterministic work the
    verb promises: make the change directory and a ``proposal.md`` stub.
    """
    if not change:
        eprint("Usage: opencontext sdd new <change-name>")
        sys.exit(2)
    change_dir = cwd / "openspec" / "changes" / change
    if change_dir.exists():
        _print_json({"status": "exists", "change": change, "path": str(change_dir)}, verbose)
        return
    change_dir.mkdir(parents=True, exist_ok=True)
    # NOTE: proposal.md is the canonical artifact name (status resolver,
    # dispatcher and oc_new all expect it); _detect_current_phase accepts it as
    # the propose-phase marker.
    (change_dir / "proposal.md").write_text(
        f"# Proposal: {change}\n\n- **Status:** draft\n\n"
        "## Intent\n\n<why this change>\n\n## Scope\n\n<what changes>\n",
        encoding="utf-8",
    )
    # SDD-ARTIFACTS: register the change and persist its state-machine position.
    from opencontext_sdd.artifacts import update_registry, write_change_manifest
    from opencontext_sdd.status import Resolve

    write_change_manifest(cwd, change)
    status = Resolve(change, cwd=str(cwd))
    update_registry(
        cwd,
        change,
        state=status.cycleState,
        path=change_dir.relative_to(cwd).as_posix(),
    )
    _print_json(
        {
            "status": "created",
            "change": change,
            "path": str(change_dir),
            "artifacts": ["proposal.md", "manifest.json"],
            "state": status.cycleState,
            "next_recommended": "spec",
        },
        verbose,
    )


def _handle_init(cwd: Path, verbose: bool) -> None:
    """Bootstrap the SDD structure: openspec scaffold + project SDD context.

    SDD-001 / SDD_CONTRACT artifact structure: init persists the project-level
    SDD context (``.opencontext/sdd/context.json`` + ``testing.md``) and the
    change registry, alongside the ``openspec/`` file-artifact store. An
    existing context.json (from install/wizard) is never overwritten.
    """
    openspec = cwd / "openspec"
    (openspec / "changes").mkdir(parents=True, exist_ok=True)
    (openspec / "specs").mkdir(parents=True, exist_ok=True)
    project_md = openspec / "project.md"
    created = not project_md.exists()
    if created:
        project_md.write_text(
            "# OpenSpec Project\n\nSDD file-artifact store. Changes live under "
            "`openspec/changes/<name>/`. Start one with `opencontext sdd new <name>`.\n",
            encoding="utf-8",
        )

    # Project SDD context (stack, testing capabilities, TDD mode). Created only
    # when missing so install/wizard settings are never stomped by a re-init.
    from opencontext_core.sdd_runtime import write_sdd_context

    context_path = cwd / ".opencontext" / "sdd" / "context.json"
    sdd_context_created = not context_path.exists()
    sdd_context_paths = [context_path]
    if sdd_context_created:
        _, sdd_context_paths = write_sdd_context(cwd)

    from opencontext_sdd.artifacts import ensure_registry

    registry_file = ensure_registry(cwd)

    _print_json(
        {
            "status": "initialized",
            "openspec": str(openspec),
            "created_project_md": created,
            "sdd_context": [p.relative_to(cwd).as_posix() for p in sdd_context_paths],
            "sdd_context_created": sdd_context_created,
            "registry": registry_file.relative_to(cwd).as_posix(),
            "next_recommended": "new",
        },
        verbose,
    )


def _handle_archive(change: str | None, cwd: Path, verbose: bool) -> None:
    """Close a verified change: move it under ``openspec/changes/archive/``
    preserving every evidence artifact (SDD-010).

    Fail-closed: without a passing verify-report the archive is blocked with
    exit code 7 (SDD_ARTIFACTS_MISSING) and nothing moves.
    """
    import shutil
    from datetime import UTC, datetime

    from opencontext_sdd.artifacts import mark_manifest_archived, update_registry
    from opencontext_sdd.status import Resolve

    from opencontext_cli.contracts.exit_codes import ExitCode

    status = Resolve(change, cwd=str(cwd))
    if status.changeRoot is None or status.nextRecommended != "archive":
        payload = {
            "status": "blocked",
            "phase": "archive",
            "change": status.changeName,
            "next_recommended": status.nextRecommended,
            "blocked_reasons": status.blockedReasons
            or ["archive requires a passing verify-report"],
            "exit_code": int(ExitCode.SDD_ARTIFACTS_MISSING),
        }
        _print_json(payload, verbose)
        sys.exit(int(ExitCode.SDD_ARTIFACTS_MISSING))

    change_root = cwd / status.changeRoot
    archive_root = cwd / "openspec" / "changes" / "archive"
    archive_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).date().isoformat()
    target = archive_root / f"{stamp}-{status.changeName}"
    suffix = 2
    while target.exists():
        target = archive_root / f"{stamp}-{status.changeName}-{suffix}"
        suffix += 1

    # Evidence inventory BEFORE the move: everything the change accumulated.
    evidence = sorted(
        p.relative_to(change_root).as_posix() for p in change_root.rglob("*") if p.is_file()
    )
    shutil.move(str(change_root), str(target))

    archive_report = {
        "schemaName": "opencontext.sdd-archive",
        "schemaVersion": 1,
        "change": status.changeName,
        "state": "archived",
        "archived_at": datetime.now(UTC).isoformat(),
        "archived_from": status.changeRoot,
        "evidence": evidence,
    }
    (target / "archive-report.json").write_text(
        json.dumps(archive_report, indent=2) + "\n", encoding="utf-8"
    )
    mark_manifest_archived(target, str(status.changeName))
    archived_to = target.relative_to(cwd).as_posix()
    update_registry(cwd, str(status.changeName), state="archived", path=archived_to)

    _print_json(
        {
            "status": "archived",
            "change": status.changeName,
            "archived_to": archived_to,
            "evidence": evidence,
            "next_recommended": "new",
        },
        verbose,
    )


def _handle_apply_execute(change: str | None, cwd: Path, verbose: bool) -> None:
    """Execute the apply phase with the shared OC Flow harness (SDD-007).

    Delegates to the same entry as ``opencontext run --workflow sdd`` so apply
    produces a normal run under ``.opencontext/runs/`` (SDD_CONTRACT rule:
    `apply` uses the same harness as OC Flow). Blocked (exit 7) when the change
    is not apply-ready.
    """
    from types import SimpleNamespace

    from opencontext_sdd.status import Resolve

    from opencontext_cli.contracts.exit_codes import ExitCode

    status = Resolve(change, cwd=str(cwd))
    if status.changeRoot is None or status.nextRecommended != "apply":
        payload = {
            "status": "blocked",
            "phase": "apply",
            "change": status.changeName,
            "next_recommended": status.nextRecommended,
            "blocked_reasons": status.blockedReasons
            or [f"apply is not the next dependency-ready phase ({status.nextRecommended})"],
            "exit_code": int(ExitCode.SDD_ARTIFACTS_MISSING),
        }
        _print_json(payload, verbose)
        sys.exit(int(ExitCode.SDD_ARTIFACTS_MISSING))

    from opencontext_cli.commands import run_cmd

    run_args = SimpleNamespace(
        task=(
            f"Apply SDD change '{status.changeName}' per {status.changeRoot}/tasks.md, "
            f"following {status.changeRoot}/specs/ and design.md"
        ),
        workflow="sdd",
        lane="fast",
        profile="balanced",
        root=str(cwd),
        json=True,
        resume=None,
        config=None,
        list_executors=False,
        yes=True,
        non_interactive=True,
    )
    rc = run_cmd.handle_run_exec(run_args)
    _refresh_change_manifest(cwd, status.changeName)
    sys.exit(int(rc))


def _refresh_change_manifest(cwd: Path, change: str | None) -> None:
    """Best-effort refresh of the per-change manifest's state-machine position."""
    if not change:
        return
    try:
        from opencontext_sdd.artifacts import write_change_manifest

        write_change_manifest(cwd, change)
    except Exception:
        pass  # the manifest is additive metadata; never mask the verb's result


def _run_phase(
    verb: str,
    cwd: Path,
    change: str | None,
    *,
    topic: str | None = None,
    task: str | None = None,
    verbose: bool = False,
) -> PhaseResultEnvelope:
    """Run an SDD phase via the orchestrator runner and return the envelope."""
    from opencontext_sdd.runner import run_phase

    envelope = run_phase(
        verb,
        change=change,
        cwd=str(cwd),
        topic=topic,
        task=task,
        verbose=verbose,
    )
    _print_json(envelope.model_dump(mode="json", exclude_none=True), verbose)
    # Honesty: these verbs RESOLVE and DISPATCH SDD phases over openspec files;
    # they do not themselves execute edits/gates. A "Ready for phase X" status
    # means "cleared to run", NOT "applied". Point the user at the real executor
    # so `sdd apply` is never mistaken for a completed mutation. stderr keeps
    # stdout JSON clean for machine consumers.
    if verb in {"apply", "verify"}:
        print(
            f"note: `opencontext sdd {verb}` resolves/dispatches the SDD phase; it does not "
            "execute edits or gates itself. To EXECUTE with the harness (real edits, TDD, "
            "gates) run `opencontext sdd apply --execute` / `opencontext run --workflow sdd` "
            "(or `opencontext oc-new`).",
            file=sys.stderr,
        )
    _refresh_change_manifest(cwd, change)
    return envelope


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _verb_help(verb: str) -> str:
    """Short help line for each verb."""
    HELP = {
        "init": "Bootstrap SDD context for the project.",
        "new": "Start a new SDD change.",
        "explore": "Explore an idea or requirement.",
        "propose": "Create a change proposal.",
        "spec": "Write detailed specs from the proposal.",
        "design": "Create technical design from specs.",
        "tasks": "Break design into implementation tasks.",
        "apply": "Implement tasks from specs and design.",
        "verify": "Validate implementation against specs.",
        "review": "Structural review of change artifacts + diff (honest, static).",
        "archive": "Archive a completed change.",
        "status": "Show structured status for the active change.",
        "continue": "Run the next dependency-ready phase.",
        "ff": "Fast-forward planning (proposal→spec→design→tasks).",
        "onboard": "Walk through SDD on the real codebase.",
        "list": "List active changes.",
    }
    return HELP.get(verb, verb.title())


def _print_json(data: Any, verbose: bool) -> None:
    """Pretty-print JSON to stdout."""
    json.dump(data, sys.stdout, indent=2, default=str)
    print()


def _unreachable(verb: str) -> None:
    raise SystemExit(f"Unreachable: unknown sdd verb '{verb}'")
