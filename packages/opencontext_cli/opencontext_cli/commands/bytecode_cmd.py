"""CLI commands: opencontext bytecode compile|inspect|decode."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from opencontext_cli.output import eprint
from opencontext_core.dx.console_styles import console

if TYPE_CHECKING:
    from opencontext_core.retrieval.contracts import EvidencePlan


def add_bytecode_commands(subparsers: argparse._SubParsersAction[Any]) -> None:
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
    eprint(f"Unknown bytecode subcommand: {cmd}")
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

    saved_path: Path | None = None
    if args.save:
        saved_path = Path(args.save)
        saved_path.parent.mkdir(parents=True, exist_ok=True)
        saved_path.write_text(AICXRenderer().render_json(bc), encoding="utf-8")

    if args.as_json:
        # --json: pure bytecode JSON to stdout, no brand chrome.
        print(AICXRenderer().render_json(bc))
        return 0

    console.header("Bytecode Compile")
    if saved_path is not None:
        console.success(f"Saved: {saved_path}")
    # The rendered AICX text is a literal payload (instruction args may contain
    # markup-like characters) — keep it on raw stdout, unbranded.
    print(AICXRenderer().render_text(bc))
    console.section("Metrics")
    _print_metrics(metrics, report)
    return 0 if report.passed else 1


def _plan_from_runtime(query: str, root: Path, risk: str, budget: int) -> EvidencePlan | None:
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


def _stub_plan(query: str, root: Path, risk: str, budget: int) -> EvidencePlan:
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

    console.header("Bytecode Inspect")
    console.print(f"Version          : {bc.version}")
    console.print(f"Request ID       : {bc.request_id}")
    console.print(
        f"Checksum         : {bc.checksum}  {'✓' if report.checksum_valid else '✗ INVALID'}"
    )
    console.print(f"Valid            : {'yes' if report.passed else 'no'}")
    console.print(f"Instructions     : {metrics.instruction_count}")
    console.print(f"Evidence items   : {metrics.evidence_count}")
    console.print(f"Gates            : {metrics.gate_count}")
    console.print(f"Dictionary keys  : {metrics.dictionary_entries}")
    console.print(f"Original tokens  : {metrics.original_tokens}")
    console.print(f"Bytecode tokens  : {metrics.bytecode_tokens}")
    console.print(f"Token reduction  : {metrics.token_reduction_pct:.1f}%")
    console.print(f"Compression ratio: {metrics.compression_ratio:.1f}x")

    if report.errors:
        console.section("Errors")
        for e in report.errors:
            console.error(e)
    if report.warnings:
        console.section("Warnings")
        for w in report.warnings:
            console.warning(w)

    console.section("Instructions")
    for instr in bc.instructions:
        # Instruction args are literal data (may contain markup chars) — raw print.
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
        # --json: pure plan JSON to stdout, no brand chrome.
        print(plan.model_dump_json(indent=2))
        return 0

    console.header("Bytecode Decode")
    # Decoded fields are literal data (queries/IDs/sources may contain markup
    # characters) — keep them on raw stdout so the payload is not corrupted.
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


def _load_bc(path: str | None) -> Any:
    from opencontext_core.context.bytecode import ContextBytecode

    if path:
        p = Path(path)
        if not p.exists():
            eprint(f"File not found: {p}")
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return ContextBytecode(**_normalize_bc_json(data))
        except Exception as exc:
            eprint(f"Failed to parse bytecode: {exc}")
            return None

    # Try last_bytecode.json (written by `bytecode compile`)
    try:
        from opencontext_core.context.bytecode.session_cache import load_last_bytecode

        bc = load_last_bytecode(".storage/opencontext")
        if bc is not None:
            return bc
    except Exception:
        pass

    # Try latest trace metadata (written by `pack` / MCP calls)
    try:
        from opencontext_core.runtime import OpenContextRuntime

        rt = OpenContextRuntime()
        trace = rt.latest_trace()
        bc_data = trace.metadata.get("aicx", {}).get("bytecode")
        if bc_data:
            return ContextBytecode(**bc_data)
    except Exception:
        pass

    eprint("No AICX bytecode found. Run 'opencontext bytecode compile' first.")
    return None


def _normalize_bc_json(data: dict[str, Any]) -> dict[str, Any]:
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


def _print_metrics(metrics: Any, report: Any) -> None:
    console.print(f"instructions     : {metrics.instruction_count}")
    console.print(f"evidence items   : {metrics.evidence_count}")
    console.print(f"dictionary keys  : {metrics.dictionary_entries}")
    console.print(f"original tokens  : {metrics.original_tokens}")
    console.print(f"bytecode tokens  : {metrics.bytecode_tokens}")
    console.print(f"token reduction  : {metrics.token_reduction_pct:.1f}%")
    status = "✓ valid" if report.passed else f"✗ {'; '.join(report.errors)}"
    console.print(f"checksum         : {status}")
