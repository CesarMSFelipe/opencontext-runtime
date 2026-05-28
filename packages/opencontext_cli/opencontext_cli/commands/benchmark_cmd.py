"""Benchmark CLI commands: run, list, and compare benchmarks."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from opencontext_core.dx.console_styles import console
from opencontext_core.evaluation.benchmark_suite import (
    BenchmarkSuite,
    format_benchmark_report_markdown,
    format_benchmark_result,
    format_benchmark_result_json,
    load_last_result,
    save_result,
)


def add_benchmark_parser(subparsers: Any) -> None:
    """Add benchmark command parsers."""
    bm_parser = subparsers.add_parser("benchmark", help="Run and manage benchmarks.")
    bm_sub = bm_parser.add_subparsers(dest="benchmark_command", required=True)

    # benchmark list
    list_parser = bm_sub.add_parser("list", help="List available benchmark cases.")
    list_parser.add_argument("--category", default=None, help="Filter by category.")

    # benchmark run
    run_parser = bm_sub.add_parser("run", help="Run benchmark cases.")
    run_parser.add_argument("--case", default=None, help="Specific case ID to run.")
    run_parser.add_argument("--category", default=None, help="Filter by category.")
    run_parser.add_argument(
        "--format",
        default="text",
        choices=["text", "json", "markdown"],
        help="Output format.",
    )
    run_parser.add_argument("--output", default=None, help="Output file (for markdown).")
    run_parser.add_argument("--save", action="store_true", help="Save results.")

    # benchmark compare
    compare_parser = bm_sub.add_parser("compare", help="Compare against last baseline.")
    compare_parser.add_argument(
        "--output", default=None, help="Output file for markdown comparison."
    )


def handle_benchmark(args: Any) -> None:
    """Handle benchmark commands."""
    command = args.benchmark_command

    if command == "list":
        _handle_list(args)
    elif command == "run":
        _handle_run(args)
    elif command == "compare":
        _handle_compare(args)


def _handle_list(args: Any) -> None:
    """List available benchmark cases."""
    suite = BenchmarkSuite()
    cases = suite.list_cases(category=args.category)

    if not cases:
        console.print("[yellow]No benchmark cases found.[/]")
        return

    from rich.table import Table

    table = Table(title=f"Benchmark Cases ({len(cases)})")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Category")
    table.add_column("Min Score", justify="right")

    for case in cases:
        table.add_row(case.id, case.name, case.category, str(case.expected_min_score))

    console.print(table)


def _handle_run(args: Any) -> None:
    """Run benchmark cases."""
    suite = BenchmarkSuite()

    # Determine which cases to run
    if args.case:
        case_ids = [args.case]
    elif args.category:
        cases = suite.list_cases(category=args.category)
        case_ids = [c.id for c in cases]
    else:
        case_ids = None

    with console.status("[bold green]Running benchmarks..."):
        result = suite.run(case_ids=case_ids)

    # Format output
    if args.format == "json":
        # Plain print to avoid Rich line wrapping breaking JSON
        print(format_benchmark_result_json(result))
    elif args.format == "markdown":
        output = format_benchmark_report_markdown(result, output_path=args.output)
        if not args.output:
            console.print(output)
    else:
        console.print(format_benchmark_result(result))

    if args.format == "markdown" and args.output:
        console.print(f"[green]Report written to {args.output}[/]")

    # Save baseline
    if args.save:
        path = save_result(result)
        # Print to stderr so it doesn't mix with JSON/markdown stdout output
        import sys as _sys

        print(f"Baseline saved to {path}", file=_sys.stderr)

    # Exit code
    if result.failed > 0:
        sys.exit(1)


def _handle_compare(args: Any) -> None:
    """Compare against last saved baseline."""
    from opencontext_core.evaluation.benchmark_suite import compare_results

    baseline = load_last_result()
    if baseline is None:
        console.print("[yellow]No baseline found. Run `opencontext benchmark run --save` first.[/]")
        sys.exit(1)

    suite = BenchmarkSuite()
    with console.status("[bold green]Running current benchmarks..."):
        current = suite.run()

    output = compare_results(baseline, current)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        console.print(f"[green]Comparison written to {args.output}[/]")
    else:
        console.print(output)

    # Check for regressions
    regressions = 0
    for r in current.results:
        b_map = {r.case_id: r.score.overall for r in baseline.results}
        if r.case_id in b_map and r.score.overall < b_map[r.case_id] - 2:
            regressions += 1

    if regressions:
        console.print(f"[red]{regressions} regression(s) detected.[/]")
        sys.exit(1)
