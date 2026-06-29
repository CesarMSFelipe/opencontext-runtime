"""Benchmark CLI commands: run, list, and compare the honest efficiency benchmark.

``opencontext benchmark run`` measures the REAL cost of building task context WITH
OpenContext (CON — a single ``prepare_context`` call) against a realistic
OpenContext-free control (SIN — a ``grep`` + full-``Read`` loop), under a mandatory
quality-parity gate. It reports measured ``{tokens, tool_calls, latency}`` deltas —
NOT a marketing claim. The exit code reflects quality parity (any case whose CON pack
misses an expected source or hits a forbidden one fails), never a reduction threshold.
"""

from __future__ import annotations

import importlib.resources
import sys
from pathlib import Path
from typing import Any

from opencontext_cli.output import eprint
from opencontext_core.dx.console_styles import BrandConsole, console
from opencontext_core.evaluation.efficiency import (
    EfficiencyBenchmark,
    format_efficiency_report,
    format_efficiency_report_json,
    load_last_efficiency_result,
    save_efficiency_result,
)
from opencontext_core.evaluation.evaluator import load_context_bench_cases
from opencontext_core.runtime import OpenContextRuntime

# NOTE: Resolve via importlib.resources so DEFAULT_SUITE works under editable install
# and wheel alike. The yaml is packaged as opencontext_cli/data/contextbench.yaml.
DEFAULT_SUITE = str(importlib.resources.files("opencontext_cli").joinpath("data/contextbench.yaml"))


def _stderr_console() -> BrandConsole:
    """Brand console bound to STDERR so diagnostics never pollute stdout/JSON."""
    bc = BrandConsole()
    if getattr(bc, "_console", None) is not None:
        from rich.console import Console as _Console

        bc._console = _Console(stderr=True)
    return bc


err_console = _stderr_console()


def add_benchmark_parser(subparsers: Any) -> None:
    """Add benchmark command parsers."""
    bm_parser = subparsers.add_parser(
        "benchmark", help="Run the honest efficiency benchmark (CON vs grep+Read control)."
    )
    bm_sub = bm_parser.add_subparsers(dest="benchmark_command", required=True)

    list_parser = bm_sub.add_parser("list", help="List available efficiency benchmark cases.")
    list_parser.add_argument("--suite", default=DEFAULT_SUITE, help="ContextBench suite path.")
    list_parser.add_argument(
        "--category", default=None, help="Filter by difficulty (simple|medium|hard)."
    )

    run_parser = bm_sub.add_parser("run", help="Run efficiency benchmark cases.")
    run_parser.add_argument("--suite", default=DEFAULT_SUITE, help="ContextBench suite path.")
    run_parser.add_argument("--case", default=None, help="Specific case ID to run.")
    run_parser.add_argument(
        "--category", default=None, help="Filter by difficulty (simple|medium|hard)."
    )
    run_parser.add_argument("--root", default=".", help="Project root to benchmark.")
    run_parser.add_argument("--max-tokens", type=int, default=6000)
    run_parser.add_argument(
        "--format", default="text", choices=["text", "json", "markdown"], help="Output format."
    )
    run_parser.add_argument("--output", default=None, help="Output file (for markdown).")
    run_parser.add_argument("--save", action="store_true", help="Save results.")
    run_parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="Use the existing pinned index instead of refreshing once (CI fast path).",
    )

    bm_sub.add_parser("compare", help="Show the last saved efficiency benchmark result.")

    suite_parser = bm_sub.add_parser(
        "suite", help="Run the unified cognitive benchmark suites (the ten 1.0 gates)."
    )
    suite_sub = suite_parser.add_subparsers(dest="suite_command", required=True)
    suite_sub.add_parser("list", help="List the registered benchmark suites.")
    suite_run = suite_sub.add_parser("run", help="Run one suite or all suites.")
    suite_run.add_argument("name", nargs="?", default=None, help="Suite name (default: all).")
    suite_run.add_argument("--root", default=".", help="Repo root to benchmark.")
    suite_run.add_argument("--smoke", action="store_true", help="Run the fast smoke subset.")

    bm_sub.add_parser(
        "suites", help="List the Runtime Intelligence benchmark suite taxonomy (13 suites)."
    )

    h2h = bm_sub.add_parser(
        "head2head",
        help=(
            "Panel head-to-head: OpenContext (surgical) vs a prose-skill + grep "
            "loop vs a careful grep agent — on tokens AND capabilities."
        ),
    )
    h2h.add_argument("--repos", required=True, help="Comma-separated repo roots to evaluate.")
    h2h.add_argument("--query", required=True, help="The task / change to gather context for.")
    h2h.add_argument(
        "--target", default="", help="Target symbol name (derived from the query if omitted)."
    )
    h2h.add_argument("--format", choices=["text", "json"], default="text")


def handle_benchmark(args: Any) -> None:
    """Handle benchmark commands."""
    command = args.benchmark_command
    if command == "list":
        _handle_list(args)
    elif command == "run":
        _handle_run(args)
    elif command == "compare":
        _handle_compare(args)
    elif command == "suites":
        _handle_suites(args)
    elif command == "suite":
        _handle_suite(args)
    elif command == "head2head":
        _handle_head2head(args)


def _handle_suite(args: Any) -> None:
    """`benchmark suite list|run` over the unified BenchmarkRunner (the ten 1.0 gates)."""
    import json as _json

    from opencontext_core.evaluation.runner import build_default_runner

    runner = build_default_runner()
    if args.suite_command == "list":
        console.header("Benchmark Suites")
        for name in runner.list_suites():
            console.print(f"  - {name}")
        return
    # run
    smoke = bool(getattr(args, "smoke", False))
    root = getattr(args, "root", ".")
    suite_name = getattr(args, "name", None)
    reports = (
        [runner.run(suite_name, root, smoke=smoke)]
        if suite_name
        else runner.run_all(root, smoke=smoke)
    )
    print(_json.dumps([r.model_dump(mode="json") for r in reports], indent=2))
    # Honest exit: only a real FAILED gate is a failure; NOT_MEASURED never blocks.
    if any(r.status.value == "failed" for r in reports):
        sys.exit(1)


def _handle_suites(args: Any) -> None:
    """List the 13-suite benchmark taxonomy and which suites have an honest runner."""
    from opencontext_core.runtime_intelligence.benchmarks import BenchmarkSystem

    system = BenchmarkSystem()
    console.header("Benchmark Suite Taxonomy")
    console.print("[bold]Runtime Intelligence benchmark suites (13):[/]")
    for suite in system.list_suites():
        status = "implemented" if system.is_implemented(suite) else "declared (not measured)"
        console.print(f"  - {suite}: {status}")


_CAP_FIELDS = (
    "portability",
    "tdd_gate",
    "kg_grounding",
    "impact_consulted",
    "memory_used",
    "spec_artifact",
    "artifact_chain",
    "correctness",
)


def _handle_head2head(args: Any) -> None:
    """Run the multi-arm head-to-head and print per-repo tokens + capability matrix."""
    import json as _json

    from opencontext_core.evaluation.models import ContextBenchCase
    from opencontext_core.evaluation.multi_arm import run_head_to_head
    from opencontext_core.evaluation.oc_arm import oc_arm_runner, semantic_layer_enabled

    repos = [r.strip() for r in str(args.repos).split(",") if r.strip()]
    case = ContextBenchCase(
        id="head2head", query=args.query, target_symbol=getattr(args, "target", "") or ""
    )
    semantic = semantic_layer_enabled(repos[0]) if repos else False
    reports = run_head_to_head(repos, [case], oc_arm_runner=oc_arm_runner, semantic_layer=semantic)

    if getattr(args, "format", "text") == "json":
        payload = [
            {
                "repo": r.repo,
                "arms": [
                    {
                        "arm": a.arm,
                        "tokens": a.tokens,
                        "tool_calls": a.tool_calls,
                        "latency_ms": round(a.latency_ms, 1),
                    }
                    for a in r.arms
                ],
                "matrix": {name: vars(m) for name, m in r.matrix.items()},
                "semantic_layer": r.semantic_layer,
            }
            for r in reports
        ]
        print(_json.dumps(payload, indent=2))
        return

    console.header("Benchmark Head-To-Head")
    for r in reports:
        layer = "on" if r.semantic_layer else "off"
        console.print(f"\n[bold]{r.repo}[/]  (semantic_layer: {layer})")
        rows = []
        for a in sorted(r.arms, key=lambda x: x.tokens):
            m = r.matrix.get(a.arm)
            flags = (
                "".join("1" if (m and getattr(m, f)) else "0" for f in _CAP_FIELDS) if m else "-"
            )
            rows.append(
                [a.arm, str(a.tokens), str(a.tool_calls), f"{a.latency_ms:.0f}", flags]
            )
        console.table("Arms", ["Arm", "Tokens", "Calls", "ms", "Capabilities"], rows)
        oc = next((a for a in r.arms if a.arm == "OC-SURGICAL"), None)
        if oc is not None:
            cheaper = [a.arm for a in r.arms if a.arm != "OC-SURGICAL" and oc.tokens < a.tokens]
            console.success(f"OC-SURGICAL cheaper than: {', '.join(cheaper) or 'none'}")
    console.dim("capabilities = " + ",".join(_CAP_FIELDS))


def _runtime(args: Any) -> OpenContextRuntime:
    config_path = getattr(args, "config", None)
    resolved = Path(config_path) if config_path else None
    return OpenContextRuntime(
        config_path=str(resolved) if resolved and resolved.exists() else None,
    )


def _select_cases(args: Any) -> list[Any]:
    suite_path = getattr(args, "suite", DEFAULT_SUITE)
    # NOTE: REQ-07 — fail loudly when the suite path doesn't exist and the caller
    # is relying on the default (i.e. not in the development repository).
    if not Path(suite_path).exists():
        eprint(
            "--suite is required outside the development repository. "
            "Provide a contextbench.yaml path with --suite.\n"
            f"(Resolved suite path does not exist: {suite_path})"
        )
        raise SystemExit(1)
    cases = load_context_bench_cases(suite_path)
    case_id = getattr(args, "case", None)
    category = getattr(args, "category", None)
    if case_id:
        cases = [c for c in cases if c.id == case_id]
    if category:
        cases = [c for c in cases if c.difficulty == category]
    return cases


def _handle_list(args: Any) -> None:
    """List available efficiency benchmark cases."""
    cases = _select_cases(args)
    console.header("Efficiency Benchmark Cases")
    if not cases:
        console.info("No benchmark cases yet.")
        return

    rows = [
        [
            case.id,
            case.difficulty or "-",
            case.target_symbol or "(derived)",
            f"{case.min_source_coverage:.2f}",
        ]
        for case in cases
    ]
    console.table(
        f"Cases ({len(cases)})",
        ["ID", "Difficulty", "Target Symbol", "Min Coverage"],
        rows,
    )


def _handle_run(args: Any) -> None:
    """Run the efficiency benchmark and report CON vs SIN cost honestly."""
    if sys.stdout.encoding and "utf" not in sys.stdout.encoding.lower():
        import io

        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    cases = _select_cases(args)
    if not cases:
        eprint("No benchmark cases match the given filters.")
        sys.exit(1)

    runtime = _runtime(args)
    bench = EfficiencyBenchmark(
        runtime,
        root=getattr(args, "root", "."),
        max_tokens=getattr(args, "max_tokens", 6000),
    )
    refresh = not getattr(args, "no_refresh", False)

    if args.format == "json":
        report = bench.evaluate_suite(cases, refresh_index=refresh)
    else:
        with console.status("[bold green]Running efficiency benchmark..."):
            report = bench.evaluate_suite(cases, refresh_index=refresh)

    if args.format == "json":
        print(format_efficiency_report_json(report))
    elif args.format == "markdown":
        output = _format_markdown(report)
        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
            console.success(f"Report written to {args.output}")
        else:
            print(output)
    else:
        console.header("Efficiency Benchmark")
        console.print(format_efficiency_report(report))

    if args.save:
        path = save_efficiency_result(report)
        # Diagnostic on stderr so --format json stdout stays pure.
        err_console.success(f"Result saved to {path}")

    # Exit code gates on quality parity only (D-CI): no reduction threshold.
    if not report.all_sufficient:
        sys.exit(1)


def _handle_compare(args: Any) -> None:
    """Show the last saved efficiency benchmark result."""
    last = load_last_efficiency_result()
    if last is None:
        eprint("No saved result. Run `opencontext benchmark run --save` first.")
        sys.exit(1)
    console.header("Efficiency Benchmark")
    console.print(format_efficiency_report(last))


def _format_markdown(report: Any) -> str:
    """Minimal markdown rendering of the efficiency report (no claim string)."""
    lines = [
        "# OpenContext Efficiency Benchmark",
        "",
        "Context WITH OpenContext (CON) vs a realistic grep+Read control (SIN). "
        "Measured numbers only.",
        "",
        "| case | parity | CON tok | SIN tok | Δtok | CON calls | SIN calls | CON ms | SIN ms |",
        "|------|--------|--------:|--------:|-----:|----------:|----------:|-------:|-------:|",
    ]
    for c in report.cases:
        parity = "ok" if c.con_sufficient else "INSUFF"
        lines.append(
            f"| {c.case_id} | {parity} | {c.con.tokens} | {c.sin.tokens} | {c.token_delta} | "
            f"{c.con.tool_calls} | {c.sin.tool_calls} | {c.con.latency_ms:.0f} | "
            f"{c.sin.latency_ms:.0f} |"
        )
    lines += [
        "",
        f"- cases: {len(report.cases)} ({report.insufficient_cases} parity-insufficient)",
        f"- median token delta (SIN - CON): {report.median_token_delta}",
        f"- median tool-call delta (SIN - CON): {report.median_tool_call_delta}",
    ]
    return "\n".join(lines)
