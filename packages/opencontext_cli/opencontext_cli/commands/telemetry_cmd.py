"""Telemetry CLI command — show cumulative token savings."""

from __future__ import annotations

from typing import Any

from opencontext_core.dx.console_styles import console


def add_telemetry_parser(subparsers: Any) -> None:
    tel_parser = subparsers.add_parser("telemetry", help="Token savings telemetry.")
    tel_sub = tel_parser.add_subparsers(dest="telemetry_command", required=True)
    show_parser = tel_sub.add_parser("show", help="Show cumulative token savings.")
    show_parser.add_argument("--root", default=".", help="Project root.")
    show_parser.add_argument("--last", type=int, default=None, help="Show only last N events.")
    tel_sub.add_parser("clear", help="Clear telemetry data.").add_argument("--root", default=".")
    export_parser = tel_sub.add_parser(
        "export", help="Export telemetry to the canonical .opencontext/telemetry/ layout."
    )
    export_parser.add_argument("--root", default=".", help="Project root.")


def handle_telemetry(args: Any) -> None:
    command = args.telemetry_command
    root = getattr(args, "root", ".")
    if command == "show":
        _handle_show(root, last=getattr(args, "last", None))
    elif command == "clear":
        _handle_clear(root)
    elif command == "export":
        _handle_export(root)


def _handle_export(root: str) -> None:
    """Mirror legacy savings telemetry into the canonical OC-OBS layout."""
    from opencontext_core.evaluation.telemetry import load_telemetry
    from opencontext_core.runtime_intelligence import telemetry_layout

    store = load_telemetry(root)
    directory = telemetry_layout.telemetry_dir(root)
    for event in store.events:
        telemetry_layout.append_event(
            "telemetry.savings.recorded",
            {
                "task": event.task,
                "naive_tokens": event.naive_tokens,
                "optimized_tokens": event.optimized_tokens,
                "reduction_pct": event.reduction_pct,
                "scenario": event.scenario,
            },
            root,
        )
    console.success(f"Exported {len(store.events)} event(s) to {directory}")


def _handle_show(root: str, last: int | None = None) -> None:
    from opencontext_core.evaluation.telemetry import load_telemetry

    store = load_telemetry(root)
    console.header("Token Savings")
    if not store.events:
        console.info(
            "No telemetry yet. Run 'opencontext pack . --query <task>' to start tracking."
        )
        return

    events = store.events[-last:] if last else store.events

    console.print(f"\n  {len(store.events)} total events\n")
    console.print(f"  Total tokens saved : [green]{store.total_saved:>10,}[/]")
    console.print(f"  Avg reduction      : [green]{store.average_reduction:>9.1f}%[/]")
    console.print(f"  Naive total        :         {store.total_naive:>10,}")
    console.print(f"  Optimized total    :         {store.total_optimized:>10,}")

    console.table(
        f"Recent Events ({len(events)})",
        ["Scenario", "Naive", "Optimized", "Reduction"],
        [
            [
                e.scenario or e.task[:50],
                f"{e.naive_tokens:,}",
                f"{e.optimized_tokens:,}",
                f"{e.reduction_pct:.1f}%",
            ]
            for e in reversed(events)
        ],
    )


def _handle_clear(root: str) -> None:
    import json
    from pathlib import Path

    from opencontext_core.evaluation.telemetry import (
        CANONICAL_EVENTS_FILE,
        CANONICAL_TELEMETRY_DIR,
        TELEMETRY_FILE,
    )

    cleared = False

    # The canonical ledger is shared with other event families, so drop only the
    # savings lines rather than deleting the whole append-only file.
    events_path = Path(root) / CANONICAL_TELEMETRY_DIR / CANONICAL_EVENTS_FILE
    if events_path.exists():
        kept: list[str] = []
        for line in events_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError:
                kept.append(line)
                continue
            if isinstance(record, dict) and record.get("event") == "telemetry.savings.recorded":
                cleared = True
                continue
            kept.append(line)
        if cleared:
            events_path.write_text(
                "".join(f"{line}\n" for line in kept), encoding="utf-8"
            )

    # Remove any pre-canonical legacy single file outright.
    legacy_path = Path(root) / TELEMETRY_FILE
    if legacy_path.exists():
        legacy_path.unlink()
        cleared = True

    if cleared:
        console.success("Telemetry cleared.")
    else:
        console.info("No telemetry yet.")
