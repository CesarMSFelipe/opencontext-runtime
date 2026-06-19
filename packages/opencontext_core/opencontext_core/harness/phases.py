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
from typing import Any

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
            storage_path=state.root / ".storage" / "opencontext",
        )
        manifest = runtime.index_project(state.root)
        pack = runtime.build_context_pack(state.task, state.max_tokens or self.config.budget_tokens)

        # Persist context pack to run directory
        run_dir = state.root / ".opencontext" / "runs" / state.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        pack_path = run_dir / "context-pack.json"
        pack_path.write_text(pack.model_dump_json(indent=2), encoding="utf-8")

        # Make the verified context available to later work phases' executor prompts
        # (spec/design/tasks) so the model works from retrieved evidence, not the
        # bare task. Rendered compactly as "source\ncontent" blocks.
        state.context_pack = "\n\n".join(
            f"### {item.source}\n{item.content}" for item in pack.included
        )

        # KG wiring: run impact analysis if task is provided
        impact_affected_files: list[str] = []
        impact_affected_tests: list[str] = []
        kg_available: bool = False
        kg_error: str | None = None
        try:
            from opencontext_core.indexing.impact_analysis import ImpactAnalyzer

            db_path = state.root / ".storage" / "opencontext" / "context_graph.db"
            if db_path.exists():
                from opencontext_core.indexing.graph_db import GraphDatabase

                db = GraphDatabase(db_path)
                analyzer = ImpactAnalyzer(db)
                impact_results = analyzer.analyze_by_name(state.task, depth=2)
                kg_available = True
                for ir in impact_results:
                    impact_affected_files.extend(ir.affected_files)
                    impact_affected_tests.extend(ir.affected_tests)
                db.close()
            else:
                kg_error = "context_graph.db not found — run `opencontext index` first"
        except Exception as exc:
            kg_error = str(exc)
            # KG wiring is best-effort — don't fail the phase if KG is unavailable

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

        # Memory context enrichment (additive, non-breaking)
        if hasattr(self, "_memory_store") and self._memory_store is not None:
            try:
                self._memory_store.search(state.task, limit=5)
            except Exception:
                pass  # memory is optional, never block explore

        # Build context contract (additive, non-breaking)
        explore_artifacts: list[HarnessArtifact] = [
            HarnessArtifact(
                id=f"explore-pack-{state.run_id[:8]}",
                phase="explore",
                path=str(state.root / ".opencontext" / "runs" / state.run_id / "context-pack.json"),
                kind="context-pack",
                description=f"Context pack with {len(pack.included)} items",
            )
        ]
        try:
            from opencontext_core.context.planning.classifier import TaskClassifier
            from opencontext_core.context.planning.contract import ContextContractBuilder
            from opencontext_core.context.planning.risk import RiskClassifier

            contract_builder = ContextContractBuilder(
                classifier=TaskClassifier(),
                risk_classifier=RiskClassifier(),
            )
            contract = contract_builder.build(state.task)
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
            pass  # contract building is additive, never block explore

        # Record context provenance for the propose phase's provenance gates.
        state.context_sources = {item.source for item in pack.included}
        state.context_required_sources = list(dict.fromkeys(impact_affected_files))
        state.context_omitted = len(pack.omitted)
        state.context_omissions_recorded = len(pack.omissions)

        return PhaseResult(
            phase="explore",
            status=status,
            ledger=ledger,
            gates=gates,
            artifacts=explore_artifacts,
            metadata={
                "included": len(pack.included),
                "omitted": len(pack.omitted),
                "indexed_files": len(manifest.files),
                "indexed_symbols": len(manifest.symbols),
                "impact_affected_files": impact_affected_files,
                "impact_affected_tests": impact_affected_tests,
                "kg_available": kg_available,
                "kg_error": kg_error,
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
    ) -> None:
        super().__init__(config, budget_mode)
        self._memory_store = memory_store

    def run(self, state: Any) -> PhaseResult:
        run_dir = state.root / ".opencontext" / "runs" / state.run_id
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
                    status=GateStatus.PASSED,
                    ledgers=state.ledgers,
                    gates=state.gates,
                    artifacts=state.artifacts,
                    decisions=state.decisions,
                    trace_ids=state.trace_ids,
                    warnings=state.warnings,
                )
                harvester = MemoryHarvester(self._memory_store)
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
        run_dir = state.root / ".opencontext" / "runs" / state.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        proposal_path = run_dir / "proposal.json"

        # Build a structured proposal from the task description
        proposal = {
            "run_id": state.run_id,
            "task": state.task,
            "created_at": datetime.now(UTC).isoformat(),
            "status": "draft",
            "summary": f"SDD proposal: {state.task}",
            "scope": {
                "root": str(state.root),
                "max_tokens": state.max_tokens,
            },
            "approach": {
                "method": "incremental",
                "style": "provider-neutral",
            },
            "artifacts": [
                {
                    "id": f"proposal-{state.run_id[:8]}",
                    "kind": "proposal",
                    "phase": "propose",
                }
            ],
        }
        proposal_path.write_text(json.dumps(proposal, indent=2), encoding="utf-8")

        gates: list[PhaseGate] = [
            ArtifactPersistedGate().evaluate(proposal_path),
        ]

        ledger = self._token_ledger("propose", 0)
        gates.append(TokenBudgetGate().evaluate(ledger))

        status = (
            GateStatus.FAILED
            if any(g.status == GateStatus.FAILED for g in gates)
            else GateStatus.PASSED
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
            metadata={"proposal_path": str(proposal_path)},
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

    context = {
        "task": getattr(state, "task", ""),
        "phase": phase,
        "run_id": getattr(state, "run_id", ""),
        "root": str(getattr(state, "root", "")),
        # Verified context pack rendered by the explore phase (empty if unavailable).
        "context": getattr(state, "context_pack", ""),
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

    ``content`` is the full intended file content after the edit (whole-file
    replacement / create). ``path`` is an absolute or root-relative path.
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
        return p

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
        return edits

    @staticmethod
    def _edit_targets(state: Any, edits: list[FileEdit]) -> list[Path]:
        """Resolve the on-disk targets the edits will write, for checkpointing."""
        executor = CodeEditExecutor(state.root)
        return [executor._resolve(e.path) for e in edits]

    def run(self, state: Any) -> PhaseResult:
        run_dir = state.root / ".opencontext" / "runs" / state.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        apply_manifest_path = run_dir / "apply-manifest.json"

        edits = self._collect_edits(state)
        changes: list[dict[str, Any]] = []
        apply_status = "planned"
        phase_status = GateStatus.PASSED
        error: str | None = None
        checkpoint = None
        diff_changes: list[dict[str, str]] = []

        if edits:
            # Snapshot exactly the files about to change BEFORE touching them, so
            # a post-apply rejection (or error) can restore them byte-for-byte.
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
            },
        )


class SpecPhase(HarnessPhase):
    """Spec phase: read proposal and produce structured spec with requirements and scenarios."""

    id = "spec"

    def run(self, state: Any) -> PhaseResult:
        run_dir = state.root / ".opencontext" / "runs" / state.run_id
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
        ]
        ledger = self._token_ledger("spec", 0)
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
        run_dir = state.root / ".opencontext" / "runs" / state.run_id
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

        spec_content = spec_path.read_text(encoding="utf-8")
        task = state.task

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
        ]
        ledger = self._token_ledger("design", 0)
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
        run_dir = state.root / ".opencontext" / "runs" / state.run_id
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

        design_content = design_path.read_text(encoding="utf-8")
        task = state.task

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
                # Default task if no files extracted
                tasks.append(
                    {
                        "id": "task-1",
                        "description": f"Implement feature: {task}",
                        "file_paths": ["harness/gates.py", "tests/harness/test_harness_gates.py"],
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
        ]
        ledger = self._token_ledger("tasks", 0)
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
        run_dir = state.root / ".opencontext" / "runs" / state.run_id
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
        verify_report = {
            "run_id": state.run_id,
            "task": state.task,
            "created_at": datetime.now(UTC).isoformat(),
            "test_result": test_result,
            "summary": (
                "All checks passed"
                if test_result["exit_code"] == 0
                else f"Tests failed ({test_result['exit_code']})"
            ),
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

        # Mutation testing hook (additive, non-breaking)
        try:
            from opencontext_core.config import load_config_or_defaults

            _cfg = load_config_or_defaults(state.root / "opencontext.yaml")
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
        args = [sys.executable, "-m", "pytest", "-q", "--tb=short"]
        if targets:
            args += targets
        else:
            args.append(str(root))
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
        run_dir = state.root / ".opencontext" / "runs" / state.run_id
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
        run_dir = state.root / ".opencontext" / "runs" / state.run_id
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
        run_dir = state.root / ".opencontext" / "runs" / state.run_id
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
            "rules_file": str(state.root / ".opencontext" / "rules.yaml"),
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
        rules_path = root / ".opencontext" / "rules.yaml"
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
