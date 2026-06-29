"""maturity — assess project adoption maturity (PR-013, CLI-CONV maturity assess).

``opencontext maturity assess`` scores readiness across five dimensions
(config / knowledge-graph / memory / harness / benchmark) from on-disk signals
and recommends the single highest-value next action. Read-only; no model calls.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from opencontext_cli.output import add_output_flag, emit, eprint, resolve_output_mode
from opencontext_core.dx.console_styles import console

# dimension -> (level, score 0..1, recommendation)
_READY = "ready"
_BASIC = "basic"
_NONE = "none"


def _root(args: Any) -> Path:
    return Path(getattr(args, "root", None) or Path.cwd())


def add_maturity_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "maturity",
        help="Assess project adoption maturity and recommend a next step.",
    )
    sub = parser.add_subparsers(dest="maturity_command", required=True)
    assess = sub.add_parser("assess", help="Score config/KG/memory/harness/benchmark readiness.")
    assess.add_argument("--root", default=".", help="Project root.")
    assess.add_argument("--json", action="store_true", help="JSON output.")
    add_output_flag(assess)


def _dim(name: str, ready: bool, basic: bool, recommendation: str) -> dict[str, Any]:
    level = _READY if ready else (_BASIC if basic else _NONE)
    score = 1.0 if ready else (0.5 if basic else 0.0)
    return {
        "dimension": name,
        "level": level,
        "score": score,
        "recommendation": recommendation if not ready else "",
    }


def _assess(root: Path) -> dict[str, Any]:
    oc = root / ".opencontext"
    config_file = root / "opencontext.yaml"
    kg_db = root / ".storage" / "opencontext" / "context_graph.db"
    sessions = oc / "sessions"
    runs = oc / "runs"
    memory = oc / "memory"
    bench = oc / "benchmarks"

    has_runs = (sessions.is_dir() and any(sessions.glob("*"))) or (
        runs.is_dir() and any(runs.glob("*"))
    )

    dims = [
        _dim(
            "config",
            config_file.exists(),
            oc.is_dir(),
            "Run 'opencontext init' to create opencontext.yaml.",
        ),
        _dim(
            "knowledge_graph",
            kg_db.exists(),
            oc.is_dir(),
            "Run 'opencontext index .' to build the knowledge graph.",
        ),
        _dim(
            "memory",
            memory.exists(),
            oc.is_dir(),
            "Capture memory via the agentic loop or 'opencontext memory' commands.",
        ),
        _dim(
            "harness",
            has_runs,
            oc.is_dir(),
            "Execute a task with 'opencontext run \"<task>\"' to build run history.",
        ),
        _dim(
            "benchmark",
            bench.is_dir() and any(bench.glob("*")),
            False,
            "Run 'opencontext benchmark suites' to baseline quality.",
        ),
    ]

    overall = sum(d["score"] for d in dims) / len(dims)
    level = _READY if overall >= 0.8 else (_BASIC if overall >= 0.4 else _NONE)
    # Highest-value next action = first non-ready dimension's recommendation.
    next_action = next((d["recommendation"] for d in dims if d["level"] != _READY), "")
    return {
        "overall_level": level,
        "overall_score": round(overall, 3),
        "dimensions": dims,
        "next_action": next_action or "Project is fully adopted — keep iterating.",
    }


def handle_maturity(args: Any) -> None:
    import sys

    if getattr(args, "maturity_command", None) != "assess":
        eprint("Usage: opencontext maturity assess")
        sys.exit(2)

    data = _assess(_root(args))

    def _human(d: dict[str, Any]) -> None:
        console.header("Maturity")
        print(f"Maturity: {d['overall_level']} ({d['overall_score']})")
        for dim in d["dimensions"]:
            mark = "x" if dim["level"] == _READY else " "
            print(f"  [{mark}] {dim['dimension']:<16} {dim['level']}")
        print(f"Next: {d['next_action']}")

    emit(data, resolve_output_mode(args), _human)
