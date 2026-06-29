"""``opencontext health`` — Runtime Intelligence self-health report (PR-011).

Renders the 10-dimension :class:`RuntimeHealthReport` (book §13), composing the
existing KG graph-health report and the other runtime-health signals. Read-only;
it never alters runtime behaviour. The Runtime Intelligence layer is advisory and
default-off — when the ``runtime_intelligence_enabled`` flag is off this command
still produces the report (it is harmless diagnostics) and notes the flag state.
"""

from __future__ import annotations

from typing import Any

from opencontext_core.dx.console_styles import console


def add_health_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "health", help="Runtime Intelligence self-health report (10 dimensions)."
    )
    parser.add_argument("--root", default=".", help="Project root.")
    parser.add_argument("--json", action="store_true", help="Emit JSON.")


def handle_health(args: Any) -> None:
    from opencontext_core.runtime_intelligence.health import RuntimeHealth
    from opencontext_core.runtime_intelligence.health_evidence import collect_health_evidence
    from opencontext_core.runtime_intelligence.reports import render_health_report, to_json

    root = getattr(args, "root", ".")
    # B9 / AVH-016: ground every dimension in real recorded evidence; a dimension
    # with no evidence source is reported UNMEASURED, never a fabricated score.
    evidence = collect_health_evidence(root)
    report = RuntimeHealth().report(root, emit=True, **evidence)

    if getattr(args, "json", False):
        print(to_json(report))  # pure JSON to stdout
        return

    console.header("Runtime Health")
    console.print(render_health_report(report))
    if not _flag_enabled(root):
        console.print(
            "[dim]runtime_intelligence is disabled in config "
            "(read-only preview; set runtime_intelligence_enabled: true to enable).[/]"
        )


def _flag_enabled(root: str) -> bool:
    try:
        from opencontext_core.config import find_config, load_config

        path = find_config(root)
        if path is None:
            return False
        config = load_config(path)
        return bool(getattr(config, "runtime_intelligence_enabled", False))
    except Exception:
        return False
