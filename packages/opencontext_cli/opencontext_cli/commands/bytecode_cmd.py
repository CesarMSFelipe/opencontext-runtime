"""CLI commands: opencontext bytecode compile|inspect|decode."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def add_bytecode_commands(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "bytecode",
        help="AICX context bytecode tools",
        description=(
            "Compile, inspect, and decode AICX context bytecode.\n\n"
            "  opencontext bytecode compile --query 'fix auth bug'\n"
            "  opencontext bytecode inspect .storage/opencontext/aicx/latest.aicx\n"
            "  opencontext bytecode decode .storage/opencontext/aicx/latest.aicx\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="bytecode_command", required=True)

    cp = sub.add_parser("compile", help="Compile a query into AICX bytecode")
    cp.add_argument("--query", "-q", required=True, help="Context query")
    cp.add_argument("--root", default=".", help="Project root (default: .)")
    cp.add_argument("--risk", default="normal", choices=["low", "normal", "high"])
    cp.add_argument("--budget", type=int, default=16000)
    cp.add_argument("--json", dest="as_json", action="store_true", help="Output JSON")
    cp.add_argument("--save", metavar="PATH", help="Save bytecode JSON to file")

    ip = sub.add_parser("inspect", help="Inspect an AICX bytecode file or latest trace")
    ip.add_argument("path", nargs="?", help="Path to .aicx JSON file (omit for latest)")

    dp = sub.add_parser("decode", help="Decode AICX bytecode back to evidence plan")
    dp.add_argument("path", nargs="?", help="Path to .aicx JSON file (omit for latest)")
    dp.add_argument("--json", dest="as_json", action="store_true")


def handle_bytecode(args: argparse.Namespace) -> int:
    cmd = args.bytecode_command
    if cmd == "compile":
        return _compile(args)
    if cmd == "inspect":
        return _inspect(args)
    if cmd == "decode":
        return _decode(args)
    print(f"Unknown bytecode subcommand: {cmd}", file=sys.stderr)
    return 1


# ── compile ────────────────────────────────────────────────────────────────────


def _compile(args: argparse.Namespace) -> int:
    from opencontext_core.context.bytecode import (
        AICXCompiler,
        AICXRenderer,
        AICXValidator,
        compute_metrics,
    )

    root = Path(args.root).resolve()

    # Build a real plan via runtime if index exists, else stub
    plan = _plan_from_runtime(args.query, root, args.risk, args.budget)
    if plan is None:
        plan = _stub_plan(args.query, root, args.risk, args.budget)

    bc = AICXCompiler().compile(plan)
    report = AICXValidator().validate(bc)
    metrics = compute_metrics(plan, bc)

    if args.save:
        save_path = Path(args.save)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(AICXRenderer().render_json(bc), encoding="utf-8")
        print(f"Saved: {save_path}")

    if args.as_json:
        print(AICXRenderer().render_json(bc))
        return 0

    print(AICXRenderer().render_text(bc))
    print()
    _print_metrics(metrics, report)
    return 0 if report.passed else 1


def _plan_from_runtime(query: str, root: Path, risk: str, budget: int) -> object | None:
    try:
        from opencontext_core.retrieval.contracts import EvidenceRequest, RetrievalSurface
        from opencontext_core.retrieval.planner import RetrievalPlanner

        manifest_path = root / ".storage" / "opencontext" / "project_manifest.json"
        if not manifest_path.exists():
            return None

        from opencontext_core.runtime import OpenContextRuntime

        rt = OpenContextRuntime(storage_path=root / ".storage" / "opencontext")
        manifest = rt.load_manifest()
        planner = RetrievalPlanner(
            manifest,
            graph_db_path=root / ".storage" / "opencontext" / "context_graph.db",
        )
        return planner.plan(
            EvidenceRequest(
                query=query,
                root=root,
                surface=RetrievalSurface.CLI,
                max_tokens=budget,
                risk_level=risk,
            ),
            10,
        )
    except Exception:
        return None


def _stub_plan(query: str, root: Path, risk: str, budget: int):
    from opencontext_core.retrieval.contracts import (
        EvidencePlan,
        EvidenceRequest,
        RetrievalSurface,
        TrustDecision,
    )

    request = EvidenceRequest(
        query=query,
        root=root,
        surface=RetrievalSurface.CLI,
        max_tokens=budget,
        risk_level=risk,
    )
    return EvidencePlan(
        request=request,
        evidence=[],
        fallback_actions=["opencontext index ."],
        trust_decision=TrustDecision(
            status="insufficient",
            reason="no index found — run opencontext index .",
        ),
        trace_id="stub",
        omissions=["no_index"],
        source_surfaces=[RetrievalSurface.CLI],
    )


# ── inspect ────────────────────────────────────────────────────────────────────


def _inspect(args: argparse.Namespace) -> int:
    from opencontext_core.context.bytecode import (
        AICXValidator,
        compute_metrics,
    )
    from opencontext_core.context.bytecode.decoder import AICXDecoder

    bc = _load_bc(getattr(args, "path", None))
    if bc is None:
        return 1

    report = AICXValidator().validate(bc)
    decoded = AICXDecoder().decode(bc)
    metrics = compute_metrics(decoded, bc)

    print(f"Version          : {bc.version}")
    print(f"Request ID       : {bc.request_id}")
    print(f"Checksum         : {bc.checksum}  {'✓' if report.checksum_valid else '✗ INVALID'}")
    print(f"Valid            : {'yes' if report.passed else 'no'}")
    print(f"Instructions     : {metrics.instruction_count}")
    print(f"Evidence items   : {metrics.evidence_count}")
    print(f"Gates            : {metrics.gate_count}")
    print(f"Dictionary keys  : {metrics.dictionary_entries}")
    print(f"Original tokens  : {metrics.original_tokens}")
    print(f"Bytecode tokens  : {metrics.bytecode_tokens}")
    print(f"Token reduction  : {metrics.token_reduction_pct:.1f}%")
    print(f"Compression ratio: {metrics.compression_ratio:.1f}x")

    if report.errors:
        print("\nErrors:")
        for e in report.errors:
            print(f"  ✗ {e}")
    if report.warnings:
        print("\nWarnings:")
        for w in report.warnings:
            print(f"  ! {w}")

    print("\nInstructions:")
    for instr in bc.instructions:
        print(f"  {instr.op:<8} {' '.join(instr.args)}")

    return 0 if report.passed else 1


# ── decode ─────────────────────────────────────────────────────────────────────


def _decode(args: argparse.Namespace) -> int:
    from opencontext_core.context.bytecode.decoder import AICXDecoder

    bc = _load_bc(getattr(args, "path", None))
    if bc is None:
        return 1

    plan = AICXDecoder().decode(bc)

    if getattr(args, "as_json", False):
        print(plan.model_dump_json(indent=2))
        return 0

    print(f"Query     : {plan.request.query}")
    print(f"Surface   : {plan.request.surface.value}")
    print(f"Risk      : {plan.request.risk_level}")
    print(f"Budget    : {plan.request.max_tokens}")
    print(f"Trust     : {plan.trust_decision.status} — {plan.trust_decision.reason}")
    print(f"Evidence  : {len(plan.evidence)} items (content lazy — not expanded)")
    for item in plan.evidence:
        print(
            f"  [{item.id[:6]}] {item.source}  conf:{item.confidence:.2f}"
            f"  fresh:{item.freshness.value}"
        )
    if plan.omissions:
        print(f"Omissions : {', '.join(plan.omissions)}")
    if plan.fallback_actions:
        print(f"Fallbacks : {', '.join(plan.fallback_actions)}")
    return 0


# ── helpers ────────────────────────────────────────────────────────────────────


def _load_bc(path: str | None):
    from opencontext_core.context.bytecode import ContextBytecode

    if path:
        p = Path(path)
        if not p.exists():
            print(f"File not found: {p}", file=sys.stderr)
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return ContextBytecode(**_normalize_bc_json(data))
        except Exception as exc:
            print(f"Failed to parse bytecode: {exc}", file=sys.stderr)
            return None

    # Try latest trace metadata
    try:
        from opencontext_core.runtime import OpenContextRuntime

        rt = OpenContextRuntime()
        trace = rt.latest_trace()
        bc_data = trace.metadata.get("aicx", {}).get("bytecode")
        if bc_data:
            return ContextBytecode(**bc_data)
        print("No AICX bytecode in latest trace. Run 'opencontext bytecode compile' first.")
        return None
    except Exception as exc:
        print(f"Could not load latest trace: {exc}", file=sys.stderr)
        return None


def _normalize_bc_json(data: dict) -> dict:
    """Accept both verbose (version/request_id) and compact (v/r) JSON formats."""
    if "v" in data and "version" not in data:
        from opencontext_core.context.bytecode.models import BytecodeInstruction

        instructions = []
        for row in data.get("i", []):
            instructions.append(BytecodeInstruction(op=row[0], args=row[1:]))
        return {
            "version": data["v"],
            "request_id": data.get("r", ""),
            "dictionary": data.get("d", {}),
            "instructions": instructions,
            "checksum": data.get("chk", ""),
        }
    return data


def _print_metrics(metrics, report) -> None:
    print(f"instructions     : {metrics.instruction_count}")
    print(f"evidence items   : {metrics.evidence_count}")
    print(f"dictionary keys  : {metrics.dictionary_entries}")
    print(f"original tokens  : {metrics.original_tokens}")
    print(f"bytecode tokens  : {metrics.bytecode_tokens}")
    print(f"token reduction  : {metrics.token_reduction_pct:.1f}%")
    status = "✓ valid" if report.passed else f"✗ {'; '.join(report.errors)}"
    print(f"checksum         : {status}")
