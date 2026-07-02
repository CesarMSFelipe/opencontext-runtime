"""runs — inspect persisted harness runs.

Usage:
  opencontext runs list [--json]
  opencontext runs show <run_id> [--json]
  opencontext runs artifacts <run_id> [--json]

Reads the on-disk run directories the harness writes to
``.opencontext/runs/<run_id>/`` (run.json, gates.json, artifacts.json, ...),
preferring the RunStore index and falling back to a directory scan so runs
created before the index existed still appear.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from opencontext_core.harness.run_store import RunStore


def _root(args: Any) -> Path:
    return Path(getattr(args, "root", None) or Path.cwd())


def _runs_dir(root: Path) -> Path:
    return root / ".opencontext" / "runs"


def _list_run_ids(root: Path) -> list[str]:
    """Run ids from the RunStore index, unioned with on-disk run dirs."""
    ids: set[str] = set(RunStore(root).list_run_ids())
    runs_dir = _runs_dir(root)
    if runs_dir.is_dir():
        for child in runs_dir.iterdir():
            if child.is_dir() and (child / "run.json").exists():
                ids.add(child.name)
    return sorted(ids)


def _run_dir(root: Path, run_id: str) -> Path:
    return _runs_dir(root) / run_id


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def add_run_exec_parser(subparsers: Any) -> None:
    """Add the ``run`` execution command (PR-007 OC Flow, FLOW-16).

    ``opencontext run "<task>" --workflow oc-flow`` is the first-run operational
    entry point (book §25). ``--workflow auto`` lets the runtime pick OC Flow for a
    localized task and recommend SDD when the task is broad/high-risk.
    """
    run_parser = subparsers.add_parser(
        "run",
        help="Run an operational task with OC Flow (the fast, local-first workflow).",
        description=(
            "Run a localized engineering task (failing test, small bugfix, lint/type "
            "error, small refactor) through OC Flow. Flag-gated by "
            "runtime.oc_flow_enabled."
        ),
    )
    run_parser.add_argument("task", nargs="?", help="The task to perform, e.g. 'Fix failing test'.")
    run_parser.add_argument(
        "--workflow",
        default="oc-flow",
        choices=["oc-flow", "auto"],
        help="Workflow to run (default: oc-flow; 'auto' selects oc-flow/sdd by task).",
    )
    run_parser.add_argument(
        "--lane",
        default="fast",
        choices=["fast", "cheap", "careful"],
        help="Execution lane (context depth, diagnosis budget, strictness).",
    )
    run_parser.add_argument(
        "--profile", default="balanced", help="Execution profile (default: balanced)."
    )
    run_parser.add_argument("--resume", default=None, help="Resume a run: <session_id>/<run_id>.")
    run_parser.add_argument("--root", default=None, help="Project root (default: cwd).")
    run_parser.add_argument(
        "--config",
        default=None,
        help="Explicit config path (overrides <root>/opencontext.yaml).",
    )
    run_parser.add_argument("--json", action="store_true", help="JSON output.")


def handle_run_exec(args: Any) -> None:
    """Dispatch the ``run`` execution command via RuntimeApi (C15 spine flip).

    Routes through :class:`~opencontext_core.runtime.api.RuntimeApi`:
    ``start_session()`` then ``run()``.  NEVER ``run_workflow`` (amendment A1).

    Rollback: revert ``state=MigrationState.migrated`` to ``state=MigrationState.legacy``
    for rt-spine and mcp-runtime in ``compat/migration.py`` and restore the legacy
    branch below.
    """
    from opencontext_core.config_resolver import missing_config_hint, resolve_config_path
    from opencontext_core.runtime.api import RunRequest, RuntimeApi, StartSessionRequest

    root = _root(args)
    # B2 / ADR-A2: read the SAME path install writes (<root>/opencontext.yaml),
    # via the one shared resolver — never the old hardcoded configs/ subpath.
    config_path = resolve_config_path(root, getattr(args, "config", None))
    if not config_path.exists():
        # Config is advisory for this explicit CLI (run defaults oc-flow on), but
        # a missing config still earns an actionable nudge (path + how to fix).
        # This diagnostic always goes to STDERR so STDOUT carries only the run
        # summary — in --json mode that is ONLY the JSON object, keeping
        # `json.load(stdout)` clean.
        print(missing_config_hint(root), file=sys.stderr)

    # Spine path (commit-007 / C15): start_session -> run. NO run_workflow.
    task = getattr(args, "task", None) or ""
    workflow = getattr(args, "workflow", "oc-flow")
    lane = getattr(args, "lane", "fast")
    profile = getattr(args, "profile", "balanced")

    # R2: pre-run cost estimate hint — one stderr line, never blocks, silent on failure.
    try:
        from opencontext_core.runtime_intelligence.cost import CostEngine

        _est = CostEngine().estimate(task, workflow, lane, root=root)
        print(
            f"[oc] estimate: ~{_est.estimated_input_tokens} tokens"
            f", ~{_est.estimated_duration_s}s ({workflow}, {lane} lane)",
            file=sys.stderr,
        )
    except Exception:
        pass  # estimate failure is a silent skip per honesty rules

    api = RuntimeApi(root)
    session = api.start_session(
        StartSessionRequest(task=task, root=str(root), profile=profile)
    )
    result = api.run(
        RunRequest(session_id=session.session_id, workflow_id=workflow, task=task)
    )
    # B1 / PROD-004: result.status is _legacy_status(legacy) which preserves
    # OC Flow terminal vocabulary ("completed", "needs_executor", etc.) and
    # translates harness GateStatus values.  Use it directly.
    oc_status = result.status
    leg = result.legacy
    # Resolve the workflow actually executed (e.g. "auto" → "oc-flow").  For
    # OCFlowRunResult the workflow_selection receipt carries the resolved name.
    sel = getattr(leg, "workflow_selection", None) or {}
    resolved_workflow = sel.get("workflow") or workflow
    # B1 / shape-parity: expose the full OCFlowRunResult vocabulary so --json
    # consumers (tests, automation) that relied on run_oc_flow_cli fields
    # (artifacts_dir, selection_reason, final_node, session_id, run_id) keep
    # working.  For non-OC-Flow legacy results, only the 4 core fields are
    # emitted.
    ocflow_session_id = getattr(leg, "session_id", None) or session.session_id
    ocflow_run_id = getattr(leg, "run_id", None) or result.run_id
    artifacts_dir = getattr(leg, "artifacts_dir", None)
    summary: dict[str, object] = {
        "status": oc_status,
        "session_id": ocflow_session_id,
        "run_id": ocflow_run_id,
        "workflow": resolved_workflow,
    }
    if artifacts_dir is not None:
        summary["artifacts_dir"] = str(artifacts_dir)
    for _field in (
        "final_node", "visited", "total_tokens", "diagnosis_attempts",
        "escalated", "graph_status", "completion_reason", "mutation_required",
        "verified_by", "verification_outcome",
    ):
        _v = getattr(leg, _field, None)
        if _v is not None:
            summary[_field] = _v
    if sel.get("reason"):
        summary["selection_reason"] = sel["reason"]
    if getattr(args, "json", False):
        print(json.dumps(summary, indent=2, default=str))
    else:
        print(f"OC Flow (spine): {summary.get('status')}")
        print(f"  workflow: {summary.get('workflow')}")
        print(f"  session_id: {summary.get('session_id')}")
        print(f"  run_id: {summary.get('run_id')}")
    # B1 / PROD-004: a mutation that found no executor/provider is reported honestly
    # as needs_executor / needs_provider. Print an actionable next step naming at
    # least one concrete remedy. STDERR keeps the --json STDOUT payload pure JSON.
    if oc_status in {"needs_executor", "needs_provider"}:
        print(
            "Hint: enable mutation by configuring a provider "
            "(export ANTHROPIC_API_KEY=... / OPENAI_API_KEY=...), an MCP sampler, or "
            "set `provider: test_stub` + `edits_file` in opencontext.yaml; see "
            "`opencontext doctor`.",
            file=sys.stderr,
        )


def add_simulate_parser(subparsers: Any) -> None:
    """Add the top-level ``simulate`` command (PR-013, SPEC-CLI-013-08 / CLI-CONV).

    A provider-free dry run: previews the selected workflow, policy decisions and
    estimated cost WITHOUT executing any mutation. Uses the Runtime Intelligence
    :class:`RuntimeSimulator` (zero provider calls) and the ``PolicySimulator``.
    """
    from opencontext_cli.output import add_output_flag

    parser = subparsers.add_parser(
        "simulate",
        help="Preview a task (workflow, policy, cost) without running it.",
        description=(
            "Dry-run a task through the shared Runtime API: predict the workflow, "
            "lane, expected files, risk, policy decisions and estimated cost with "
            "ZERO provider calls and no file changes."
        ),
    )
    parser.add_argument("task", nargs="?", help="The task to simulate.")
    parser.add_argument("--root", default=".", help="Project root (default: cwd).")
    parser.add_argument("--json", action="store_true", help="JSON output (alias of --output json).")
    add_output_flag(parser)


def handle_simulate(args: Any) -> None:
    """Run the provider-free simulation and render it. Never mutates files."""
    import sys

    from opencontext_cli.output import emit, resolve_output_mode
    from opencontext_core.runtime_intelligence.simulator import RuntimeSimulator
    from opencontext_core.tools.policy import ToolPermissionPolicy
    from opencontext_core.tools.simulator import PolicySimulator

    task = getattr(args, "task", None)
    if not task:
        print('Usage: opencontext simulate "<task>"', file=sys.stderr)
        sys.exit(2)
    root = getattr(args, "root", ".")

    report = RuntimeSimulator().simulate(task, root=root, emit=False)
    cost = report.cost_estimates[0] if report.cost_estimates else None

    # Preview the policy decisions for the representative write/run tools against
    # the safe-default read-only allowlist (mirrors the MCP default posture).
    policy = ToolPermissionPolicy(
        allowed_tools={
            "opencontext_search",
            "opencontext_context",
            "opencontext_node",
            "opencontext_status",
            "opencontext_quality",
        }
    )
    preview_tools = [
        "opencontext_search",
        "opencontext_run",
        "opencontext_replace_symbol_body",
    ]
    decisions = [d.model_dump() for d in PolicySimulator(policy).simulate(preview_tools)]

    data = {
        "task": task,
        "workflow": report.recommended_workflow,
        "lane": report.recommended_lane,
        "expected_files": report.expected_files,
        "risk_flags": report.risk_flags,
        "confidence": report.confidence_estimate,
        "recommendation": report.recommendation,
        "estimated_cost": cost.model_dump() if cost is not None else {},
        "policy_decisions": decisions,
        "provider_calls": report.provider_calls,
        "mutated": False,
    }

    def _human(d: dict[str, Any]) -> None:
        print(f"Task          : {d['task']}")
        print(f"Workflow      : {d['workflow']} (lane: {d['lane']})")
        print(f"Confidence    : {d['confidence']}")
        if d["risk_flags"]:
            print(f"Risk          : {', '.join(d['risk_flags'])}")
        if d["estimated_cost"]:
            c = d["estimated_cost"]
            print(
                f"Est. cost     : ~{c.get('estimated_input_tokens', 0)} in / "
                f"{c.get('estimated_output_tokens', 0)} out tokens, "
                f"{c.get('estimated_duration_s', 0)}s"
            )
        print(f"Recommendation: {d['recommendation']}")
        print("Policy preview:")
        for dec in d["policy_decisions"]:
            print(f"  [{dec['decision']}] {dec['tool']} ({dec['reason']})")
        print("No files were changed (dry run).")

    emit(data, resolve_output_mode(args), _human)


def _print_profile(run_dir: Path) -> None:
    """Print per-component timing profile from trace.json (R3).

    Reads ``timings_ms`` from ``run_dir/trace.json``.  When the file is absent
    or has no timing data, prints an honest "no trace recorded" line and returns
    — never crashes or raises.
    """
    trace_path = run_dir / "trace.json"
    if not trace_path.exists():
        print("\nProfile: no trace recorded for this run.")
        return
    try:
        raw = _read_json(trace_path)
        if not isinstance(raw, dict):
            print("\nProfile: no trace recorded for this run.")
            return
        timings = raw.get("timings_ms") or {}
        if not timings:
            print("\nProfile: no trace recorded for this run.")
            return

        from opencontext_core.runtime_intelligence.profiler import RuntimeProfiler

        # Duck-typed proxy: RuntimeProfiler only needs .run_id and .timings_ms.
        class _TraceProxy:
            def __init__(self, run_id: str, timings_ms: dict[str, float]) -> None:
                self.run_id = run_id
                self.timings_ms = timings_ms

        proxy = _TraceProxy(
            run_id=raw.get("run_id", run_dir.name),
            timings_ms={k: float(v) for k, v in timings.items()},
        )
        report = RuntimeProfiler().profile(proxy)  # type: ignore[arg-type]

        print("\nProfile (per-component time share):")
        for component, share in sorted(
            report.cost_by_component.items(), key=lambda kv: kv[1], reverse=True
        ):
            bar = "#" * max(1, int(share * 20))
            print(f"  {component:<20} {share:>6.1%}  {bar}")
        if report.recommendations:
            print(f"  Recommendation: {report.recommendations[0]}")
    except Exception as exc:
        # Profiler failure is non-fatal — honest degraded message.
        print(f"\nProfile: could not load trace ({exc}).")


def add_run_parser(subparsers: Any) -> None:
    """Add the ``runs`` command group."""

    runs_parser = subparsers.add_parser("runs", help="Inspect persisted harness runs.")
    runs_subs = runs_parser.add_subparsers(dest="runs_action")

    list_p = runs_subs.add_parser("list", help="List persisted run IDs.")
    list_p.add_argument("--json", action="store_true", help="JSON output.")

    show_p = runs_subs.add_parser("show", help="Show a run summary.")
    show_p.add_argument("run_id", help="Run ID.")
    show_p.add_argument("--json", action="store_true", help="JSON output.")
    show_p.add_argument(
        "--profile",
        action="store_true",
        default=False,
        help="Show per-component timing profile from trace (if available).",
    )

    art_p = runs_subs.add_parser("artifacts", help="List a run's artifact files.")
    art_p.add_argument("run_id", help="Run ID.")
    art_p.add_argument("--json", action="store_true", help="JSON output.")


def handle_run_inspect(args: Any) -> None:
    """Dispatch the ``runs`` sub-command."""

    action = getattr(args, "runs_action", None)
    root = _root(args)

    if action == "list":
        ids = _list_run_ids(root)
        if getattr(args, "json", False):
            print(json.dumps(ids, indent=2))
        else:
            for rid in ids:
                print(rid)
        return

    if action == "show":
        run_dir = _run_dir(root, args.run_id)
        run_json = _read_json(run_dir / "run.json")
        if run_json is None:
            print(f"Run not found: {args.run_id}", file=sys.stderr)
            sys.exit(1)
        gates = _read_json(run_dir / "gates.json") or {}
        artifacts = _read_json(run_dir / "artifacts.json") or {}
        summary = {
            "run_id": run_json.get("run_id", args.run_id),
            "workflow": run_json.get("workflow"),
            "task": run_json.get("task"),
            "status": run_json.get("status"),
            "created_at": run_json.get("created_at"),
            "gates": len(gates.get("gates", []) if isinstance(gates, dict) else []),
            "artifacts": len(artifacts.get("artifacts", []) if isinstance(artifacts, dict) else []),
        }
        print(json.dumps(summary, indent=2))

        # R3: per-component profiler surface (--profile flag).
        if getattr(args, "profile", False):
            _print_profile(run_dir)

        return

    if action == "artifacts":
        run_dir = _run_dir(root, args.run_id)
        if not run_dir.is_dir():
            print(f"Run not found: {args.run_id}", file=sys.stderr)
            sys.exit(1)
        names = sorted(p.name for p in run_dir.iterdir() if p.is_file())
        if getattr(args, "json", False):
            print(json.dumps(names, indent=2))
        else:
            for name in names:
                print(name)
        return

    print("Usage: opencontext runs [list|show|artifacts]")
    sys.exit(1)
