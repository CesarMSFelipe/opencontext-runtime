"""Concrete SDD phase implementations for the harness runner."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from opencontext_core.workflow.phase_result import PhaseResultEnvelope

from opencontext_core.context.budgeting import estimate_tokens
from opencontext_core.paths import StorageMode, resolve_storage_path, resolve_workspace_path
from opencontext_core.harness.budget import TokenBudgetEnforcer
from opencontext_core.harness.checkpoint import CheckpointStore
from opencontext_core.harness.config import PhaseConfig
from opencontext_core.harness.gates import (
    ArtifactPersistedGate,
    ContextPackCreatedGate,
    ProjectIndexExistsGate,
    TokenBudgetGate,
)
from opencontext_core.harness.models import (
    BudgetMode,
    GateStatus,
    HarnessArtifact,
    HarnessDecision,
    PhaseGate,
    PhaseLedger,
)


@dataclass
class PhaseResult:
    """Result of executing a single harness phase."""

    phase: str
    status: GateStatus
    ledger: PhaseLedger | None = None
    gates: list[PhaseGate] = field(default_factory=list)
    artifacts: list[HarnessArtifact] = field(default_factory=list)
    decisions: list[HarnessDecision] = field(default_factory=list)
    trace_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_envelope(
        self,
        run_id: str,
        change_id: str,
        duration_s: float = 0.0,
    ) -> PhaseResultEnvelope:
        """Produce a canonical ``PhaseResultEnvelope`` from this harness result.

        Maps ``GateStatus`` to the envelope's ``PhaseResultStatus`` so the
        conductor can call ``can_advance()`` without inspecting internal gate lists.
        """
        from opencontext_core.workflow.phase_result import PhaseResultEnvelope

        _gate_to_envelope: dict[GateStatus, str] = {
            GateStatus.PASSED: "passed",
            GateStatus.WARNING: "warning",
            GateStatus.FAILED: "failed",
            GateStatus.SKIPPED: "skipped",
        }
        envelope_status = _gate_to_envelope.get(self.status, "failed")
        artifact_ids = [str(a.path) for a in self.artifacts]
        token_usage: dict[str, int] = {}
        if self.ledger is not None:
            token_usage = {
                "used": self.ledger.used_tokens,
                "budget": self.ledger.budget_tokens,
            }
        return PhaseResultEnvelope(
            run_id=run_id,
            change_id=change_id,
            phase=self.phase,
            status=envelope_status,  # type: ignore[arg-type]
            artifacts=artifact_ids,
            token_usage=token_usage,
            duration_s=duration_s,
        )


# Default per-handoff compaction budget. The forwarded prior-phase artifact is
# context, not the phase's own output, so it is trimmed toward this ceiling rather
# than the (larger) per-phase output budget.
_HANDOFF_TARGET_TOKENS = 4000
# Surgical-first explore budget (P2): the cheap default. Ranked retrieval puts the
# target symbol in the top of this budget, so a tight pack grounds most tasks at a
# fraction of the broad budget's cost (measured: ~21.7k vs ~31.8k tokens end-to-end).
SURGICAL_EXPLORE_BUDGET = 1500


def _surgical_coverage(pack: Any, existing_required: list[str]) -> float:
    """Fraction of the EXISTING required symbols the surgical pack actually covers.

    Per-required-symbol, not the old any-vs-none binary. Falls back to binary when no
    required term is a real symbol in the codebase, so a brand-new parameter name in the
    task (not yet a symbol) never forces a needless widen.
    """
    if not existing_required:
        return 1.0 if getattr(pack, "included", None) else 0.0
    blob = " ".join(
        f"{getattr(i, 'content', '') or ''} {getattr(i, 'source', '') or ''}"
        for i in getattr(pack, "included", [])
    ).lower()
    if not blob.strip():
        return 0.0
    # Whole-word match so a short required name (e.g. "id") can't spuriously match
    # inside a larger word ("width") and inflate coverage.
    hits = sum(1 for s in existing_required if re.search(rf"\b{re.escape(s.lower())}\b", blob))
    return hits / len(existing_required)


def _guardrail_gate(phase: str, content: str, *, strict: bool = False) -> PhaseGate:
    """Surface SDD anti-pattern guardrail hits on a phase's produced content as an
    advisory gate — this makes the guardrail subsystem LIVE in the harness (it was dead
    behind the unused SDDOrchestrator). Advisory (WARNING) so it never breaks a flow;
    promote a 'block'-severity hit to FAILED via config when ready.

    Also detects the ``SCAFFOLD`` marker that
    :func:`run_phase_executor` / :class:`ExecutorOutcome` inject when no real
    model produced the artifact (``# SCAFFOLD —``… or the JSON ``"_scaffold": True``
    on tasks.json). A scaffold passes the superficial pattern checks
    (GIVEN/WHEN/THEN, ### Requirement:) but is a planning placeholder, not a
    completed artifact — so the gate reports a dedicated WARNING that names it as
    such. In ``strict`` mode (``runtime.sdd_strict``) a detected scaffold is
    FAILED instead of WARNING so the phase is BLOCKED and the run does not advance
    (spec PR-004 SDD-CONV: scaffold blocking in strict mode).
    """
    if _is_scaffold_content(content or ""):
        return PhaseGate(
            id="guardrails",
            phase=phase,
            status=GateStatus.FAILED if strict else GateStatus.WARNING,
            message=(
                "Phase produced a SCAFFOLD — no real executor generated this artifact. "
                + (
                    "Strict mode (runtime.sdd_strict) blocks the phase until a real "
                    "executor produces it. "
                    if strict
                    else ""
                )
                + "Wire an executor (state.delegate) or run inside your AI agent "
                "(Claude Code / Codex / OpenCode) so the phase produces a real artifact."
            ),
        )
    try:
        from opencontext_core.agents.sdd_guardrails import evaluate_guardrails

        hits = evaluate_guardrails(phase, content or "")
    except Exception:
        hits = []
    if not hits:
        return PhaseGate(id="guardrails", phase=phase, status=GateStatus.PASSED)
    msg = "; ".join(f"[{h.severity}] {h.name}: {h.counter_argument}" for h in hits)
    return PhaseGate(id="guardrails", phase=phase, status=GateStatus.WARNING, message=msg)


def _phase_contract_gate(phase: str, content: str, *, enabled: bool) -> PhaseGate:
    if not enabled:
        return PhaseGate(id="phase_contract", phase=phase, status=GateStatus.SKIPPED)
    from opencontext_core.sdd.validators import validate_phase

    result = validate_phase(phase, content)
    # WARNING (not FAILED) so individual phase status stays PASSED/WARNING.
    # Hard blocking only happens in sdd_strict mode via the runner's contract_blocked check.
    return PhaseGate(
        id="phase_contract",
        phase=phase,
        status=GateStatus.PASSED if result.passed else GateStatus.WARNING,
        message=result.reason,
    )


def _is_scaffold_content(content: str) -> bool:
    """Detect a static SCAFFOLD template in a phase's produced content.

    ``SpecPhase`` / :class:`DesignPhase` / :class:`TasksPhase` mark their
    template outputs with one of:

    * the markdown marker ``> SCAFFOLD —`` at the top of the file
    * the JSON key ``"_scaffold": True`` (TasksPhase)

    Any of these identify a planning placeholder that is structurally valid but
    not a real AI-produced artifact, and the guardrail gate MUST surface a
    WARNING so downstream consumers know to either wire an executor or treat the
    artifact as "planned, not completed".
    """
    if not content:
        return False
    text = content
    if '_scaffold" : true' in text.lower() or '"_scaffold": true' in text.lower():
        return True
    return "scaffold \u2014" in text.lower() or "scaffold --" in text.lower()


def _render_memory_records(records: Any) -> str:
    """Render recalled memory records as a compact context block (or '' if none).

    Filters out the ``EPISODIC`` layer by default: an episodic row is a per-run
    \"task X completed\" breadcrumb that purely inflates the memory block's token
    usage with no actionable information for the agent. ``FAILURE``,
    ``PROCEDURAL`` and ``SEMANTIC`` rows are kept (actionable signal). The
    ``include_episodic`` flag bypasses the filter for callers that want the raw
    view (e.g. the audit trail).
    """
    lines: list[str] = []
    for r in records or []:
        content = getattr(r, "content", None)
        if content is None and isinstance(r, dict):
            content = r.get("content")
        if not content:
            continue
        layer = getattr(r, "layer", None)
        if layer is None and isinstance(r, dict):
            layer = r.get("layer", "")
        # EPISODIC layer (per-run breadcrumb) is excluded by default; everything
        # else flows through. Keep the filter lenient on stringly-typed layers
        # so legacy records with a free-text ``layer`` field still match.
        layer_key = (str(layer).lower() if layer else "") or ""
        if layer_key in ("episodic", "memory_episodic", "memory:episodic"):
            continue
        lines.append(f"- [{layer or 'memory'}] {content}")
    return "\n".join(lines)


def _compact_artifact(text: str, state: Any, target_tokens: int = _HANDOFF_TARGET_TOKENS) -> str:
    """Compact a forwarded prior-phase artifact toward ``target_tokens`` (B2).

    Routes through ``summarize_to_budget`` (``memory/rehydration.py``): a no-op when
    the text already fits, a model-summarized condense when a gateway is wired, and
    a deterministic line-boundary trim otherwise. The gateway is ``state.delegate``
    per the change brief; ``summarize_to_budget`` already guards the gateway call in
    try/except, so a delegate that is absent (None) — or that cannot summarize —
    degrades safely to the deterministic trim. Never raises.
    """
    from opencontext_core.memory.rehydration import summarize_to_budget

    gateway = getattr(state, "delegate", None)
    return summarize_to_budget(text, target_tokens, gateway)


class HarnessPhase:
    """Base class for a single harness phase."""

    id: str = ""

    def __init__(self, config: PhaseConfig, budget_mode: BudgetMode = BudgetMode.WARN) -> None:
        self.config = config
        self.budget_mode = budget_mode

    def run(self, state: Any) -> PhaseResult:
        """Execute the phase. Override in subclasses."""
        raise NotImplementedError

    def _token_ledger(self, phase: str, used_tokens: int) -> PhaseLedger:
        """Build a PhaseLedger with its status computed by the budget enforcer.

        Phases used to construct PhaseLedger directly, leaving status at its
        default PASSED — so the TokenBudgetGate was a no-op even when a phase blew
        its budget. Route through the enforcer so an over-budget phase actually
        WARNs (or FAILs in strict mode).
        """
        return TokenBudgetEnforcer().evaluate(
            phase=phase,
            used_tokens=used_tokens,
            budget_tokens=self.config.budget_tokens,
            mode=self.budget_mode,
        )


class ExplorePhase(HarnessPhase):
    """Explore phase: index project, build context pack, evaluate gates."""

    id = "explore"

    def __init__(
        self,
        config: PhaseConfig,
        budget_mode: BudgetMode = BudgetMode.WARN,
        memory_store: Any = None,
    ) -> None:
        super().__init__(config, budget_mode)
        self._memory_store = memory_store

    def run(self, state: Any) -> PhaseResult:
        from opencontext_core.runtime import OpenContextRuntime

        runtime = OpenContextRuntime(
            config_path=state.root / "opencontext.yaml"
            if (state.root / "opencontext.yaml").exists()
            else None,
            storage_path=resolve_storage_path(state.root, StorageMode.local),
        )
        manifest = runtime.index_project(state.root)

        # Build the context contract early so its required_symbols can gate surgical
        # coverage PER-SYMBOL (not the old any-vs-none binary). Reused below for the
        # contract.yaml artifact, so it is built once.
        contract = None
        required_symbols: list[str] = []
        try:
            from opencontext_core.context.planning.classifier import TaskClassifier
            from opencontext_core.context.planning.contract import ContextContractBuilder
            from opencontext_core.context.planning.risk import RiskClassifier

            contract = ContextContractBuilder(
                classifier=TaskClassifier(), risk_classifier=RiskClassifier()
            ).build(state.task)
            required_symbols = list(getattr(contract, "required_symbols", []) or [])
        except Exception:
            contract = None
        symbol_names = {(getattr(s, "name", "") or "").lower() for s in manifest.symbols}
        # required_symbols come glob-wrapped from _extract_key_terms ("*login*"); strip
        # the asterisks before testing membership against the bare symbol names, else
        # existing_required is always empty and coverage silently falls back to binary.
        existing_required = [
            s.strip("*") for s in required_symbols if s.strip("*").lower() in symbol_names
        ]

        # Surgical-first explore (P2): retrieve a tight, cheap pack by default and widen
        # to the full budget only when it fails to cover the required EXISTING symbols.
        full_budget = state.max_tokens or self.config.budget_tokens
        # surgical_explore / surgical_coverage_floor are real PhaseConfig
        # attributes (forwarded from workflow_defaults via from_yaml_file).
        # ``None`` falls back to ``True`` (zero-config default) for surgical
        # and ``0.8`` (the documented floor) for coverage, replacing the silent
        # getattr-returns-True / 1.0 defaults.
        surgical_flag = (
            self.config.surgical_explore if self.config.surgical_explore is not None else True
        )
        surgical_floor = (
            self.config.surgical_coverage_floor
            if self.config.surgical_coverage_floor is not None
            else 0.8
        )
        surgical = surgical_flag and full_budget > SURGICAL_EXPLORE_BUDGET
        explore_arm = "OC-SURGICAL"
        explore_expanded = False
        if surgical:
            pack, pack_trace_id = runtime.build_context_pack_with_trace(
                state.task, SURGICAL_EXPLORE_BUDGET
            )
            coverage = _surgical_coverage(pack, existing_required)
            if coverage < surgical_floor:
                pack, pack_trace_id = runtime.build_context_pack_with_trace(state.task, full_budget)
                explore_arm = "OC-BROAD"
                explore_expanded = True
        else:
            pack, pack_trace_id = runtime.build_context_pack_with_trace(state.task, full_budget)

        # Persist context pack to run directory
        run_dir = resolve_workspace_path(state.root, StorageMode.local) / "runs" / state.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        pack_path = run_dir / "context-pack.json"
        pack_path.write_text(pack.model_dump_json(indent=2), encoding="utf-8")

        # Recall prior memory for this task and FOLD it into the context (the search
        # result used to be discarded — the one memory read in the flow did nothing).
        memory_block = ""
        if getattr(self, "_memory_store", None) is not None:
            try:
                memory_block = _render_memory_records(
                    self._memory_store.search(state.task, limit=5)
                )
            except Exception:
                memory_block = ""  # memory is optional, never block explore

        # Make the verified context available to later work phases' executor prompts
        # (spec/design/tasks) so the model works from retrieved evidence, not the bare
        # task. Prior-memory block (failures/decisions) goes first when present.
        rendered = "\n\n".join(f"### {item.source}\n{item.content}" for item in pack.included)
        state.context_pack = (
            f"### prior memory (failures/decisions from past runs)\n{memory_block}\n\n{rendered}"
            if memory_block
            else rendered
        )
        # Hard cap the RENDERED context (pack widen + memory block) so the string that
        # actually reaches the downstream prompt can never blow the model's input
        # budget. The pack is budgeted as data; this guards the rendered text too.
        cap_tokens = max(full_budget, SURGICAL_EXPLORE_BUDGET) * 2
        if estimate_tokens(state.context_pack) > cap_tokens:
            state.context_pack = _compact_artifact(
                state.context_pack, state, target_tokens=cap_tokens
            )

        # KG wiring: run impact analysis if task is provided
        impact_affected_files: list[str] = []
        impact_affected_tests: list[str] = []
        kg_available: bool = False
        kg_error: str | None = None
        try:
            from opencontext_core.indexing.impact_analysis import ImpactAnalyzer

            db_path = resolve_storage_path(state.root, StorageMode.local) / "context_graph.db"
            if db_path.exists():
                from opencontext_core.indexing.graph_db import GraphDatabase

                db = GraphDatabase(db_path)
                try:
                    analyzer = ImpactAnalyzer(db)
                    kg_available = True
                    # Impact keys on a SYMBOL name, not a free-text sentence — feed it the
                    # contract's existing required symbols (asterisk-stripped above), not
                    # the raw task string, which matches no node and left impact (and the
                    # required-sources gate) silently empty for every normal task.
                    impact_targets = existing_required or [state.task]
                    for target in impact_targets:
                        for ir in analyzer.analyze_by_name(target, depth=2):
                            impact_affected_files.extend(ir.affected_files)
                            impact_affected_tests.extend(ir.affected_tests)
                finally:
                    # Always close — a present-but-broken graph raises in analyze_by_name
                    # and would otherwise leak the sqlite/WAL handles.
                    db.close()
            else:
                kg_error = "context_graph.db not found — run `opencontext index` first"
        except Exception as exc:
            kg_error = str(exc)
            # KG wiring is best-effort — don't fail the phase if KG is unavailable

        # Architecture-health BASELINE capture (zero-config quality sensor). This
        # is the ONLY snapshot point; the verify-phase architecture_clean gate
        # diffs the post-apply graph against it. Architecture-only + token-free
        # (no language subprocesses, no model). Best-effort: any failure leaves
        # the baseline None, which makes the verify gate SKIPPED — never a false
        # "clean".
        try:
            from opencontext_core.quality.evaluator import QualityEvaluator

            baseline = QualityEvaluator(state.root).snapshot()
            state.architecture_baseline = baseline
            state.architecture_baseline_dict = baseline.metrics.as_dict() | {
                "score": baseline.score
            }
        except Exception:
            pass

        gates: list[PhaseGate] = [
            ProjectIndexExistsGate().evaluate(state.root),
            ContextPackCreatedGate().evaluate(len(pack.included)),
        ]
        ledger = self._token_ledger("explore", pack.used_tokens)
        gates.append(TokenBudgetGate().evaluate(ledger))

        status = (
            GateStatus.FAILED
            if any(g.status == GateStatus.FAILED for g in gates)
            else (
                GateStatus.WARNING
                if any(g.status == GateStatus.WARNING for g in gates)
                else GateStatus.PASSED
            )
        )

        # (memory recall folded into state.context_pack above — no longer discarded)

        # Context contract artifact (built once, above)
        explore_artifacts: list[HarnessArtifact] = [
            HarnessArtifact(
                id=f"explore-pack-{state.run_id[:8]}",
                phase="explore",
                path=str(resolve_workspace_path(state.root, StorageMode.local) / "runs" / state.run_id / "context-pack.json"),
                kind="context-pack",
                description=f"Context pack with {len(pack.included)} items",
            )
        ]
        if contract is not None:
            try:
                contract_path = run_dir / "contract.yaml"
                contract_path.write_text(contract.to_yaml())
                explore_artifacts.append(
                    HarnessArtifact(
                        id=f"contract-{state.run_id}",
                        phase="explore",
                        path=str(contract_path),
                        kind="context-contract",
                        description="Verified context contract",
                    )
                )
            except Exception:
                pass  # contract persistence is additive, never block explore

        # Record context provenance for the propose phase's provenance gates.
        state.context_sources = {item.source for item in pack.included}
        state.context_required_sources = list(dict.fromkeys(impact_affected_files))
        state.context_omitted = len(pack.omitted)
        state.context_omissions_recorded = len(pack.omissions)
        # problem 5: surface the contract's risk tier + resolved required symbols
        # on state so ProposePhase can build a proposal.json that reflects
        # ExplorePhase's actual analysis (was previously a static placeholder
        # containing only ``method: incremental`` regardless of the task).
        state.contract_risk_tier = getattr(
            getattr(contract, "risk_tier", None), "value", None
        ) or getattr(contract, "risk_tier", None)
        state.contract_required_symbols = list(existing_required)
        state.impact_affected_tests = list(dict.fromkeys(impact_affected_tests))

        # Pass-1 surgical budget / widen budget persisted into state so the
        # archive / run.json can report exactly what the explore chose. Used by
        # :meth:`HarnessRunner.persist_run` to surface ``explore_arm`` /
        # ``surgical_tokens`` / ``broad_tokens`` in run.json for audit.
        state.explore_arm = explore_arm
        state.explore_expanded = explore_expanded
        state.explore_surgical_tokens = SURGICAL_EXPLORE_BUDGET if surgical else 0
        state.explore_broad_tokens = full_budget if explore_expanded else 0
        state.explore_kg_available = kg_available

        # Omitted sources (path[:line]) the explore pruned — used downstream by
        # MemoryHarvester to populate ``FAILURE:missing_context`` linked_nodes
        # instead of relying on a never-populated ``metadata.missing_context``
        # attribute on the explore artifact (which the harvester currently reads
        # and finds empty).
        state.context_omitted_paths = [
            f"{getattr(item, 'source', '')}:0"
            for item in getattr(pack, "omitted", []) or []
            if getattr(item, "source", "")
        ]

        return PhaseResult(
            phase="explore",
            status=status,
            ledger=ledger,
            gates=gates,
            artifacts=explore_artifacts,
            trace_id=pack_trace_id,
            metadata={
                "included": len(pack.included),
                "omitted": len(pack.omitted),
                # Path-list the memory harvester can read to populate
                # ``FAILURE:missing_context`` linked_nodes (was previously
                # empty because ``_extract_missing_context`` only looked at
                # ``metadata["missing_context"]`` on artifacts — never set).
                "missing_context": list(state.context_omitted_paths),
                "indexed_files": len(manifest.files),
                "indexed_symbols": len(manifest.symbols),
                "impact_affected_files": impact_affected_files,
                "impact_affected_tests": impact_affected_tests,
                "kg_available": kg_available,
                "kg_error": kg_error,
                "arm": explore_arm,
                "expanded": explore_expanded,
                # Transparency: is the semantic (embedding) retrieval layer active, or is
                # retrieval KG/lexical-only? Off by default on a fresh repo.
                "semantic_layer": bool(
                    getattr(getattr(runtime.config, "embedding", None), "enabled", False)
                ),
                "risk_tier": getattr(getattr(contract, "risk_tier", None), "value", None)
                or getattr(contract, "risk_tier", None),
            },
        )


class ArchivePhase(HarnessPhase):
    """Archive phase: produce all run artifacts and the archive report.

    Produces memory_delta.json (summary of project memory changes) and
    graph_delta.json (summary of knowledge graph changes) by extracting
    relevant data from the run's artifact collection. Then produces a
    structured archive-report.json summary.
    """

    id = "archive"

    def __init__(
        self,
        config: PhaseConfig,
        budget_mode: BudgetMode = BudgetMode.WARN,
        memory_store: Any = None,
        memory_v2: bool = False,
    ) -> None:
        super().__init__(config, budget_mode)
        self._memory_store = memory_store
        # PR-009: when True, harvested writes route through the MemoryHarness.
        self._memory_v2 = memory_v2

    def run(self, state: Any) -> PhaseResult:
        run_dir = resolve_workspace_path(state.root, StorageMode.local) / "runs" / state.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # run.json is finalized by the runner's persist_run() AFTER all phases,
        # so it does not exist yet at archive time. Write a preliminary copy here
        # so the phase is self-contained and its persistence gate is meaningful;
        # persist_run() overwrites it with the final status afterward.
        run_json_path = run_dir / "run.json"
        if not run_json_path.exists():
            run_json_path.write_text(
                json.dumps(
                    {
                        "run_id": state.run_id,
                        "task": state.task,
                        "status": "archiving",
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

        # Produce memory_delta.json
        memory_delta = self._build_memory_delta(state)
        memory_delta_path = run_dir / "memory_delta.json"
        memory_delta_path.write_text(json.dumps(memory_delta, indent=2), encoding="utf-8")

        # Produce graph_delta.json
        graph_delta = self._build_graph_delta(state)
        graph_delta_path = run_dir / "graph_delta.json"
        graph_delta_path.write_text(json.dumps(graph_delta, indent=2), encoding="utf-8")

        # Gate checks — all three core artifacts must now exist
        artifacts_to_check = [
            ("run.json", "run"),
            ("memory_delta.json", "memory_delta"),
            ("graph_delta.json", "graph_delta"),
        ]
        gates: list[PhaseGate] = []
        missing: list[str] = []
        for filename, _kind in artifacts_to_check:
            path = run_dir / filename
            gate = ArtifactPersistedGate().evaluate(path)
            gates.append(gate)
            if gate.status != GateStatus.PASSED:
                missing.append(filename)

        # Produce the archive report
        archive_report = {
            "run_id": state.run_id,
            "task": state.task,
            "created_at": datetime.now(UTC).isoformat(),
            "status": "archived",
            "phases_completed": len(state.ledgers),
            "total_artifacts": len(state.artifacts),
            "total_gates": len(state.gates),
            "passed_gates": sum(1 for g in state.gates if g.status == GateStatus.PASSED),
            "failed_gates": sum(1 for g in state.gates if g.status == GateStatus.FAILED),
            "warnings": state.warnings,
            "artifacts": [
                {
                    "id": a.id,
                    "phase": a.phase,
                    "kind": a.kind,
                    "path": a.path,
                }
                for a in state.artifacts
            ],
            "missing_artifacts": missing,
            "summary": (
                f"Archived run {state.run_id}: "
                f"{len(state.artifacts)} artifacts, "
                f"{sum(1 for g in state.gates if g.status == GateStatus.PASSED)}/"
                f"{len(state.gates)} gates passed."
                if not missing
                else f"Archive incomplete — missing: {', '.join(missing)}"
            ),
        }
        report_path = run_dir / "archive-report.json"
        report_path.write_text(json.dumps(archive_report, indent=2), encoding="utf-8")

        ledger = PhaseLedger(
            phase="archive",
            used_tokens=0,
            budget_tokens=self.config.budget_tokens,
            budget_mode=self.budget_mode,
        )
        status = (
            GateStatus.FAILED
            if any(g.status == GateStatus.FAILED for g in gates)
            else GateStatus.PASSED
        )

        # Memory harvest (additive, non-breaking)
        if hasattr(self, "_memory_store") and self._memory_store is not None:
            try:
                from opencontext_core.harness.models import HarnessRunResult
                from opencontext_core.memory.harvester import MemoryHarvester

                run_result = HarnessRunResult(
                    run_id=state.run_id,
                    workflow=getattr(state, "workflow", "unknown"),
                    task=state.task,
                    status=status,
                    ledgers=state.ledgers,
                    gates=state.gates,
                    artifacts=state.artifacts,
                    decisions=state.decisions,
                    trace_ids=state.trace_ids,
                    warnings=state.warnings,
                    context_omitted_paths=list(getattr(state, "context_omitted_paths", []) or []),
                )
                harness = None
                if getattr(self, "_memory_v2", False):
                    from opencontext_core.memory.harness import MemoryHarness

                    harness = MemoryHarness(self._memory_store)
                harvester = MemoryHarvester(self._memory_store, harness=harness)
                harvester.harvest(run_result)
            except Exception:
                pass  # harvesting is optional, never block archive

        return PhaseResult(
            phase="archive",
            status=status,
            ledger=ledger,
            gates=gates,
            artifacts=[
                HarnessArtifact(
                    id=f"archive-{state.run_id[:8]}",
                    phase="archive",
                    path=str(report_path),
                    kind="archive-report",
                    description=f"Archive report for run {state.run_id}",
                )
            ],
            metadata={
                "missing_artifacts": missing,
                "total_artifacts": len(state.artifacts),
            },
        )

    def _build_memory_delta(self, state: Any) -> dict[str, Any]:
        """Build the memory_delta artifact from run state.

        Summarises project memory changes observed during this run:
        - New or updated files (from explore phase artifacts)
        - New symbols discovered
        - Decisions made
        - Trace IDs collected
        """
        delta = {
            "run_id": state.run_id,
            "task": state.task,
            "created_at": datetime.now(UTC).isoformat(),
            "changed_files": [],
            "decisions": [
                {"id": d.id, "reason": d.reason, "phase": d.phase} for d in state.decisions
            ],
            "trace_ids": list(state.trace_ids),
            "summary": "",
        }

        # Extract file changes from explore/propose artifacts
        for artifact in state.artifacts:
            if artifact.kind in ("context-pack", "proposal", "spec", "design", "tasks"):
                path = Path(artifact.path)
                if path.exists() and path.suffix == ".json":
                    try:
                        data = json.loads(path.read_text(encoding="utf-8"))
                        if "changed_files" in data:
                            delta["changed_files"].extend(data["changed_files"])
                        if "files" in data and isinstance(data["files"], list):
                            for f in data["files"][:50]:
                                if isinstance(f, dict) and f.get("path"):
                                    delta["changed_files"].append(f["path"])
                    except Exception:
                        pass

        delta["changed_files"] = list(set(delta["changed_files"]))[:100]
        delta["summary"] = (
            f"{len(delta['changed_files'])} files considered, "
            f"{len(delta['decisions'])} decisions, "
            f"{len(state.trace_ids)} trace(s)."
        )
        return delta

    def _build_graph_delta(self, state: Any) -> dict[str, Any]:
        """Build the graph_delta artifact from run state.

        Summarises knowledge graph changes observed during this run:
        - Symbols referenced or created
        - Call relationships discovered
        - Phase-level KG activity flags
        """
        delta = {
            "run_id": state.run_id,
            "task": state.task,
            "created_at": datetime.now(UTC).isoformat(),
            "symbols": [],
            "phases_with_kg_activity": [],
            "summary": "",
        }

        # Extract symbol references from artifacts
        for artifact in state.artifacts:
            path = Path(artifact.path)
            if path.exists() and path.suffix == ".json":
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if "symbols" in data:
                        delta["symbols"].extend(data["symbols"])
                    if artifact.phase not in delta["phases_with_kg_activity"]:
                        delta["phases_with_kg_activity"].append(artifact.phase)
                except Exception:
                    pass

        # Deduplicate symbols
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for s in delta["symbols"]:
            key = s.get("name", "") or s.get("id", "")
            if key and key not in seen:
                seen.add(key)
                unique.append(s)
        delta["symbols"] = unique[:200]

        delta["summary"] = (
            f"{len(delta['symbols'])} symbols, "
            f"{len(delta['phases_with_kg_activity'])} phase(s) with KG activity."
        )
        return delta


class ProposePhase(HarnessPhase):
    """Propose phase: create a structured SDD change proposal from exploration."""

    id = "propose"

    def run(self, state: Any) -> PhaseResult:
        run_dir = resolve_workspace_path(state.root, StorageMode.local) / "runs" / state.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        proposal_path = run_dir / "proposal.json"

        # Delegate to the wired executor for a REAL proposal narrative; fall back to the
        # structured scaffold when no model is wired (mirrors spec/design/tasks — honest,
        # never a fabricated "success"). Keeps the JSON contract spec reads downstream.
        outcome = run_phase_executor(state, "propose")
        real = outcome.is_real
        narrative = (outcome.output or "").strip() if real else ""
        used = estimate_tokens(outcome.output or "") if real else 0

        # problem 5: read ExplorePhase's actual analysis (impact + contract + risk
        # tier) so proposal.json carries forward what explore found, not a static
        # ``method: incremental`` placeholder. Each field tolerates a missing
        # state attribute (older harness callers don't set them) by falling back
        # to ``[]``/``None`` so ProposePhase never breaks on a stale state.
        impacted_files = list(getattr(state, "context_required_sources", []) or [])
        required_symbols = list(getattr(state, "contract_required_symbols", []) or [])
        impacted_tests = list(getattr(state, "impact_affected_tests", []) or [])
        contract_risk = getattr(state, "contract_risk_tier", None)
        # Build a structured "scope" that the spec phase reads (was previously an
        # empty {"root": ..., "max_tokens": ...} — SpecPhase had no authored evidence).
        scope = {
            "root": str(state.root),
            "max_tokens": state.max_tokens,
            "affected_files": impacted_files,
            "affected_tests": impacted_tests,
            "required_symbols": required_symbols,
            "risk_tier": contract_risk,
            "explore_arm": getattr(state, "explore_arm", None),
            "explore_expanded": getattr(state, "explore_expanded", None),
        }
        # Build an honest "evidence" pointer the spec/design phases mirror, so
        # nothing downstream has to fall back to the bare task text.
        evidence = {
            "explore_pack": str(
                resolve_workspace_path(state.root, StorageMode.local) / "runs" / state.run_id / "context-pack.json"
            ),
            "contract_path": str(
                resolve_workspace_path(state.root, StorageMode.local) / "runs" / state.run_id / "contract.yaml"
            ),
            "affected_files": impacted_files,
            "affected_tests": impacted_tests,
            "required_symbols": required_symbols,
            "risk_tier": contract_risk,
            "kg_available": getattr(state, "explore_kg_available", None),
        }

        proposal = {
            "run_id": state.run_id,
            "task": state.task,
            "created_at": datetime.now(UTC).isoformat(),
            "status": "drafted" if real else "planned",
            "summary": narrative or f"SDD proposal: {state.task}",
            "scope": scope,
            "evidence": evidence,
            "approach": {
                "method": "delegated" if real else "incremental",
                "style": "provider-neutral",
                "rationale": narrative,
                "risk_tier": contract_risk,
            },
            "affected_files": impacted_files,
            "affected_tests": impacted_tests,
            "required_symbols": required_symbols,
            "risk_tier": contract_risk,
            "artifacts": [
                {
                    "id": f"proposal-{state.run_id[:8]}",
                    "kind": "proposal",
                    "phase": "propose",
                }
            ],
        }
        # Honesty parity with SpecPhase/DesignPhase/TasksPhase (spec PR-004 REQ-08):
        # when no real executor produced the proposal, mark it as a scaffold so the
        # guardrail gate surfaces it as a non-PASS (and FAILs it in strict mode) and
        # append the "no model bound" warning. Without this, a static proposal was
        # reported as a PASSED success — the one honesty gap among the work phases.
        if not real:
            proposal["_scaffold"] = True
            if getattr(state, "delegate", None) is None:
                state.warnings.append(
                    "Phase 'ProposePhase': no model bound — emitted a structured plan for "
                    "your agent's model to complete. Run OpenContext inside your AI agent "
                    "(Claude Code, Codex, OpenCode, …) to use its selected model, or set a "
                    "provider for standalone generation."
                )
        proposal_path.write_text(json.dumps(proposal, indent=2), encoding="utf-8")

        strict = bool(getattr(state, "sdd_strict", False))
        gates: list[PhaseGate] = [
            ArtifactPersistedGate().evaluate(proposal_path),
            _guardrail_gate("propose", json.dumps(proposal), strict=strict),
        ]

        ledger = self._token_ledger("propose", used)
        gates.append(TokenBudgetGate().evaluate(ledger))

        manifest_path = _write_phase_manifest(
            run_dir, "propose", proposal_path, state.task, outcome
        )

        status = (
            GateStatus.FAILED
            if any(g.status == GateStatus.FAILED for g in gates)
            else outcome.gate_status
        )

        return PhaseResult(
            phase="propose",
            status=status,
            ledger=ledger,
            gates=gates,
            artifacts=[
                HarnessArtifact(
                    id=f"proposal-{state.run_id[:8]}",
                    phase="propose",
                    path=str(proposal_path),
                    kind="proposal",
                    description=f"SDD proposal: {state.task}",
                )
            ],
            metadata={
                "proposal_path": str(proposal_path),
                "manifest_path": str(manifest_path),
                "executor": outcome.executor,
            },
        )


@dataclass
class ExecutorOutcome:
    """Result of attempting to run a real executor for a work-producing phase.

    Mirrors the honest-ApplyPhase contract for the planning phases (spec/design/
    tasks): a phase MUST NOT present a static template scaffold as a successful
    AI-produced artifact.

    Attributes:
        executor: ``"real"`` when a registered executor produced the output,
            ``"absent"`` when no executor/LLM was wired, ``"error"`` when an
            executor was wired but failed.
        output: The executor's produced content (only meaningful when
            ``executor == "real"``); ``None`` otherwise so the caller falls back
            to its scaffold.
        error: The executor error message when ``executor == "error"``.
    """

    executor: str
    output: str | None = None
    error: str | None = None

    @property
    def is_real(self) -> bool:
        return self.executor == "real" and self.output is not None

    @property
    def artifact_status(self) -> str:
        """Domain status for the phase artifact/manifest.

        ``"completed"`` only when a real executor produced the artifact; never
        over a static scaffold or a failed executor.
        """
        return "completed" if self.is_real else "planned"

    @property
    def gate_status(self) -> GateStatus:
        """PhaseResult status: PASSED only on a real executor success.

        When the executor is absent or errored the phase reports WARNING — a
        non-PASSED status that honestly signals "no real artifact produced"
        without hard-failing the run (which is reserved for budget/gate
        violations and blocked writes).
        """
        return GateStatus.PASSED if self.is_real else GateStatus.WARNING


# Lazily-built, process-wide cache of the builtin skill registry. Building it
# scans the on-disk builtin skills dir once; resolution per phase is cheap.
_BUILTIN_SKILL_REGISTRY: list[Any] | None = None
_BUILTIN_SKILL_REGISTRY_BUILT = False


def _builtin_skill_registry() -> list[Any]:
    """Return the builtin skill registry, building it once (best-effort).

    Never raises: any failure to scan/parse the builtin skills dir yields an
    empty registry so the executor wiring degrades to today's behaviour (no
    injected skill rules) rather than breaking the phase.
    """
    global _BUILTIN_SKILL_REGISTRY, _BUILTIN_SKILL_REGISTRY_BUILT
    if _BUILTIN_SKILL_REGISTRY_BUILT:
        return _BUILTIN_SKILL_REGISTRY or []
    registry: list[Any] = []
    try:
        from opencontext_core.skills import registry as _skill_registry

        builtin_dir = Path(_skill_registry.__file__).parent / "builtin"
        registry = _skill_registry.build_registry(user_dirs=[str(builtin_dir)], project_dirs=[])
    except Exception:
        registry = []
    _BUILTIN_SKILL_REGISTRY = registry
    _BUILTIN_SKILL_REGISTRY_BUILT = True
    return registry


def _phase_skill_rules(phase: str, max_skills: int = 2) -> str:
    """Resolve up to ``max_skills`` builtin skills for ``phase`` and render their
    COMPACT rules as a small markdown section, or ``""`` when none match.

    Best-effort and token-frugal: matches on the phase name as the task type
    (empty file patterns), caps rules per skill, and never raises.
    """
    try:
        registry = _builtin_skill_registry()
        if not registry:
            return ""
        from opencontext_core.skills.compact_rules import generate_compact_rules
        from opencontext_core.skills.resolver import resolve_skills

        matched = resolve_skills(
            registry, file_patterns=[], task_type=phase, max_matches=max_skills
        )
        if not matched:
            return ""
        rules = generate_compact_rules(matched, max_per_skill=6).strip()
        if not rules:
            return ""
        return f"## Applicable skills\n{rules}"
    except Exception:
        return ""


# Metrics surfaced (in this fixed order) in the Architect@design health block.
# Each is a key in ``state.architecture_baseline_dict`` (``QualityMetrics.as_dict``).
# Order is deterministic — duplication/max_nesting (the Phase-3 depth+redundancy
# signals) lead so the design persona sees them first.
_DESIGN_HEALTH_METRICS: tuple[str, ...] = (
    "duplication",
    "max_nesting",
    "cycles",
    "god_files",
    "max_cc",
)


def _render_health_for_design(snapshot: dict[str, Any]) -> str:
    """Format the explore architecture-health snapshot for the design persona.

    ``snapshot`` is ``state.architecture_baseline_dict`` — the JSON-safe mirror
    ``ExplorePhase`` writes (``metrics.as_dict() | {'score': ...}``), so it
    already carries the Phase-3 ``duplication`` / ``max_nesting`` signals. This is
    PURE string formatting: deterministic, fixed key order, ZERO model calls and
    ZERO subprocess. An empty/falsy snapshot yields ``""`` (nothing to surface).
    """
    if not snapshot:
        return ""
    score = int(snapshot.get("score", 0))
    parts = ", ".join(f"{name} {int(snapshot.get(name, 0))}" for name in _DESIGN_HEALTH_METRICS)
    return (
        "## Architecture health\n"
        f"architecture health: {score} — {parts}\n"
        "Account for these signals in the design: avoid adding duplication, deep "
        "nesting, cycles, or god-files; prefer flattening and extracting shared logic."
    )


def _render_program_plan(plan: Any) -> str:
    """Render a compact PR-000 ``ProgramPlan`` block for a phase's executor context.

    Meta-plan awareness (spec PR-004 SDD-CONV): when a ``ProgramPlan`` is present
    the SDD flow seeds phase scope from it (the program intent + the slices this
    change covers) while the canonical phase order is preserved by the scheduler.
    Pure, defensive string formatting — never raises; returns ``""`` when absent.
    """
    if plan is None:
        return ""
    try:
        intent = getattr(plan, "intent", None)
        summary = ""
        if intent is not None:
            summary = (
                getattr(intent, "summary", "")
                or getattr(intent, "title", "")
                or getattr(intent, "raw_text", "")
            )
        slices = getattr(plan, "slices", []) or []
        slice_titles = [
            str(getattr(s, "title", None) or getattr(s, "slice_id", "")) for s in slices
        ]
        lines = ["## Program plan (meta-plan)"]
        if summary:
            lines.append(f"This change is part of program intent: {summary}")
        if slice_titles:
            lines.append("Program slices: " + ", ".join(t for t in slice_titles if t))
        if len(lines) == 1:
            return ""
        return "\n".join(lines)
    except Exception:
        return ""


def run_phase_executor(state: Any, phase: str) -> ExecutorOutcome:
    """Invoke the wired executor for a work-producing phase, honestly.

    Looks for a delegation layer on the run ``state`` (``state.delegate`` — a
    :class:`opencontext_core.agents.delegation.SubAgentDelegate`-shaped object
    exposing ``delegate(phase, context) -> SubAgentResult``). This mirrors how
    :class:`ApplyPhase` reads ``state.apply_edits``: the executor/delegation
    layer is supplied on the state, never fabricated by the phase.

    Returns an :class:`ExecutorOutcome` describing whether a real executor ran.
    The phase uses the outcome to decide between reporting a real, completed
    artifact and an honest ``planned`` scaffold — it NEVER labels a static
    template as a successful AI-produced artifact.
    """
    delegate = getattr(state, "delegate", None)
    if delegate is None or not callable(getattr(delegate, "delegate", None)):
        return ExecutorOutcome(executor="absent")

    prior = getattr(state, "prior_artifact", "") or ""
    pack = getattr(state, "context_pack", "") or ""
    # The prior phase's artifact (compacted spec for design, design for tasks) FIRST,
    # then the explore context pack. Previously only the explore pack was passed, so
    # design never saw the spec and tasks never saw the design — the handoff was dead.
    base_context = f"{prior}\n\n{pack}" if prior else pack
    # Differentiate the phase by its resolved builtin skills, not only its persona:
    # append a small, compact "## Applicable skills" section in addition to (never
    # replacing) the prior artifact + pack. Empty when no skill matches the phase.
    skill_rules = _phase_skill_rules(phase)
    if skill_rules:
        base_context = f"{base_context}\n\n{skill_rules}" if base_context else skill_rules
    # Meta-plan awareness: when a PR-000 ProgramPlan is attached to the run state,
    # seed phase scope from it (prepended so it frames the rest of the context).
    plan_block = _render_program_plan(getattr(state, "program_plan", None))
    if plan_block:
        base_context = f"{plan_block}\n\n{base_context}" if base_context else plan_block
    # Architect@design surfacing (Phase-3, seam 4): the design persona sees the
    # current architecture-health snapshot (captured at explore) so design
    # decisions are grounded in real duplication/nesting/cycle/god-file signals.
    # Additive — mirrors the skill_rules append; only for the design phase.
    if phase == "design":
        snapshot = getattr(state, "architecture_baseline_dict", None) or {}
        if snapshot:
            health_block = _render_health_for_design(snapshot)
            if health_block:
                base_context = f"{base_context}\n\n{health_block}" if base_context else health_block
    context = {
        "task": getattr(state, "task", ""),
        "phase": phase,
        "run_id": getattr(state, "run_id", ""),
        "root": str(getattr(state, "root", "")),
        "context": base_context,
    }
    try:
        result = delegate.delegate(phase, context)
    except Exception as exc:  # delegation layer raised — report, do not fake
        return ExecutorOutcome(executor="error", error=str(exc))

    status = getattr(result, "status", "error")
    output = getattr(result, "output", "") or ""
    if status == "success" and output.strip():
        return ExecutorOutcome(executor="real", output=output)
    # Executor was wired but did not produce usable output.
    return ExecutorOutcome(
        executor="error",
        error=getattr(result, "error", None) or f"executor returned status={status!r}",
    )


def _write_phase_manifest(
    run_dir: Path,
    phase: str,
    artifact_path: Path,
    task: str,
    outcome: ExecutorOutcome,
) -> Path:
    """Persist an honest manifest side-car for a work-producing phase.

    Records the artifact ``status`` (``"completed"`` only when a real executor
    ran, otherwise ``"planned"``) and which executor produced it, so the
    distinction between a real artifact and a static scaffold is inspectable
    on disk. Returns the manifest path.
    """
    manifest = {
        "run_id": run_dir.name,
        "task": task,
        "created_at": datetime.now(UTC).isoformat(),
        "phase": phase,
        "status": outcome.artifact_status,
        "executor": outcome.executor,
        "artifact_path": str(artifact_path),
        "summary": (
            f"{phase} produced by real executor for: {task}"
            if outcome.is_real
            else (
                f"{phase} executor errored — scaffold only for: {task}"
                if outcome.executor == "error"
                else f"No executor — {phase} scaffold (planned) only for: {task}"
            )
        ),
    }
    if outcome.error is not None:
        manifest["error"] = outcome.error
    manifest_path = run_dir / f"{phase}-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


def _path_is_forbidden(rel_posix: str, patterns: list[str]) -> bool:
    """True if a root-relative POSIX path matches any forbidden pattern.

    Patterns are glob-or-literal (``.env``, ``*.pem``, ``secrets/``); a trailing
    slash forbids the whole subtree. Both the full relative path and the basename
    are tested so ``.env`` matches at any depth.
    """
    from fnmatch import fnmatch

    name = rel_posix.rsplit("/", 1)[-1]
    for raw in patterns:
        pat = raw.rstrip("/")
        if not pat:
            continue
        if rel_posix == pat or name == pat:
            return True
        if fnmatch(rel_posix, pat) or fnmatch(name, pat):
            return True
        if rel_posix.startswith(pat + "/"):
            return True
    return False


@dataclass
class FileEdit:
    """A single concrete file edit produced by an executor.

    Surgical edits (targeting only changed lines/blocks) are preferred; whole-file
    replacement is accepted as an explicit fallback when surgical edit is not
    possible (e.g. new file or heavy restructure). ``path`` is an absolute or
    root-relative path.
    """

    path: str
    content: str


@dataclass
class AppliedChange:
    """Record of a file that was actually written during apply."""

    path: str
    created: bool
    bytes_written: int


class CodeEditExecutor:
    """Minimal honest code-edit executor: write whole-file edits with rollback.

    Applies a list of :class:`FileEdit` to disk. On any failure mid-apply, ALL
    files touched so far are restored to their pre-apply state (created files are
    removed, modified files are reverted to their original bytes), then the
    original exception is re-raised. Returns the list of changed files only when
    the whole batch succeeds.
    """

    def __init__(self, root: Path, *, forbidden_paths: list[str] | None = None) -> None:
        self.root = Path(root)
        self.forbidden_paths = list(forbidden_paths or [])

    def _resolve(self, raw_path: str) -> Path:
        p = Path(raw_path)
        if not p.is_absolute():
            p = self.root / p
        # Containment guard (security boundary): an edit MUST stay within the
        # project root. Reject absolute paths and ../ escapes before any write.
        resolved = p.resolve()
        if not resolved.is_relative_to(self.root.resolve()):
            raise PermissionError(f"path escape blocked: {raw_path}")
        return resolved

    def _check_forbidden(self, edits: list[FileEdit]) -> None:
        """Raise before any write if an edit targets a forbidden path.

        Enforced here (the single write chokepoint) so the apply loop cannot
        touch secrets/build output the safety config declares off-limits. Checked
        for the whole batch up front, so a violation causes ZERO filesystem
        mutation rather than a write-then-rollback.
        """
        if not self.forbidden_paths:
            return
        for edit in edits:
            target = self._resolve(edit.path)
            try:
                rel = target.resolve().relative_to(self.root.resolve()).as_posix()
            except ValueError:
                rel = target.as_posix()
            if _path_is_forbidden(rel, self.forbidden_paths):
                raise PermissionError(f"edit to forbidden path blocked: {edit.path}")

    def apply(self, edits: list[FileEdit]) -> list[AppliedChange]:
        """Apply edits atomically with rollback on failure."""
        self._check_forbidden(edits)
        applied: list[AppliedChange] = []
        # (path, original_bytes_or_None_if_created)
        rollback: list[tuple[Path, bytes | None]] = []
        try:
            for edit in edits:
                target = self._resolve(edit.path)
                existed = target.exists()
                original = target.read_bytes() if existed and target.is_file() else None
                # Record rollback intent BEFORE mutating so partial writes revert.
                rollback.append((target, original if existed else None))
                target.parent.mkdir(parents=True, exist_ok=True)
                data = edit.content.encode("utf-8")
                target.write_bytes(data)
                applied.append(
                    AppliedChange(
                        path=str(target),
                        created=not existed,
                        bytes_written=len(data),
                    )
                )
            return applied
        except Exception:
            self._rollback(rollback)
            raise

    @staticmethod
    def _rollback(rollback: list[tuple[Path, bytes | None]]) -> None:
        """Restore every touched path to its pre-apply state."""
        for target, original in reversed(rollback):
            try:
                if original is None:
                    # File was created (or absent) before failure — remove it.
                    if target.exists() and target.is_file():
                        target.unlink()
                else:
                    target.write_bytes(original)
            except Exception:
                # Best-effort restore of the remaining files; keep going.
                continue


class ApplyPhase(HarnessPhase):
    """Apply phase: apply concrete executor edits to disk, honestly.

    Contract (honest reporting):
      - When the executor produced concrete file edits, write them to disk, list
        each changed file in the manifest, and report ``status="applied"``.
      - When no edits were produced, report ``status="planned"`` and make ZERO
        filesystem mutation. The manifest is NEVER ``"applied"`` over an empty
        ``changes`` list.
      - On a mid-apply failure, all touched files are rolled back and the phase
        reports ``status="failed"``.

    Checkpoint safety: before any write the phase snapshots exactly the target
    files into a harness-owned checkpoint, so the write is ``snapshot -> apply ->
    (on gate/approval failure or error) restore``. When ``verify_after_apply`` is
    supplied it runs after a successful write; if it returns ``False`` (a gate or
    approval rejected the change) the workspace is restored to the checkpoint
    byte-for-byte and the phase reports ``status="rolled_back"`` / FAILED. The
    checkpoint id and computed diff are exposed in the result metadata for
    inspection and replay.

    Edits are read from ``state.apply_edits`` (a list of ``{"path", "content"}``
    dicts or :class:`FileEdit`), which the executor/delegation layer populates.
    """

    id = "apply"

    def __init__(
        self,
        config: PhaseConfig,
        budget_mode: BudgetMode = BudgetMode.WARN,
        *,
        verify_after_apply: Callable[[list[dict[str, Any]]], bool] | None = None,
        forbidden_paths: list[str] | None = None,
    ) -> None:
        super().__init__(config, budget_mode)
        # Optional post-apply check. Returns True to keep the write, False to
        # roll back to the checkpoint (e.g. a post-write gate/approval rejected
        # the change). When None, a successful write is always kept.
        self._verify_after_apply = verify_after_apply
        # Paths the executor must never write (secrets, build output). Enforced in
        # the edit executor before any write.
        self._forbidden_paths = list(forbidden_paths or [])

    @staticmethod
    def _collect_edits(state: Any) -> list[FileEdit]:
        raw = getattr(state, "apply_edits", None) or []
        edits: list[FileEdit] = []
        for item in raw:
            if isinstance(item, FileEdit):
                edits.append(item)
            elif isinstance(item, dict) and "path" in item and "content" in item:
                edits.append(FileEdit(path=str(item["path"]), content=str(item["content"])))
            else:
                # Attempt ApplyEdit materialisation: read the current file, apply
                # the surgical op in-memory, and emit a whole-file FileEdit.
                # This preserves the checkpoint/forbidden/rollback machinery intact.
                try:
                    from opencontext_core.agents.executor import ApplyEdit, apply_edit

                    if not isinstance(item, ApplyEdit):
                        continue
                    root: Path = getattr(state, "root", Path("."))
                    # apply_edit writes to disk; we want in-memory only, so we
                    # work on a temp copy and then read the result back.
                    import shutil
                    import tempfile

                    file_path = root / item.path
                    if not file_path.exists():
                        # CREATE_FILE op — apply directly, emit result.
                        with tempfile.TemporaryDirectory() as tmp:
                            tmp_root = Path(tmp)
                            apply_edit(tmp_root, item)
                            result_content = (tmp_root / item.path).read_text(encoding="utf-8")
                        edits.append(FileEdit(path=item.path, content=result_content))
                    else:
                        # Existing file: copy to temp dir, apply op, read result.
                        with tempfile.TemporaryDirectory() as tmp:
                            tmp_root = Path(tmp)
                            tmp_file = tmp_root / item.path
                            tmp_file.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(file_path, tmp_file)
                            apply_edit(tmp_root, item)
                            result_content = tmp_file.read_text(encoding="utf-8")
                        edits.append(FileEdit(path=item.path, content=result_content))
                except Exception:
                    # Silently skip unapplied ApplyEdit; the run continues with
                    # whatever edits DID materialise.
                    pass
        return edits

    @staticmethod
    def _edit_targets(state: Any, edits: list[FileEdit]) -> list[Path]:
        """Resolve the on-disk targets the edits will write, for checkpointing."""
        executor = CodeEditExecutor(state.root)
        return [executor._resolve(e.path) for e in edits]

    def run(self, state: Any) -> PhaseResult:
        run_dir = resolve_workspace_path(state.root, StorageMode.local) / "runs" / state.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        apply_manifest_path = run_dir / "apply-manifest.json"

        edits = self._collect_edits(state)
        changes: list[dict[str, Any]] = []
        apply_status = "planned"
        phase_status = GateStatus.PASSED
        error: str | None = None
        checkpoint = None
        diff_changes: list[dict[str, str]] = []

        durable = bool(getattr(state, "durable_artifacts", False)) and bool(
            getattr(state, "session_id", "")
        )

        if edits:
            # Snapshot exactly the files about to change BEFORE touching them, so
            # a post-apply rejection (or error) can restore them byte-for-byte.
            # On the durable path use CheckpointManager so per-file pre-apply
            # checksums are recorded (CHK-02) for the ApplyReceipt before/after.
            if durable:
                from opencontext_core.harness.checkpoint import CheckpointManager

                checkpoint = CheckpointManager(state.root).create(
                    self._edit_targets(state, edits),
                    session_id=state.session_id,
                    run_id=state.run_id,
                )
            else:
                checkpoint = CheckpointStore(state.root).create(self._edit_targets(state, edits))
            executor = CodeEditExecutor(state.root, forbidden_paths=self._forbidden_paths)
            try:
                applied = executor.apply(edits)
                changes = [
                    {
                        "path": c.path,
                        "created": c.created,
                        "bytes_written": c.bytes_written,
                    }
                    for c in applied
                ]
                apply_status = "applied"
                if checkpoint is not None:
                    diff_changes = [{"path": c.path, "change": c.change} for c in checkpoint.diff()]
                # Post-apply verification: a False result (gate/approval rejected
                # the write) rolls the workspace back to the checkpoint.
                if self._verify_after_apply is not None and not self._verify_after_apply(changes):
                    if checkpoint is not None:
                        checkpoint.restore()
                    apply_status = "rolled_back"
                    phase_status = GateStatus.FAILED
                    error = "post-apply verification failed — rolled back to checkpoint"
                    changes = []
            except Exception as exc:
                # The executor rolls back its own partial writes; also restore the
                # checkpoint so the workspace is guaranteed pre-apply state.
                if checkpoint is not None:
                    checkpoint.restore()
                error = str(exc)
                apply_status = "failed"
                phase_status = GateStatus.FAILED
                changes = []

        apply_manifest = {
            "run_id": state.run_id,
            "task": state.task,
            "created_at": datetime.now(UTC).isoformat(),
            "status": apply_status,
            "changes": changes,
            "checkpoint_id": checkpoint.id if checkpoint is not None else None,
            "diff": diff_changes,
            "summary": (
                f"Applied {len(changes)} file edit(s) for: {state.task}"
                if apply_status == "applied"
                else (
                    f"Apply rolled back to checkpoint for: {state.task}"
                    if apply_status == "rolled_back"
                    else (
                        f"Apply failed and rolled back for: {state.task}"
                        if apply_status == "failed"
                        else f"No executor edits — planned only for: {state.task}"
                    )
                )
            ),
        }
        if error is not None:
            apply_manifest["error"] = error
        apply_manifest_path.write_text(json.dumps(apply_manifest, indent=2), encoding="utf-8")

        # PR-002 durable evidence (flag-guarded). Additive: writes the patch
        # artifact, per-file ApplyReceipts and the checkpoint record under the
        # session run tree, and routes rollback through harness/rollback.py. The
        # non-durable path above is byte-identical to PR-001.
        durable_meta: dict[str, Any] = {}
        if durable and checkpoint is not None and edits:
            try:
                durable_meta = self._emit_durable_evidence(
                    state, checkpoint, changes, apply_status, error
                )
            except Exception as _dur_exc:  # evidence is additive — never fail apply
                durable_meta = {"durable_error": str(_dur_exc)}

        # Keep the KG fresh mid-flow: incrementally re-index the files this phase changed
        # so verify/review reason over the POST-change graph, not the stale explore-time
        # snapshot. Best-effort — a reindex failure never fails apply.
        # The KG keys every node by ROOT-RELATIVE path; the executor records absolute
        # paths, so convert them or reindex writes duplicate absolute-keyed nodes and
        # never prunes the stale relative-keyed ones (verify/review would stay stale).
        changed_paths: set[str] = set()
        for c in changes:
            p = c.get("path")
            if not p:
                continue
            try:
                changed_paths.add(Path(p).resolve().relative_to(state.root).as_posix())
            except ValueError:
                changed_paths.add(p)  # outside the root — pass through unchanged
        if changed_paths and apply_status != "failed":
            try:
                from opencontext_core.runtime import OpenContextRuntime

                OpenContextRuntime(
                    storage_path=resolve_storage_path(state.root, StorageMode.local)
                ).reindex_files(changed_paths, root=state.root)
            except Exception:
                pass  # freshness is best-effort; never block apply on a reindex error

        gates: list[PhaseGate] = [
            ArtifactPersistedGate().evaluate(apply_manifest_path),
        ]
        ledger = PhaseLedger(
            phase="apply",
            used_tokens=0,
            budget_tokens=self.config.budget_tokens,
            budget_mode=self.budget_mode,
        )

        if any(g.status == GateStatus.FAILED for g in gates):
            phase_status = GateStatus.FAILED

        return PhaseResult(
            phase="apply",
            status=phase_status,
            ledger=ledger,
            gates=gates,
            artifacts=[
                HarnessArtifact(
                    id=f"apply-manifest-{state.run_id[:8]}",
                    phase="apply",
                    path=str(apply_manifest_path),
                    kind="apply-manifest",
                    description="Apply manifest with change tracking",
                )
            ],
            metadata={
                "manifest_path": str(apply_manifest_path),
                "apply_status": apply_status,
                "changed_files": [c["path"] for c in changes],
                "checkpoint_id": checkpoint.id if checkpoint is not None else None,
                "diff": diff_changes,
                **durable_meta,
            },
        )

    @staticmethod
    def _emit_durable_evidence(
        state: Any,
        checkpoint: Any,
        changes: list[dict[str, Any]],
        apply_status: str,
        error: str | None,
    ) -> dict[str, Any]:
        """Write the PR-002 evidence for one apply: patch + ApplyReceipts +
        checkpoint record, or rollback receipt/report/events on failure.

        Returns metadata merged into the phase result. Assumes ``state`` carries
        ``session_id``; ``apply`` is the only mutating phase, so this is its seam.
        """
        from opencontext_core.agentic.receipt import sha256_file
        from opencontext_core.harness.artifact_store import ArtifactStore
        from opencontext_core.harness.checkpoint import CheckpointManager
        from opencontext_core.harness.receipt_store import ReceiptStore
        from opencontext_core.harness.rollback import rollback as do_rollback
        from opencontext_core.harness.sessions import (
            build_unified_diff,
            ensure_layout,
            next_patch_path,
        )
        from opencontext_core.models.receipt import ApplyReceipt

        session_id = state.session_id
        run_id = state.run_id
        run_dir = ensure_layout(state.root, session_id, run_id)
        artifact_store = ArtifactStore(run_dir)
        receipt_store = ReceiptStore(run_dir)

        # Persist the checkpoint record so it links into the run manifest (CHK-02).
        cp_model = CheckpointManager(state.root).model(
            checkpoint, session_id=session_id, run_id=run_id
        )
        checkpoint_path = run_dir / "checkpoints" / f"{cp_model.checkpoint_id}.json"
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_text(cp_model.model_dump_json(indent=2), encoding="utf-8")
        before = cp_model.checksums
        meta: dict[str, Any] = {
            "durable_run_dir": str(run_dir),
            "durable_checkpoint_id": cp_model.checkpoint_id,
        }

        if apply_status == "applied" and changes:
            patch_text = build_unified_diff(checkpoint)
            patch_path = next_patch_path(run_dir)
            patch_path.write_text(patch_text, encoding="utf-8")
            diff_rel = patch_path.relative_to(run_dir).as_posix()
            patch_ref = artifact_store.register_file(
                patch_path,
                kind="patch",
                run_id=run_id,
                session_id=session_id,
                media_type="text/x-diff",
                produced_by="apply",
                metadata={"checkpoint_id": cp_model.checkpoint_id},
            )
            receipt_ids: list[str] = []
            for change in changes:
                path = change["path"]
                created = bool(change.get("created"))
                checksum_after = sha256_file(path)
                checksum_before = before.get(path)
                changed = created or (checksum_before != checksum_after)
                receipt = ApplyReceipt(
                    path=path,
                    operation="create" if created else "modify",
                    changed=changed,
                    checksum_before=checksum_before,
                    checksum_after=checksum_after,
                    diff_path=diff_rel,
                    reason=state.task,
                )
                receipt_store.write(receipt)
                receipt_ids.append(receipt.receipt_id)
            meta["patch_path"] = diff_rel
            meta["patch_artifact_id"] = patch_ref.artifact_id
            meta["apply_receipt_ids"] = receipt_ids
        elif apply_status in ("rolled_back", "failed"):
            # The inline restore already ran above; emit evidence only.
            events: list[Any] = []
            rb = do_rollback(
                checkpoint,
                run_dir=run_dir,
                reason=error or f"apply {apply_status}",
                session_id=session_id,
                run_id=run_id,
                artifact_store=artifact_store,
                receipt_store=receipt_store,
                events=events,
                restore=False,
            )
            meta["rollback_receipt_id"] = rb.receipt_id
            meta["rollback_report_artifact_id"] = rb.report_artifact_id
            meta["rollback_events"] = [e.model_dump(mode="json") for e in events]

        return meta


class SpecPhase(HarnessPhase):
    """Spec phase: read proposal and produce structured spec with requirements and scenarios."""

    id = "spec"

    def run(self, state: Any) -> PhaseResult:
        run_dir = resolve_workspace_path(state.root, StorageMode.local) / "runs" / state.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        proposal_path = run_dir / "proposal.json"
        spec_path = run_dir / "spec.md"

        # Read proposal artifact
        if not proposal_path.exists():
            return PhaseResult(
                phase="spec",
                status=GateStatus.FAILED,
                gates=[],
                metadata={"error": "Proposal artifact missing"},
            )

        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
        task = proposal.get("task", state.task)
        approach = proposal.get("approach", {})
        # Forward the compacted proposal to the spec executor — the model-facing handoff
        # (was previously read raw / never forwarded to the executor).
        state.prior_artifact = _compact_artifact(
            f"## Proposal from the prior phase\n{proposal_path.read_text(encoding='utf-8')}",
            state,
        )

        # Honest executor contract: run the real executor when wired, otherwise
        # emit a clearly-marked scaffold reported as "planned" (NOT a success).
        outcome = run_phase_executor(state, "spec")
        if outcome.is_real:
            spec_content = outcome.output or ""
        else:
            if getattr(state, "delegate", None) is None:
                state.warnings.append(
                    "Phase 'SpecPhase': no model bound — emitted a structured plan for your "
                    "agent's model to complete. Run OpenContext inside your AI agent "
                    "(Claude Code, Codex, OpenCode, …) to use its selected model, or set a "
                    "provider for standalone generation."
                )
            # Static template SCAFFOLD — explicitly NOT a real AI-produced spec.
            spec_content = f"""# Delta Spec: {task}

> SCAFFOLD — generated by a static template, not an executor. No agent/LLM was
> wired for the spec phase, so this is a planning placeholder, not a completed
> artifact. Wire an executor (state.delegate) to produce a real spec.

## ADDED Requirements

### Requirement: {task.replace("-", " ").title()}
MUST implement the feature described as: {task}.

#### Scenario: Basic implementation
GIVEN a harness run with task "{task}"
WHEN the SDD workflow executes
THEN the system SHALL produce artifacts for all required phases

#### Scenario: Implementation follows provider-neutral approach
GIVEN the approach specification: {approach}
WHEN implementation is designed
THEN the code SHALL remain provider-neutral (no external LLM provider coupling)

## MODIFIED Requirements

_None — initial implementation._

## REMOVED Requirements

_None._

## Success Criteria

- SpecPhase writes valid markdown spec with RFC 2119 requirements and GIVEN/WHEN/THEN scenarios
- Spec artifact is persisted to `.opencontext/runs/{{run_id}}/spec.md`
"""
        spec_path.write_text(spec_content, encoding="utf-8")
        manifest_path = _write_phase_manifest(run_dir, "spec", spec_path, task, outcome)

        gates: list[PhaseGate] = [
            ArtifactPersistedGate().evaluate(spec_path),
            _guardrail_gate("spec", spec_content, strict=bool(getattr(state, "sdd_strict", False))),
            _phase_contract_gate("spec", spec_content, enabled=outcome.is_real),
        ]
        ledger = self._token_ledger(
            "spec", estimate_tokens(outcome.output or "") if outcome.is_real else 0
        )
        gates.append(TokenBudgetGate().evaluate(ledger))

        status = (
            GateStatus.FAILED
            if any(g.status == GateStatus.FAILED for g in gates)
            else outcome.gate_status
        )

        return PhaseResult(
            phase="spec",
            status=status,
            ledger=ledger,
            gates=gates,
            artifacts=[
                HarnessArtifact(
                    id=f"spec-{state.run_id[:8]}",
                    phase="spec",
                    path=str(spec_path),
                    kind="spec",
                    description=f"Spec for: {task}",
                )
            ],
            metadata={
                "spec_path": str(spec_path),
                "manifest_path": str(manifest_path),
                "executor": outcome.executor,
            },
        )


class DesignPhase(HarnessPhase):
    """Design phase: read spec and produce technical design with architecture decisions."""

    id = "design"

    def run(self, state: Any) -> PhaseResult:
        run_dir = resolve_workspace_path(state.root, StorageMode.local) / "runs" / state.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        spec_path = run_dir / "spec.md"
        design_path = run_dir / "design.md"

        # Read spec artifact
        if not spec_path.exists():
            return PhaseResult(
                phase="design",
                status=GateStatus.FAILED,
                gates=[],
                metadata={"error": "Spec artifact missing"},
            )

        # Compact the forwarded spec artifact toward the handoff budget (B2). A
        # spec already within budget passes through unchanged; an oversized one is
        # condensed (model when wired, deterministic line-trim otherwise).
        spec_content = _compact_artifact(spec_path.read_text(encoding="utf-8"), state)
        task = state.task
        # Forward the compacted spec to the design executor — the model-facing handoff.
        state.prior_artifact = f"## Spec from the prior phase (compacted)\n{spec_content}"

        # Honest executor contract: run the real executor when wired, otherwise
        # emit a clearly-marked scaffold reported as "planned" (NOT a success).
        outcome = run_phase_executor(state, "design")
        if outcome.is_real:
            design_content = outcome.output or ""
        else:
            if getattr(state, "delegate", None) is None:
                state.warnings.append(
                    "Phase 'DesignPhase': no model bound — emitted a structured plan for your "
                    "agent's model to complete. Run OpenContext inside your AI agent "
                    "(Claude Code, Codex, OpenCode, …) to use its selected model, or set a "
                    "provider for standalone generation."
                )
            # Extract requirements from spec content for the scaffold body.
            requirements = []
            for line in spec_content.split("\n"):
                if "### Requirement:" in line or "### " in line:
                    requirements.append(line.lstrip("# ").strip())
            req_lines = (
                "\n".join(f"- {r}" for r in requirements[:5])
                if requirements
                else "- (analyze spec.md for details)"
            )
            # Static template SCAFFOLD — explicitly NOT a real AI-produced design.
            design_content = f"""# Design: {task}

> SCAFFOLD — generated by a static template, not an executor. No agent/LLM was
> wired for the design phase, so this is a planning placeholder, not a completed
> artifact. Wire an executor (state.delegate) to produce a real design.

## Architecture

This section describes the high-level architecture for implementing: {task}.

### Components
- New components should follow the existing patterns in the codebase
- Provider-neutral design: no direct coupling to external LLM APIs

## Files to Create/Modify

{req_lines}

## Dependencies

- No new external dependencies required
- Uses existing opencontext_core modules

## Data Flow

```
(state) --> SpecPhase --> DesignPhase --> TasksPhase --> ApplyPhase
```

## Testing Strategy

- Unit tests for new components
- Integration tests for phase interactions
- Provider-neutral test fixtures
"""
        design_path.write_text(design_content, encoding="utf-8")
        manifest_path = _write_phase_manifest(run_dir, "design", design_path, task, outcome)

        gates: list[PhaseGate] = [
            ArtifactPersistedGate().evaluate(design_path),
            _guardrail_gate(
                "design", design_content, strict=bool(getattr(state, "sdd_strict", False))
            ),
            _phase_contract_gate("design", design_content, enabled=outcome.is_real),
        ]
        ledger = self._token_ledger(
            "design", estimate_tokens(outcome.output or "") if outcome.is_real else 0
        )
        gates.append(TokenBudgetGate().evaluate(ledger))

        status = (
            GateStatus.FAILED
            if any(g.status == GateStatus.FAILED for g in gates)
            else outcome.gate_status
        )

        return PhaseResult(
            phase="design",
            status=status,
            ledger=ledger,
            gates=gates,
            artifacts=[
                HarnessArtifact(
                    id=f"design-{state.run_id[:8]}",
                    phase="design",
                    path=str(design_path),
                    kind="design",
                    description=f"Design for: {task}",
                )
            ],
            metadata={
                "design_path": str(design_path),
                "manifest_path": str(manifest_path),
                "executor": outcome.executor,
            },
        )


class TasksPhase(HarnessPhase):
    """Tasks phase: read design and produce task breakdown as JSON."""

    id = "tasks"

    def run(self, state: Any) -> PhaseResult:
        run_dir = resolve_workspace_path(state.root, StorageMode.local) / "runs" / state.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        design_path = run_dir / "design.md"
        tasks_path = run_dir / "tasks.json"

        # Read design artifact
        if not design_path.exists():
            return PhaseResult(
                phase="tasks",
                status=GateStatus.FAILED,
                gates=[],
                metadata={"error": "Design artifact missing"},
            )

        # Compact the forwarded design artifact toward the handoff budget (B2),
        # mirroring the spec->design handoff. No-op when already within budget.
        design_content = _compact_artifact(design_path.read_text(encoding="utf-8"), state)
        task = state.task
        # Forward the compacted design to the tasks executor — the model-facing handoff.
        state.prior_artifact = f"## Design from the prior phase (compacted)\n{design_content}"

        # Honest executor contract: run the real executor when wired, otherwise
        # emit a clearly-marked scaffold reported as "planned" (NOT a success).
        outcome = run_phase_executor(state, "tasks")
        if not outcome.is_real and getattr(state, "delegate", None) is None:
            state.warnings.append(
                "Phase 'TasksPhase': no model bound — emitted a structured plan for your "
                "agent's model to complete. Run OpenContext inside your AI agent "
                "(Claude Code, Codex, OpenCode, …) to use its selected model, or set a "
                "provider for standalone generation."
            )
        task_count = 0
        if outcome.is_real:
            # The executor owns the breakdown format. Persist its output as-is,
            # preferring structured JSON when it parsed, else wrap it verbatim.
            raw = outcome.output or ""
            try:
                parsed = json.loads(raw)
                tasks_path.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
                task_count = len(parsed) if isinstance(parsed, list) else 1
            except json.JSONDecodeError:
                tasks_path.write_text(
                    json.dumps({"executor_output": raw}, indent=2), encoding="utf-8"
                )
                task_count = 1
        else:
            # Parse files from design content for the scaffold breakdown.
            file_pattern = re.compile(r"[-*] (.+\.(?:py|ts|js|go|rs))")
            files = file_pattern.findall(design_content)
            tasks: list[dict[str, Any]] = []
            if files:
                for i, f in enumerate(files, 1):
                    tasks.append(
                        {
                            "id": f"task-{i}",
                            "description": f"Implement {f} per design",
                            "file_paths": [f],
                            "complexity": "medium",
                        }
                    )
            else:
                # No files in the design scaffold (e.g. no model filled it). Use the
                # files the explore phase actually surfaced for THIS task — never a
                # hard-coded path (which previously leaked OpenContext's own internals
                # into every project's task plan).
                candidate_files = list(
                    dict.fromkeys(getattr(state, "context_required_sources", []) or [])
                )
                if not candidate_files:
                    sources: set[str] = getattr(state, "context_sources", set()) or set()
                    candidate_files = sorted({str(s).split(":")[0] for s in sources})
                tasks.append(
                    {
                        "id": "task-1",
                        "description": f"Implement feature: {task}",
                        "file_paths": candidate_files,
                        "complexity": "medium",
                    }
                )
            # Always include a test task
            tasks.append(
                {
                    "id": "task-test",
                    "description": "Write failing test before implementation",
                    "file_paths": ["tests/"],
                    "complexity": "low",
                }
            )
            # Wrap the scaffold so the artifact is explicitly NOT a real
            # AI-produced breakdown — it is a planning placeholder.
            scaffold = {
                "_scaffold": True,
                "_note": (
                    "SCAFFOLD — static template, not an executor. No agent/LLM was "
                    "wired for the tasks phase; this is a planning placeholder, not "
                    "a completed artifact. Wire an executor (state.delegate)."
                ),
                "tasks": tasks,
            }
            tasks_path.write_text(json.dumps(scaffold, indent=2), encoding="utf-8")
            task_count = len(tasks)

        manifest_path = _write_phase_manifest(run_dir, "tasks", tasks_path, task, outcome)

        gates: list[PhaseGate] = [
            ArtifactPersistedGate().evaluate(tasks_path),
            _guardrail_gate(
                "tasks",
                tasks_path.read_text(encoding="utf-8"),
                strict=bool(getattr(state, "sdd_strict", False)),
            ),
            _phase_contract_gate(
                "tasks", tasks_path.read_text(encoding="utf-8"), enabled=outcome.is_real
            ),
        ]
        ledger = self._token_ledger(
            "tasks", estimate_tokens(outcome.output or "") if outcome.is_real else 0
        )
        gates.append(TokenBudgetGate().evaluate(ledger))

        status = (
            GateStatus.FAILED
            if any(g.status == GateStatus.FAILED for g in gates)
            else outcome.gate_status
        )

        return PhaseResult(
            phase="tasks",
            status=status,
            ledger=ledger,
            gates=gates,
            artifacts=[
                HarnessArtifact(
                    id=f"tasks-{state.run_id[:8]}",
                    phase="tasks",
                    path=str(tasks_path),
                    kind="tasks",
                    description=f"Task breakdown for: {task}",
                )
            ],
            metadata={
                "task_count": task_count,
                "manifest_path": str(manifest_path),
                "executor": outcome.executor,
            },
        )


class VerifyPhase(HarnessPhase):
    """Verify phase: run tests and validate implementation."""

    id = "verify"

    def run(self, state: Any) -> PhaseResult:
        run_dir = resolve_workspace_path(state.root, StorageMode.local) / "runs" / state.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        verify_report_path = run_dir / "verify-report.json"

        # NOTE: TDD failing-test ordering is enforced as an apply PRE-gate by the
        # runner (driven by harness.tdd_mode), NOT here in VerifyPhase. See
        # HarnessRunner._evaluate_apply_pre_gates.

        changed = [
            e["path"] if isinstance(e, dict) else getattr(e, "path", str(e))
            for e in (getattr(state, "apply_edits", None) or [])
        ]
        test_result = self._run_tests(state.root, changed_files=changed)
        # REQ-12: distinguish "no tests executed" from "all checks passed". A
        # vacuous exit_code==0 over zero scoped tests is NOT a real green — report
        # it honestly so a reader never mistakes "nothing ran" for "everything
        # passed". ``had_changes`` separates the genuine REQ-12 case (changed files
        # mapped to no test → advisory WARNING) from a benign no-op run (no edits
        # to verify → stays a neutral pass).
        tests_executed = bool(test_result.get("tests_executed", True))
        had_changes = bool(changed)
        if test_result["exit_code"] != 0:
            summary = f"Tests failed ({test_result['exit_code']})"
        elif not tests_executed:
            summary = (
                "No tests executed for changed files" if had_changes else "No changes to verify"
            )
        else:
            summary = "All checks passed"
        verify_report = {
            "run_id": state.run_id,
            "task": state.task,
            "created_at": datetime.now(UTC).isoformat(),
            "test_result": test_result,
            "tests_executed": tests_executed,
            "summary": summary,
        }
        verify_report_path.write_text(json.dumps(verify_report, indent=2), encoding="utf-8")

        gates: list[PhaseGate] = [
            ArtifactPersistedGate().evaluate(verify_report_path),
        ]

        ledger = PhaseLedger(
            phase="verify",
            used_tokens=0,
            budget_tokens=self.config.budget_tokens,
            budget_mode=self.budget_mode,
        )

        # If tests failed, mark as WARNING (not FAILED, since verify is about
        # reporting — FAILED is reserved for budget/gate violations)
        if test_result["exit_code"] != 0:
            gates.append(
                PhaseGate(
                    id="verify_tests_passed",
                    phase="verify",
                    status=GateStatus.WARNING,
                    message=f"Tests exited with code {test_result['exit_code']}",
                )
            )
        elif not tests_executed and had_changes:
            # REQ-12: changed files mapped to no test file — verify did not actually
            # run any test, so surface a non-PASS advisory instead of a silent green.
            gates.append(
                PhaseGate(
                    id="verify_no_tests",
                    phase="verify",
                    status=GateStatus.WARNING,
                    message=(
                        "No scoped tests executed for the changed files — verify ran zero "
                        "tests, so this is not a verified pass."
                    ),
                )
            )

        # Mutation testing hook (additive, non-breaking)
        try:
            from opencontext_core.config import load_config_or_defaults

            _cfg = load_config_or_defaults(state.root / "opencontext.yaml", auto_detect=False)
            _mut_cfg = getattr(getattr(_cfg, "testing", None), "mutation", None)
            if _mut_cfg is not None and getattr(_mut_cfg, "enabled", False):
                from opencontext_core.mutation.models import MutationResult  # noqa: F401
                from opencontext_core.mutation.runner import MutationRunner

                mutation_result = MutationRunner().run(
                    state.root,
                    scope="changed",
                    threshold=_mut_cfg.threshold,
                )
                gate_status = GateStatus.PASSED
                if not mutation_result.available:
                    gate_status = GateStatus.WARNING
                elif mutation_result.score < _mut_cfg.threshold:
                    gate_status = (
                        GateStatus.FAILED if _mut_cfg.fail_on_low_score else GateStatus.WARNING
                    )
                gates.append(
                    PhaseGate(
                        id="mutation-tests",
                        phase="verify",
                        status=gate_status,
                        message=(
                            f"Mutation coverage: {mutation_result.score:.1f}%"
                            if mutation_result.available
                            else (mutation_result.error or "Not available")
                        ),
                    )
                )
        except Exception:
            pass  # mutation is optional

        # ComplianceMatrix (additive, behind verify.compliance_matrix flag — default off).
        # Reads the spec from .sdd/changes/*/spec.md; skips gracefully when absent.
        compliance_matrix: Any = None
        try:
            from opencontext_core.config import load_config_or_defaults

            _vcfg = load_config_or_defaults(state.root / "opencontext.yaml", auto_detect=False)
            _compliance_enabled = bool(
                getattr(getattr(_vcfg, "verify", None), "compliance_matrix", False)
            )
            if _compliance_enabled:
                from opencontext_core.verify.compliance import (
                    ComplianceMatrix,
                    VerificationKind,
                    VerificationStatus,
                )

                # Resolve spec path: look for any spec.md under .sdd/changes/
                spec_path: Path | None = None
                sdd_changes = state.root / ".sdd" / "changes"
                if sdd_changes.exists():
                    candidates = sorted(sdd_changes.glob("*/spec.md"))
                    if candidates:
                        spec_path = candidates[-1]  # use most recently modified

                if spec_path is None or not spec_path.exists():
                    gates.append(
                        PhaseGate(
                            id="compliance_no_spec",
                            phase="verify",
                            status=GateStatus.WARNING,
                            message=(
                                "ComplianceMatrix: no spec.md found"
                                " — skipping requirement coverage check."
                            ),
                        )
                    )
                else:
                    matrix = ComplianceMatrix()
                    spec_text = spec_path.read_text(encoding="utf-8")
                    # Parse requirement IDs from lines like "### Requirement: REQ-xxx"
                    import re as _re

                    req_ids = _re.findall(r"###\s+Requirement:\s+(REQ-\S+)", spec_text)
                    passed_gate_ids = {g.id for g in gates if g.status == GateStatus.PASSED}
                    for req_id in req_ids:
                        # Mark PASS if there is a matching gate already; else MISSING
                        matched = any(req_id.lower() in gid.lower() for gid in passed_gate_ids)
                        matrix.add(
                            req_id,
                            kind=VerificationKind.GATE,
                            status=(
                                VerificationStatus.PASS if matched else VerificationStatus.MISSING
                            ),
                        )
                    compliance_matrix = matrix

                    missing_reqs = [
                        e.requirement_id
                        for e in matrix.iter_entries()
                        if e.status == VerificationStatus.MISSING
                    ]
                    gate_status = GateStatus.WARNING if missing_reqs else GateStatus.PASSED
                    gates.append(
                        PhaseGate(
                            id="compliance_matrix",
                            phase="verify",
                            status=gate_status,
                            message=(
                                f"ComplianceMatrix: {len(req_ids) - len(missing_reqs)}"
                                f"/{len(req_ids)} requirements covered."
                                + (f" Missing: {', '.join(missing_reqs)}" if missing_reqs else "")
                            ),
                            metadata={"matrix": matrix.model_dump(mode="json")},
                        )
                    )
        except Exception as _cm_exc:
            gates.append(
                PhaseGate(
                    id="compliance_matrix_error",
                    phase="verify",
                    status=GateStatus.WARNING,
                    message=f"ComplianceMatrix: failed to build ({_cm_exc})",
                )
            )

        status = (
            GateStatus.FAILED
            if any(g.status == GateStatus.FAILED for g in gates)
            else (
                GateStatus.WARNING
                if any(g.status == GateStatus.WARNING for g in gates)
                else GateStatus.PASSED
            )
        )

        return PhaseResult(
            phase="verify",
            status=status,
            ledger=ledger,
            gates=gates,
            artifacts=[
                HarnessArtifact(
                    id=f"verify-report-{state.run_id[:8]}",
                    phase="verify",
                    path=str(verify_report_path),
                    kind="verify-report",
                    description=verify_report["summary"],
                )
            ],
            metadata={
                "_compliance_matrix": compliance_matrix,
                "exit_code": test_result["exit_code"],
                "passed": test_result["passed"],
                "failed": test_result["failed"],
                "errors": test_result["errors"],
            },
        )

    def _resolve_test_targets(self, root: Path, changed_files: list[str]) -> list[str]:
        """Map changed source files to likely test files. Falls back to [] (full suite)."""
        if not changed_files:
            return []
        targets: list[str] = []
        for src in changed_files:
            p = Path(src)
            stem = p.stem
            # direct test file
            for candidate in [
                root / "tests" / f"test_{stem}.py",
                root / "tests" / p.parent / f"test_{stem}.py",
                root / f"test_{stem}.py",
                p.parent / f"test_{stem}.py",
            ]:
                if candidate.exists():
                    targets.append(str(candidate))
        # deduplicate while preserving order
        seen: set[str] = set()
        return [t for t in targets if not (t in seen or seen.add(t))]  # type: ignore[func-returns-value]

    def _run_tests(self, root: Path, changed_files: list[str] | None = None) -> dict[str, Any]:
        """Run pytest scoped to changed files when possible, full suite as fallback."""
        targets = self._resolve_test_targets(root, changed_files or [])
        if not targets:
            # No changed file maps to a test file — skip rather than run the whole
            # suite for a verify-report (slow, and pre-existing unrelated failures
            # would spuriously WARN the verify gate).
            return {
                "exit_code": 0,
                "passed": 0,
                "failed": 0,
                "errors": 0,
                "tests_executed": False,
                "output": "no scoped tests for changed files",
                "error_output": "",
            }
        args = [sys.executable, "-m", "pytest", "-q", "--tb=short", *targets]
        # CMD-1: route the command through the policy deny-list before executing.
        # Until PR-005 ``forbidden_commands`` was loaded but read by no execution
        # path; this is the wiring that makes it actually enforce. The harness only
        # ever runs pytest here (never a forbidden command), so legitimate flows are
        # unchanged — but any forbidden command is now refused instead of run.
        from opencontext_core.harness.config import HarnessConfig
        from opencontext_core.policy.commands import CommandClassifier

        harness_cfg = HarnessConfig()
        if harness_cfg.command_enforcement and CommandClassifier().is_forbidden(
            " ".join(args), harness_cfg.forbidden_commands
        ):
            return {
                "exit_code": -3,
                "passed": 0,
                "failed": 0,
                "errors": 1,
                "output": "",
                "error_output": "command blocked by policy: forbidden_command",
            }
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=120,
            )
            passed, failed, errors = self._parse_pytest_output(result.stdout)
            return {
                "exit_code": result.returncode,
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "tests_executed": True,
                "output": result.stdout[-2000:],
                "error_output": result.stderr[-1000:],
            }
        except subprocess.TimeoutExpired:
            return {
                "exit_code": -1,
                "passed": 0,
                "failed": 0,
                "errors": 1,
                "output": "",
                "error_output": "pytest timed out after 120s",
            }
        except FileNotFoundError:
            return {
                "exit_code": -2,
                "passed": 0,
                "failed": 0,
                "errors": 1,
                "output": "",
                "error_output": "pytest not found",
            }

    @staticmethod
    def _parse_pytest_output(output: str) -> tuple[int, int, int]:
        """Parse pytest -q summary line into (passed, failed, errors)."""
        import re

        # Matches: "12 passed", "3 failed", "1 error" in the summary line
        passed = sum(int(m) for m in re.findall(r"(\d+) passed", output))
        failed = sum(int(m) for m in re.findall(r"(\d+) failed", output))
        errors = sum(int(m) for m in re.findall(r"(\d+) error", output))
        return passed, failed, errors


class ReviewPhase(HarnessPhase):
    """Review phase: create a review summary by reading all phase artifacts.

    Produces a human- and machine-readable review.json that aggregates the
    state of every artifact produced during the run, making it easy to
    understand what was created without digging into individual files.
    """

    id = "review"

    def run(self, state: Any) -> PhaseResult:
        run_dir = resolve_workspace_path(state.root, StorageMode.local) / "runs" / state.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        review_path = run_dir / "review.json"

        # Read artifact summaries from disk where available
        artifact_summaries: list[dict[str, Any]] = []
        for artifact in state.artifacts:
            summary: dict[str, Any] = {
                "id": artifact.id,
                "phase": artifact.phase,
                "kind": artifact.kind,
                "path": artifact.path,
                "description": artifact.description,
            }
            # Try to read the artifact to extract a short preview
            artifact_path = Path(artifact.path)
            if artifact_path.exists() and artifact_path.stat().st_size < 50_000:
                try:
                    data = json.loads(artifact_path.read_text(encoding="utf-8"))
                    # Extract common summary fields when present
                    for key in ("summary", "status", "task", "description"):
                        if key in data:
                            summary[key] = data[key]
                except Exception:
                    pass
            artifact_summaries.append(summary)

        # Build a phase-by-phase status from ledgers
        phase_status: dict[str, dict[str, Any]] = {}
        for ledger in state.ledgers:
            phase_status[ledger.phase] = {
                "status": ledger.status.value,
                "used_tokens": ledger.used_tokens,
                "budget_tokens": ledger.budget_tokens,
                "remaining": ledger.remaining,
            }

        # Summarise gate outcomes
        gate_summary: dict[str, int] = {
            "passed": 0,
            "warning": 0,
            "failed": 0,
        }
        for g in state.gates:
            key = g.status.value
            if key in gate_summary:
                gate_summary[key] += 1

        review = {
            "run_id": state.run_id,
            "task": state.task,
            "created_at": datetime.now(UTC).isoformat(),
            "status": "completed",
            "phases": phase_status,
            "phases_completed": len(phase_status),
            "gates": gate_summary,
            "total_artifacts": len(state.artifacts),
            "artifacts": artifact_summaries,
            "total_decisions": len(state.decisions),
            "warnings": state.warnings,
            "trace_ids": state.trace_ids,
            # Legacy flat gate counts (for backward compatibility)
            "total_gates": len(state.gates),
            "passed_gates": gate_summary["passed"],
            "warning_gates": gate_summary["warning"],
            "failed_gates": gate_summary["failed"],
            "summary": (
                f"Review completed: {len(phase_status)} phases, "
                f"{gate_summary['passed']} gates passed, "
                f"{gate_summary['warning']} warnings, "
                f"{gate_summary['failed']} failures."
            ),
        }
        review_path.write_text(json.dumps(review, indent=2), encoding="utf-8")

        gates: list[PhaseGate] = [
            ArtifactPersistedGate().evaluate(review_path),
        ]
        if state.warnings:
            gates.append(
                PhaseGate(
                    id="review_warnings",
                    phase="review",
                    status=GateStatus.WARNING,
                    message=f"{len(state.warnings)} warnings during run",
                )
            )

        ledger = PhaseLedger(
            phase="review",
            used_tokens=0,
            budget_tokens=self.config.budget_tokens,
            budget_mode=self.budget_mode,
        )

        status = (
            GateStatus.FAILED
            if any(g.status == GateStatus.FAILED for g in gates)
            else (
                GateStatus.WARNING
                if any(g.status == GateStatus.WARNING for g in gates)
                else GateStatus.PASSED
            )
        )

        return PhaseResult(
            phase="review",
            status=status,
            ledger=ledger,
            gates=gates,
            artifacts=[
                HarnessArtifact(
                    id=f"review-{state.run_id[:8]}",
                    phase="review",
                    path=str(review_path),
                    kind="review",
                    description=f"Review summary for {state.run_id}",
                )
            ],
            metadata={
                "phases_completed": review["phases_completed"],
                "total_gates": review["total_gates"],
                "passed_gates": review["passed_gates"],
                "warning_gates": review["warning_gates"],
                "failed_gates": review["failed_gates"],
            },
        )


class JudgmentDayPhase(HarnessPhase):
    """Adversarial review: two independent evaluations of apply-phase artifacts.

    Reads artifacts from the apply phase and produces a judgment report with
    BLOCKER / SHOULD_FIX / NIT / APPROVED findings. No LLM is required —
    the phase performs a structural/heuristic review and records the result
    so a human or downstream phase can act on it.
    """

    id = "judgment"

    def run(self, state: Any) -> PhaseResult:
        run_dir = resolve_workspace_path(state.root, StorageMode.local) / "runs" / state.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        apply_artifacts = [a for a in state.artifacts if a.phase == "apply"]
        verify_artifacts = [a for a in state.artifacts if a.phase == "verify"]

        findings: list[dict[str, str]] = []
        blocker_count = 0
        should_fix_count = 0

        # Structural checks on apply artifacts
        for a in apply_artifacts:
            p = Path(a.path)
            if not p.exists():
                findings.append(
                    {
                        "severity": "BLOCKER",
                        "artifact": a.id,
                        "finding": f"Apply artifact missing on disk: {a.path}",
                    }
                )
                blocker_count += 1

        # Check verify was present
        if not verify_artifacts:
            findings.append(
                {
                    "severity": "SHOULD_FIX",
                    "artifact": "verify",
                    "finding": "No verify artifacts found — apply was not independently verified.",
                }
            )
            should_fix_count += 1

        # Check gate failures from apply + verify
        apply_failed_gates = [
            g
            for g in state.gates
            if g.phase in ("apply", "verify") and g.status == GateStatus.FAILED
        ]
        for g in apply_failed_gates:
            findings.append(
                {
                    "severity": "BLOCKER",
                    "artifact": g.id,
                    "finding": f"Gate failed in {g.phase}: {g.message}",
                }
            )
            blocker_count += 1

        # Warnings from state
        for w in state.warnings:
            if any(kw in w.lower() for kw in ("llm", "provider", "delegate", "executor")):
                findings.append(
                    {
                        "severity": "SHOULD_FIX",
                        "artifact": "warnings",
                        "finding": f"LLM/provider warning: {w}",
                    }
                )
                should_fix_count += 1

        if not findings:
            findings.append(
                {
                    "severity": "APPROVED",
                    "artifact": "all",
                    "finding": "No structural issues found. Human review recommended before merge.",
                }
            )

        overall = (
            "BLOCKER"
            if blocker_count > 0
            else ("SHOULD_FIX" if should_fix_count > 0 else "APPROVED")
        )

        report = {
            "run_id": state.run_id,
            "task": state.task,
            "created_at": datetime.now(UTC).isoformat(),
            "overall": overall,
            "blocker_count": blocker_count,
            "should_fix_count": should_fix_count,
            "findings": findings,
        }

        report_path = run_dir / "judgment.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

        gate_status = (
            GateStatus.FAILED
            if overall == "BLOCKER"
            else (GateStatus.WARNING if overall == "SHOULD_FIX" else GateStatus.PASSED)
        )
        gates: list[PhaseGate] = [
            PhaseGate(
                id="judgment_overall",
                phase="judgment",
                status=gate_status,
                message=f"Judgment: {overall} ({blocker_count} blockers, {should_fix_count} should-fix)",  # noqa: E501
            ),
            ArtifactPersistedGate().evaluate(report_path),
        ]

        ledger = PhaseLedger(
            phase="judgment",
            used_tokens=0,
            budget_tokens=self.config.budget_tokens,
            budget_mode=self.budget_mode,
        )

        return PhaseResult(
            phase="judgment",
            status=gate_status,
            ledger=ledger,
            gates=gates,
            artifacts=[
                HarnessArtifact(
                    id=f"judgment-{state.run_id[:8]}",
                    phase="judgment",
                    path=str(report_path),
                    kind="judgment",
                    description=f"Adversarial review report: {overall}",
                )
            ],
            metadata={"overall": overall, "findings": len(findings)},
        )


class GGARulesPhase(HarnessPhase):
    """Guardian Angel rules enforcement.

    Reads `.opencontext/rules.yaml` and validates the apply-phase diffs
    against project-level coding standards (max lines, forbidden patterns,
    required docstrings, etc.). No LLM required.
    """

    id = "gga"

    @staticmethod
    def _changed_source_paths(state: Any) -> list[str]:
        """Source files the apply phase actually wrote, from its manifest."""
        paths: list[str] = []
        for artifact in state.artifacts:
            if artifact.phase != "apply":
                continue
            manifest_path = Path(artifact.path)
            if manifest_path.name != "apply-manifest.json" or not manifest_path.exists():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for change in manifest.get("changes", []):
                path = change.get("path")
                if path:
                    paths.append(str(path))
        return paths

    def run(self, state: Any) -> PhaseResult:
        run_dir = resolve_workspace_path(state.root, StorageMode.local) / "runs" / state.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        rules = self._load_rules(state.root)
        violations: list[dict[str, str]] = []

        # Scan the source the apply phase actually wrote (manifest changes[].path),
        # not the apply-manifest.json artifact itself — whose .json suffix was
        # always skipped, so every quality rule passed vacuously.
        for raw_path in self._changed_source_paths(state):
            p = Path(raw_path)
            if not p.exists() or p.suffix not in (".py", ".ts", ".js", ".go", ".rs"):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            lines = text.splitlines()
            max_lines = rules.get("max_lines_per_file", 0)
            if max_lines and len(lines) > max_lines:
                violations.append(
                    {
                        "severity": "SHOULD_FIX",
                        "file": str(p),
                        "rule": "max_lines_per_file",
                        "detail": f"{len(lines)} lines (limit {max_lines})",
                    }
                )

            for pattern in rules.get("forbidden_patterns", []):
                if pattern in text:
                    violations.append(
                        {
                            "severity": "BLOCKER",
                            "file": str(p),
                            "rule": "forbidden_pattern",
                            "detail": f"Forbidden pattern found: {pattern!r}",
                        }
                    )

        blocker_count = sum(1 for v in violations if v["severity"] == "BLOCKER")

        report = {
            "run_id": state.run_id,
            "created_at": datetime.now(UTC).isoformat(),
            "rules_file": str(resolve_workspace_path(state.root, StorageMode.local) / "rules.yaml"),
            "violations": violations,
            "blocker_count": blocker_count,
        }

        report_path = run_dir / "gga.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

        gate_status = (
            GateStatus.FAILED
            if blocker_count > 0
            else (GateStatus.WARNING if violations else GateStatus.PASSED)
        )
        gates: list[PhaseGate] = [
            PhaseGate(
                id="gga_rules",
                phase="gga",
                status=gate_status,
                message=f"GGA: {blocker_count} blockers, {len(violations)} total violations",
            ),
            ArtifactPersistedGate().evaluate(report_path),
        ]

        ledger = PhaseLedger(
            phase="gga",
            used_tokens=0,
            budget_tokens=self.config.budget_tokens,
            budget_mode=self.budget_mode,
        )

        return PhaseResult(
            phase="gga",
            status=gate_status,
            ledger=ledger,
            gates=gates,
            artifacts=[
                HarnessArtifact(
                    id=f"gga-{state.run_id[:8]}",
                    phase="gga",
                    path=str(report_path),
                    kind="gga_report",
                    description=f"GGA rules report: {len(violations)} violations",
                )
            ],
            metadata={"blocker_count": blocker_count, "violations": len(violations)},
        )

    @staticmethod
    def _load_rules(root: Path) -> dict[str, Any]:
        """Load .opencontext/rules.yaml if present, else return empty rules."""
        rules_path = resolve_workspace_path(root, StorageMode.local) / "rules.yaml"
        if not rules_path.exists():
            return {}
        try:
            import importlib.util

            if importlib.util.find_spec("yaml") is not None:
                import yaml  # type: ignore[import-untyped,unused-ignore]

                data = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
        except Exception:
            pass
        return {}
