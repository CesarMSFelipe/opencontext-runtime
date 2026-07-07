"""OCFlowRunner — drives OC Flow under Runtime governance (PR-007, FLOW-1, FLOW-2,
FLOW-3, FLOW-15, FLOW-16, FLOW-CONV §6).

The runner walks the declarative graph from ``start_node``, dispatches each node
handler, enforces the per-node exit conditions and token budgets, resolves the next
node from the typed outcome, and persists artifacts/events/decision receipts under
the run's artifact tree. It consults an advisory Runtime Brain (PR-000.1) for the
next-node recommendation — advisory only; the deterministic graph governs (doc 59
§Brain restrictions). It also resolves ``--workflow auto`` to OC Flow for localized
tasks and recommends escalation to SDD as risk/scope grows.

Layering (doc 58): L9 composing L1 ids, L2 stores, L8 brain (via port), L6 registries
— all downward.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from opencontext_core.agents.executor import ApplyEdit
from opencontext_core.context.planning.workflow_selector import (
    WorkflowSelection,
)
from opencontext_core.context.planning.workflow_selector import (
    select_workflow as _shared_select_workflow,
)
from opencontext_core.oc_flow.budgets import (
    BudgetGuard,
    resolve_max_attempts,
)
from opencontext_core.oc_flow.completion import (
    CompletionStatus,
    completion_reason,
    functional_change_expected,
    mutation_required,
    resolve_completion,
    verification_required,
)
from opencontext_core.oc_flow.definition import oc_flow_definition, resolve_next_node
from opencontext_core.oc_flow.models import (
    DiagnosisAttempt,
    InspectionReport,
    Lane,
    NodeOutcome,
    TaskContract,
)
from opencontext_core.oc_flow.nodes import (
    NODE_HANDLERS,
    DeterministicNodeExecutor,
    NodeExecutor,
    OCFlowContext,
    OCFlowError,
    can_exit,
)
from opencontext_core.oc_flow.personas import persona_id_for_oc_flow_node
from opencontext_core.oc_flow.run_bundle import (
    enforce_gates,
    evaluate_oc_flow_gates,
    memory_block,
    write_run_bundle,
)
from opencontext_core.paths import StorageMode, resolve_storage_path, resolve_workspace_path
from opencontext_core.runtime.brain import NullRuntimeBrain, RuntimeBrainPort
from opencontext_core.runtime.decisions import (
    DecisionLog,
    RuntimeDecision,
    summarize_decision_log,
)
from opencontext_core.runtime.ids import new_run_id, new_session_id
from opencontext_core.tdd.red_green import (
    TDD_NOT_APPLICABLE,
    TDD_TEST_ONLY_EDIT,
    VIOLATION_REASONS,
    TddEvidence,
    capture_test_run,
    evaluate_strict,
    is_test_only_change,
    regression_command,
    runner_available,
)

# Safety cap on total node steps (the diagnosis attempt budget already bounds the
# loop; this guards against any pathological graph cycle).
_MAX_STEPS = 50

# Event family per node event (doc 59 §Event hierarchy).
_NODE_EVENT_FAMILY = "workflow"


@dataclass
class OCFlowRunResult:
    """The outcome of an OC Flow run."""

    run_id: str
    session_id: str
    # completed | blocked | needs_executor | needs_provider | needs_user_edit | escalated
    status: str
    final_node: str
    visited: list[str] = field(default_factory=list)
    artifacts_dir: Path | None = None
    total_tokens: int = 0
    diagnosis_attempts: int = 0
    escalated: bool = False
    decisions: list[dict[str, Any]] = field(default_factory=list)
    # B1 / AVH-011: the honest terminal status, why, and the workflow-selection
    # receipt (B6). ``graph_status`` keeps the raw traversal verdict for tooling.
    graph_status: str = "completed"
    completion_reason: str = ""
    mutation_required: bool = False
    workflow_selection: dict[str, Any] = field(default_factory=dict)
    verified_by: list[str] = field(default_factory=list)
    verification_outcome: str = "not_run"
    # Contract surface (RUN_STATE_CONTRACT / TDD_STRICT_CONTRACT): the canonical
    # final state, its documented exit code, and the RED/GREEN evidence block.
    canonical_status: str = ""
    exit_code: int = 0
    tdd: dict[str, Any] | None = None


# --------------------------------------------------------------------- workflow selector
def select_workflow(task: str) -> str:
    """Resolve ``--workflow auto`` to ``oc-flow`` or ``sdd`` (FLOW-CONV, B6).

    Delegates to the ONE shared selector (``context.planning.workflow_selector``) so
    ``run --workflow auto`` and ``simulate`` cannot disagree (AVH-013). No routing
    policy lives here any more.
    """
    return _shared_select_workflow(task).workflow


def should_escalate_to_sdd(contract: TaskContract, *, max_changed_areas: int = 5) -> bool:
    """Recommend switching to SDD when scope/risk outgrows OC Flow (book §23)."""
    if len(contract.changed_areas) > max_changed_areas:
        return True
    risk = {r.lower() for r in contract.risk_flags}
    high_risk = {"public_api", "schema", "architecture", "security", "migration", "breaking_change"}
    return bool(risk & high_risk)


def _green_evidence_from_inspection(inspection: InspectionReport | None) -> Any:
    """Project the inspection's targeted-tests gate onto GREEN test-run evidence.

    Local inspection already executed the post-mutation test command and recorded
    its command/exit_code/captured_at on the gate — no re-run needed.
    """
    from opencontext_core.tdd.red_green import TddRunEvidence

    if inspection is None:
        return None
    for gate in inspection.gate_results:
        if gate.get("id") == "targeted_tests" and "exit_code" in gate:
            return TddRunEvidence(
                command=str(gate.get("command", "")),
                exit_code=int(gate["exit_code"]),
                failure_summary=(
                    str(gate.get("message", "")) if gate.get("exit_code") != 0 else ""
                ),
                captured_at=str(gate.get("captured_at", "")),
            )
    return None


@dataclass(frozen=True)
class ResolvedTestCommand:
    """A verification command plus the source that chose it (evidence field)."""

    command: list[str] | None
    source: str  # "configured" | "project_venv" | "runtime"


def _configured_test_command(root: Path) -> list[str] | None:
    """The explicit ``workflow_defaults.test_command`` from harness.yaml, if any."""
    try:
        from opencontext_core.harness.config import HarnessConfig

        harness_path = resolve_workspace_path(root, StorageMode.local) / "harness.yaml"
        return HarnessConfig.from_yaml_file(harness_path).test_command
    except Exception:
        return None


def _pytest_importable(venv: Path, python: Path) -> bool:
    """Best-effort check that ``python`` (in ``venv``) can import pytest.

    Structural markers first (cheap, and hermetic for fixture layouts), then a
    real import probe as the honest fallback.
    """
    if (venv / "bin" / "pytest").is_file() or (venv / "Scripts" / "pytest.exe").is_file():
        return True
    if (venv / "Lib" / "site-packages" / "pytest" / "__init__.py").is_file():
        return True
    if any(venv.glob("lib/python*/site-packages/pytest/__init__.py")):
        return True
    import subprocess

    try:
        probe = subprocess.run(
            [str(python), "-c", "import pytest"], capture_output=True, timeout=15
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0


def _project_venv_python(root: Path) -> Path | None:
    """The project's own venv interpreter (with pytest importable), or ``None``."""
    for venv_name in (".venv", "venv"):
        venv = root / venv_name
        for python in (venv / "bin" / "python", venv / "Scripts" / "python.exe"):
            if python.is_file() and _pytest_importable(venv, python):
                return python
    return None


def _discover_test_files(root: Path) -> list[str]:
    tests = sorted(
        p.relative_to(root)
        for pattern in ("test_*.py", "*_test.py")
        for p in root.rglob(pattern)
        if ".opencontext" not in p.parts
    )
    # NOTE: caps at 10 to avoid running the full suite; pass explicit test_command for large repos.
    return [str(p) for p in tests[:10]]


def resolve_test_command(root: Path) -> ResolvedTestCommand:
    """Resolve the verification command for ``root`` with its provenance.

    Order: (1) explicit ``workflow_defaults.test_command`` (harness.yaml) —
    "configured"; (2) the PROJECT's own interpreter (``.venv``/``venv`` with
    pytest importable) — "project_venv"; (3) the current ``sys.executable`` —
    "runtime" (the existing ``runner_available`` preflight still applies).
    """
    configured = _configured_test_command(root)
    if configured:
        return ResolvedTestCommand(command=list(configured), source="configured")
    tests = _discover_test_files(root)
    if not tests:
        return ResolvedTestCommand(command=None, source="runtime")
    venv_python = _project_venv_python(root)
    if venv_python is not None:
        return ResolvedTestCommand(
            command=[str(venv_python), "-m", "pytest", "-q", *tests], source="project_venv"
        )
    return ResolvedTestCommand(
        command=[sys.executable, "-m", "pytest", "-q", *tests], source="runtime"
    )


def _discover_test_command(root: Path) -> list[str] | None:
    """Small pytest discovery for test-fix tasks (see :func:`resolve_test_command`)."""
    return resolve_test_command(root).command


# ------------------------------------------------------------------------------- runner
class OCFlowRunner:
    """Executes the OC Flow workflow definition under Runtime governance."""

    def __init__(
        self,
        root: Path,
        *,
        executor: NodeExecutor | None = None,
        brain: RuntimeBrainPort | None = None,
        cache: Any | None = None,
        enabled: bool = True,
        context_engine_enabled: bool | None = None,
        kg_v2_enabled: bool | None = None,
        memory_store: Any | None = None,
    ) -> None:
        self.root = Path(root)
        self.definition = oc_flow_definition()
        self.executor = executor or DeterministicNodeExecutor()
        # Advisory-only Brain (flag-gated): defaults to the inert NullRuntimeBrain.
        self.brain: RuntimeBrainPort = brain or NullRuntimeBrain()
        self.brain_advisory = brain is not None
        self.cache = cache
        self.enabled = enabled
        # VDM-004 seam wiring: resolve the PR-010 ContextEngine (context_engine) and
        # PR-008 KG v2 (kg_v2) gather-path flags. An explicit ctor value wins (cli /
        # tests); otherwise they come from the project config at ``root`` so flipping
        # ``runtime.context_engine_enabled`` / ``runtime.kg_v2_enabled`` activates the
        # vNext gather path with no code change. Default config = legacy (both off).
        if context_engine_enabled is None or kg_v2_enabled is None:
            runtime_cfg = self._load_runtime_config()
            if context_engine_enabled is None:
                context_engine_enabled = bool(getattr(runtime_cfg, "context_engine_enabled", False))
            if kg_v2_enabled is None:
                kg_v2_enabled = bool(getattr(runtime_cfg, "kg_v2_enabled", False))
        self._context_engine_enabled = bool(context_engine_enabled)
        self._kg_v2_enabled = bool(kg_v2_enabled)
        # RUN_STATE_CONTRACT needs_configuration pre-gate (OC-004): resolve the
        # config-load error ONCE. When the workspace declares an opencontext.yaml
        # that cannot load, the run terminates as canonical needs_configuration
        # (exit 3) instead of crashing or silently degrading to defaults.
        self._config_error_detail = self._resolve_config_error()
        # Always locate the KG index regardless of the kg_v2_enabled flag. When the
        # index is present and no seed paths are given, node_gather_context uses the
        # path for opportunistic KG grounding even without kg_v2_enabled=True. On an
        # unindexed project _resolve_graph_db_path() returns None so no seeding occurs.
        # An invalid config cannot resolve a storage path — skip (the pre-gate fires).
        self._graph_db_path = (
            None if self._config_error_detail is not None else self._resolve_graph_db_path()
        )
        # Memory + compression parity (SDD harness/context substrate): resolve the
        # agent memory store and the compression config from the project config so
        # gather_context reads memory / compresses oversized content and
        # consolidation persists the memory delta through the harvester/harness.
        # An injected store (tests/hosts) wins over config resolution.
        self._memory_enabled = False
        self._memory_harvest_enabled = False
        self._memory_v2_enabled = False
        self._memory_approval_required = False
        self._memory_store: Any | None = memory_store
        self._compression_enabled = False
        self._compression_config: Any | None = None
        self._resolve_memory_and_compression()
        self._tdd_mode = self._resolve_tdd_mode()

    def _resolve_tdd_mode(self) -> str:
        """Resolve the strict-TDD posture for this run root.

        Mirrors the harness resolution: OPENCONTEXT_TDD_MODE env wins, then the
        installed ``.opencontext/harness.yaml`` (``workflow_defaults.tdd_mode`` —
        the SAME file HarnessRunner reads), then the opencontext.yaml
        ``harness.tdd_mode``. Defaults to ``ask`` so the RED-first pre-check stays
        off unless explicitly opted into strict TDD.
        """
        import os

        env = os.environ.get("OPENCONTEXT_TDD_MODE")
        if env in ("strict", "ask", "off"):
            return env
        try:
            import yaml

            harness_path = resolve_workspace_path(self.root, StorageMode.local) / "harness.yaml"
            if harness_path.is_file():
                data = yaml.safe_load(harness_path.read_text(encoding="utf-8")) or {}
                if isinstance(data, dict):
                    mode = (data.get("workflow_defaults") or {}).get("tdd_mode")
                    if mode in ("strict", "ask", "off"):
                        return str(mode)
        except Exception:
            pass  # harness.yaml is advisory here; fall through to opencontext.yaml
        try:
            from opencontext_core.config import load_config_or_defaults

            cfg = load_config_or_defaults(self.root / "opencontext.yaml", auto_detect=False)
            harness_cfg = getattr(cfg, "harness", None)
            mode = getattr(harness_cfg, "tdd_mode", "ask") if harness_cfg is not None else "ask"
            return str(mode) if mode in ("strict", "ask", "off") else "ask"
        except Exception:
            return "ask"

    # -- config / kg resolution ----------------------------------------------
    def _resolve_config_error(self) -> str | None:
        """The config-load failure for an EXISTING config file, or ``None``.

        A missing config is NOT an error — zero-config defaults apply and the run
        proceeds (needs_executor semantics stay intact). An opencontext.yaml that
        exists but cannot load (unparseable YAML, schema-invalid section) means
        required configuration is invalid: the run must terminate as canonical
        ``needs_configuration`` (RUN_STATE_CONTRACT), naming what to fix.
        """
        try:
            from opencontext_core.config import load_config_or_defaults
            from opencontext_core.config_resolver import resolve_config_path

            path = resolve_config_path(self.root)
            if not path.exists():
                return None
            load_config_or_defaults(path, auto_detect=False)
            return None
        except Exception as exc:
            return str(exc)

    def _load_runtime_config(self) -> Any:
        """Load the project's RuntimeMigration flags from ``<root>/opencontext.yaml``.

        Config is advisory here: a missing or invalid config yields built-in defaults
        (every migration flag legacy-off via ``getattr(..., False)``), so flag-off
        behaviour is byte-identical to before this seam was wired.
        """
        try:
            from opencontext_core.config import load_config_or_defaults
            from opencontext_core.config_resolver import resolve_config_path

            config = load_config_or_defaults(resolve_config_path(self.root), auto_detect=False)
            return config.runtime
        except Exception:  # pragma: no cover - config is advisory; default to legacy.
            return None

    def _resolve_memory_and_compression(self) -> None:
        """Resolve memory flags/store + compression config from the project config.

        Mirrors the SDD harness runner: the store MUST resolve to the same DB
        (path + provider) the runtime's recall path reads, so it comes from
        ``BackendFactory.create_memory_store`` honoring ``memory.provider`` and the
        storage mode. Best-effort: any failure degrades to no-memory /
        no-compression and the nodes record the omission or no-op reason honestly.
        """
        try:
            from opencontext_core.config import load_config_or_defaults
            from opencontext_core.config_resolver import resolve_config_path

            config = load_config_or_defaults(resolve_config_path(self.root), auto_detect=False)
        except Exception:  # config is advisory; run without memory/compression
            return
        memory_cfg = getattr(config, "memory", None)
        self._memory_enabled = bool(getattr(memory_cfg, "enabled", False))
        self._memory_harvest_enabled = bool(getattr(memory_cfg, "harvest_after_run", False))
        # MEMORY_CONTRACT rule 4: whether newly harvested memory awaits approval
        # before use — reported per run as memory.requires_approval.
        self._memory_approval_required = bool(getattr(memory_cfg, "approval_required", False))
        self._memory_v2_enabled = bool(
            getattr(getattr(config, "runtime", None), "memory_v2_enabled", False)
        )
        compression_cfg = getattr(getattr(config, "context", None), "compression", None)
        self._compression_enabled = bool(getattr(compression_cfg, "enabled", False))
        self._compression_config = compression_cfg
        if self._memory_store is None and self._memory_enabled:
            try:
                from opencontext_core.backends.factory import BackendFactory

                storage_path = resolve_storage_path(
                    self.root,
                    config.storage.mode,
                    getattr(config.storage, "custom_path", None),
                )
                storage_path.mkdir(parents=True, exist_ok=True)
                self._memory_store = BackendFactory.create_memory_store(config, storage_path)
            except Exception:  # store is optional — gather/consolidation degrade
                self._memory_store = None

    def _resolve_graph_db_path(self) -> Path | None:
        """Locate the project's KG v2 index under ``root``, or None when unindexed.

        ``kg_first_subgraph`` returns None for a missing DB, so kg_v2 stays active but
        non-fatal on an unindexed project (the gather falls back to the legacy path).
        """
        from opencontext_core.config_resolver import resolve_active_storage_file

        for name in ("context_graph.db", "codegraph.db"):
            candidate = resolve_active_storage_file(self.root, name)
            if candidate.exists():
                return candidate
        return None

    # -- paths ----------------------------------------------------------------
    def _run_dir(self, session_id: str, run_id: str) -> Path:
        from opencontext_core.paths.execution_state import sessions_root

        return sessions_root(self.root) / session_id / "runs" / run_id

    def _locate_run_dir(self, session_id: str, run_id: str) -> Path:
        """Find a persisted run dir: active tree first, legacy in-repo fallback.

        Readers (resume) must still see runs persisted before execution state
        moved to user-mode storage. Returns the active-mode path when the run
        exists nowhere, so error messages name the canonical location.
        """
        from opencontext_core.paths.execution_state import execution_read_roots

        for sessions in execution_read_roots(self.root, "sessions"):
            candidate = sessions / session_id / "runs" / run_id
            if candidate.is_dir():
                return candidate
        return self._run_dir(session_id, run_id)

    def _artifacts_dir(self, session_id: str, run_id: str) -> Path:
        return self._run_dir(session_id, run_id) / "artifacts" / "oc-flow"

    # -- run ------------------------------------------------------------------
    def run(
        self,
        task: str,
        *,
        lane: Lane | str = Lane.FAST,
        profile: str | None = "balanced",
        seed_paths: list[str] | None = None,
        requested_edits: list[ApplyEdit] | None = None,
        run_external_inspection: bool = False,
        test_command: list[str] | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
    ) -> OCFlowRunResult:
        """Run OC Flow for ``task``; an interrupt yields canonical ``cancelled``.

        Thin cancellation boundary over :meth:`_run_governed` (RUN_STATE_CONTRACT):
        a KeyboardInterrupt/SIGINT mid-run is finalized as status ``cancelled``
        (exit code 1) and, when the run dir already exists, run.json is persisted
        with the cancelled state — best-effort, never corrupting partial artifacts.
        """
        session_id = session_id or new_session_id()
        run_id = run_id or new_run_id()
        try:
            return self._run_governed(
                task,
                lane=lane,
                profile=profile,
                seed_paths=seed_paths,
                requested_edits=requested_edits,
                run_external_inspection=run_external_inspection,
                test_command=test_command,
                session_id=session_id,
                run_id=run_id,
            )
        except KeyboardInterrupt:
            return self._finalize_cancelled(task, session_id=session_id, run_id=run_id)

    def _finalize_cancelled(self, task: str, *, session_id: str, run_id: str) -> OCFlowRunResult:
        """Signal-safe cancellation finalizer (RUN_STATE_CONTRACT ``cancelled``)."""
        from opencontext_core.models.canonical_status import exit_code_for_run

        exit_code = exit_code_for_run("cancelled")
        reason = "run interrupted (SIGINT/KeyboardInterrupt)"
        run_dir = self._run_dir(session_id, run_id)
        if run_dir.is_dir():
            # Best-effort persistence — a failure here must never mask the
            # cancellation itself.
            try:
                finished_at = datetime.now(tz=UTC).isoformat()
                manifest_path = run_dir / "run.json"
                manifest = _load(manifest_path)
                if not isinstance(manifest, dict):
                    manifest = {
                        "schema_version": "opencontext.oc_flow.run_manifest.v1",
                        "run_id": run_id,
                        "session_id": session_id,
                        "workflow": "oc-flow",
                        "task": task,
                        "created_at": finished_at,
                    }
                manifest.update(
                    {
                        "status": "cancelled",
                        "canonical_status": "cancelled",
                        "exit_code": exit_code,
                        "completion_reason": reason,
                        "finished_at": finished_at,
                    }
                )
                _dump(manifest_path, manifest)
                state = _load(run_dir / "state.json")
                if isinstance(state, dict):
                    state["status"] = "cancelled"
                    _dump(run_dir / "state.json", state)
            except Exception:
                pass
        return OCFlowRunResult(
            run_id=run_id,
            session_id=session_id,
            status="cancelled",
            final_node="cancelled",
            completion_reason=reason,
            canonical_status="cancelled",
            exit_code=exit_code,
        )

    def _finalize_needs_configuration(
        self, task: str, *, session_id: str, run_id: str
    ) -> OCFlowRunResult:
        """Terminate a run whose required configuration is invalid (OC-004).

        Persists the run.json/gates.json evidence bundle with a failed
        ``config_valid`` gate and returns the canonical ``needs_configuration``
        result (exit 3), with a reason naming the configuration to fix.
        """
        from opencontext_core.models.canonical_status import exit_code_for_run

        detail = self._config_error_detail or "project configuration failed to load"
        reason = (
            f"required configuration is invalid: {detail} — fix the named file/keys "
            "(see `opencontext config doctor`) or remove the file to run with defaults"
        )
        status = "needs_configuration"
        exit_code = exit_code_for_run(status)
        finished_at = datetime.now(tz=UTC).isoformat()
        manifest = {
            "schema_version": "opencontext.oc_flow.run_manifest.v1",
            "run_id": run_id,
            "session_id": session_id,
            "workflow": "oc-flow",
            "task": task,
            "status": status,
            "canonical_status": status,
            "exit_code": exit_code,
            "created_at": finished_at,
            "started_at": finished_at,
            "finished_at": finished_at,
            "completion_reason": reason,
            "mutation_required": mutation_required(task),
            "changed_files": [],
            "verification": {
                "executed": False,
                "commands": [],
                "outcome": "not_run",
                "passed": False,
                "runner_source": None,
            },
            "tdd": None,
            "memory": memory_block([]),
        }
        gates = evaluate_oc_flow_gates(
            workspace_valid=self.root.is_dir(),
            config_valid=False,
            context_pack_created=None,
            executor_available=None,
            tdd_red_proven_if_strict=None,
            mutation_performed_if_required=None,
            verification_executed=None,
            verification_passed=None,
        )
        write_run_bundle(
            self._run_dir(session_id, run_id),
            manifest=manifest,
            gates=gates,
            verification={
                "run_id": run_id,
                "commands": [],
                "outcome": "not_run",
                "exit_code": None,
                "runner_source": None,
                "summary": reason,
            },
        )
        return OCFlowRunResult(
            run_id=run_id,
            session_id=session_id,
            status=status,
            final_node="init",
            graph_status="not_run",
            completion_reason=reason,
            mutation_required=mutation_required(task),
            canonical_status=status,
            exit_code=exit_code,
        )

    def _run_governed(
        self,
        task: str,
        *,
        lane: Lane | str = Lane.FAST,
        profile: str | None = "balanced",
        seed_paths: list[str] | None = None,
        requested_edits: list[ApplyEdit] | None = None,
        run_external_inspection: bool = False,
        test_command: list[str] | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
    ) -> OCFlowRunResult:
        """Run OC Flow end to end for ``task`` (FLOW-16, book §25)."""
        if not self.enabled:
            raise OCFlowError("OC Flow is disabled (set runtime.oc_flow_enabled=true)")

        # Defense in depth: redact secrets in the task at the flow boundary so any
        # caller (MCP, API, direct) that did not pre-redact still never persists a
        # raw token into run artifacts or the provider-bound context envelope. The
        # prose pass also catches inline NAME=value assignments (AC-028).
        if task:
            from opencontext_core.safety.redaction import redact_prose_secrets

            task = redact_prose_secrets(task)

        lane_enum = Lane(str(lane))
        session_id = session_id or new_session_id()
        run_id = run_id or new_run_id()

        # needs_configuration pre-gate (OC-004 / RUN_STATE_CONTRACT): an existing
        # config that cannot load terminates the run BEFORE the graph walks.
        if self._config_error_detail is not None:
            return self._finalize_needs_configuration(task, session_id=session_id, run_id=run_id)

        artifacts_dir = self._artifacts_dir(session_id, run_id)
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        # If a caller passed concrete edits, drive them through the deterministic
        # executor so a model-free run can still apply a real surgical change.
        executor = self.executor
        if requested_edits is not None and isinstance(executor, DeterministicNodeExecutor):
            executor = DeterministicNodeExecutor(requested_edits=requested_edits)

        started_at = datetime.now(tz=UTC).isoformat()
        # B1 / AVH-011: classify whether this task implies a mutation; threaded into
        # the inspection scope gate and the post-graph completion gate.
        mut_required = mutation_required(task)
        verify_required = verification_required(task)
        strict_tdd = self._tdd_mode == "strict"
        if strict_tdd and mut_required:
            # TDD_STRICT_CONTRACT: a strict mutation run must execute tests, so
            # verification is required regardless of the task wording.
            verify_required = True
        # Evidence provenance: which source chose the verification command
        # (an explicitly passed command counts as configured).
        runner_source: str | None = "configured" if test_command is not None else None
        if verify_required and test_command is None:
            resolved_command = resolve_test_command(self.root)
            test_command = resolved_command.command
            runner_source = resolved_command.source if test_command else None
        run_external_inspection = run_external_inspection or bool(test_command)

        # RED evidence (TDD_STRICT_CONTRACT): run the relevant tests BEFORE any
        # mutation whenever a test command exists for a mutation task. Strict mode
        # additionally enforces the contract table (no runner / already-green test
        # -> violation); other modes capture evidence only.
        tdd_evidence = TddEvidence(mode=self._tdd_mode)
        runner_ok = True
        if mut_required and test_command:
            # Preflight (TDD_STRICT_CONTRACT): an unavailable runner can never
            # prove RED — "No module named pytest" exiting 1 is an environment
            # error, not a failing test. Strict mode routes an unavailable
            # runner to the blocked/no-test-runner path instead of capturing a
            # spurious non-zero exit as evidence.
            runner_ok = runner_available(test_command)
            if runner_ok:
                tdd_evidence.red = capture_test_run(test_command, self.root)
        if strict_tdd:
            tdd_evidence.violation = evaluate_strict(
                mutation_required=mut_required,
                has_test_command=bool(test_command) and runner_ok,
                red=tdd_evidence.red,
            )
        if strict_tdd and not mut_required:
            # TDD policy: a documentation/read-only task has no applicable
            # RED/GREEN cycle — record an explicit not_applicable result with a
            # justification instead of a silent empty strict block. Evidence is
            # never fabricated for such tasks.
            tdd_evidence.mode_result = TDD_NOT_APPLICABLE
            tdd_evidence.justification = (
                "strict TDD is not applicable: the task is read-only/documentation "
                "and requires no functional change, so no RED/GREEN cycle was run"
            )
        # C16: compute once, use for both ctx and the retry_policy decision below.
        _max_attempts_resolved = resolve_max_attempts(profile=profile, lane=lane_enum)
        ctx = OCFlowContext(
            root=self.root,
            artifacts_dir=artifacts_dir,
            task=task,
            lane=lane_enum,
            profile=profile,
            executor=executor,
            max_attempts=_max_attempts_resolved,
            seed_paths=seed_paths or [],
            cache=self.cache,
            run_external_inspection=run_external_inspection,
            test_command=test_command,
            mutation_required=mut_required,
            # VDM-004: vNext gather-path flags reach the node handlers here. With both
            # off (default config) node_gather_context runs the legacy executor path.
            context_engine_enabled=self._context_engine_enabled,
            kg_v2_enabled=self._kg_v2_enabled,
            graph_db_path=self._graph_db_path,
            # Memory + compression parity: gather_context folds memory recall and
            # compresses oversized content; consolidation persists the memory delta
            # through the harvester/harness with this run's provenance.
            memory_enabled=self._memory_enabled,
            memory_store=self._memory_store,
            memory_harvest_enabled=self._memory_harvest_enabled,
            memory_v2_enabled=self._memory_v2_enabled,
            memory_approval_required=self._memory_approval_required,
            tdd_mode=self._tdd_mode,
            tdd_red_exit_code=(tdd_evidence.red.exit_code if tdd_evidence.red else None),
            run_id=run_id,
            compression_enabled=self._compression_enabled,
            compression_config=self._compression_config,
        )

        # B6 / AVH-013: the explainable workflow-selection receipt (same shared
        # selector `run --workflow auto` and `simulate` consume).
        selection = _shared_select_workflow(task)

        decisions = DecisionLog()
        events: list[dict[str, Any]] = []
        guard = BudgetGuard()
        visited: list[str] = []

        node = self.definition.start_node
        status = "completed"
        steps = 0
        self._emit_event(
            events,
            "workflow.selected",
            node,
            {
                "workflow": "oc-flow",
                "lane": lane_enum.value,
                "selection_reason": selection.reason,
                "selection_signals": selection.signals,
                "mutation_required": mut_required,
            },
        )

        # C16 (product-closure-r13): emit RuntimeDecision records for the real
        # selection points made by this run.  Only record decisions for selection
        # points that ACTUALLY EXIST in OC Flow today (book §Brain restrictions):
        #   workflow, context_strategy, provider, execution_profile, retry_policy.
        #   NOT emitted (no real selection): persona (deterministic lookup),
        #   skill_bundle (not in OC Flow runner today).
        decisions.append(
            RuntimeDecision(
                kind="workflow",
                chosen=selection.workflow,
                reason=selection.reason,
                alternatives=["sdd"] if selection.workflow == "oc-flow" else ["oc-flow"],
                confidence=0.9,
                inputs={"signals": list(selection.signals), "lane": lane_enum.value},
            )
        )
        _context_strategy = (
            "context_engine"
            if self._context_engine_enabled
            else ("kg_v2" if self._kg_v2_enabled else "legacy")
        )
        decisions.append(
            RuntimeDecision(
                kind="context_strategy",
                chosen=_context_strategy,
                reason=(
                    "context_engine_enabled flag"
                    if self._context_engine_enabled
                    else ("kg_v2_enabled flag" if self._kg_v2_enabled else "default legacy gather")
                ),
                alternatives=(
                    ["kg_v2", "legacy"]
                    if self._context_engine_enabled
                    else (
                        ["context_engine", "legacy"]
                        if self._kg_v2_enabled
                        else ["context_engine", "kg_v2"]
                    )
                ),
                confidence=1.0,
                inputs={
                    "context_engine_enabled": self._context_engine_enabled,
                    "kg_v2_enabled": self._kg_v2_enabled,
                },
            )
        )
        _provider_chosen = (
            "deterministic" if not bool(getattr(executor, "provider_available", False)) else "model"
        )
        decisions.append(
            RuntimeDecision(
                kind="provider",
                chosen=_provider_chosen,
                reason=(
                    "no model provider configured; deterministic executor active"
                    if _provider_chosen == "deterministic"
                    else "model provider available"
                ),
                alternatives=(
                    ["model"] if _provider_chosen == "deterministic" else ["deterministic"]
                ),
                confidence=1.0,
                inputs={"provider_available": _provider_chosen != "deterministic"},
            )
        )
        decisions.append(
            RuntimeDecision(
                kind="execution_profile",
                chosen=profile or "balanced",
                reason=f"profile='{profile or 'balanced'}' passed by caller",
                confidence=1.0,
                inputs={"lane": lane_enum.value},
            )
        )
        decisions.append(
            RuntimeDecision(
                kind="retry_policy",
                chosen=str(_max_attempts_resolved),
                reason=(
                    f"resolve_max_attempts(profile={profile!r}, lane={lane_enum.value!r})"
                    f" → {_max_attempts_resolved}"
                ),
                confidence=1.0,
                inputs={
                    "profile": profile,
                    "lane": lane_enum.value,
                    "max_attempts": _max_attempts_resolved,
                },
            )
        )

        # TDD strict violation: refuse BEFORE any node runs — the contract forbids
        # mutating without proven RED, so the graph never walks (exit-6 path).
        if tdd_evidence.violation is not None:
            ctx.block_reason = VIOLATION_REASONS.get(tdd_evidence.violation, tdd_evidence.violation)
            self._emit_event(
                events,
                "tdd.violation",
                node,
                {"violation": tdd_evidence.violation, "mode": self._tdd_mode},
            )

        while tdd_evidence.violation is None and node not in self.definition.terminal_nodes:
            steps += 1
            if steps > _MAX_STEPS:
                status = "failed"
                break
            handler = NODE_HANDLERS.get(node)
            if handler is None:
                raise OCFlowError(f"no handler for node {node!r}")

            self._emit_event(events, "node.started", node, {})
            result = handler(ctx)
            visited.append(node)
            guard.charge(node, result.llm_tokens)
            self._emit_event(
                events,
                "node.completed",
                node,
                {"outcome": result.outcome.value, "tokens": result.llm_tokens},
            )

            # C16: after consolidation, emit the memory_promotion decision so
            # decisions.json captures the PromotionPolicyV2 verdict.
            if node == "consolidation":
                verdict_str = str(result.outputs.get("promotion_verdict", "not_promoted"))
                decisions.append(
                    RuntimeDecision(
                        kind="memory_promotion",
                        chosen=verdict_str,
                        reason=(
                            "PromotionPolicyV2 evaluated composite score from run signals "
                            "(inspection outcome + changed-file count)"
                        ),
                        confidence=0.8,
                        inputs={
                            "changed_files": len(ctx.changed_files),
                            "inspection_outcome": (
                                ctx.inspection.outcome if ctx.inspection else "not_run"
                            ),
                        },
                    )
                )

            # Exit-condition guard (book §7-§11): refuse to advance until met.
            if not can_exit(node, ctx):
                raise OCFlowError(f"exit conditions not satisfied for node {node!r}")

            # Terminal outcomes without graph edges (RUN_STATE_CONTRACT):
            # gather_context reporting NEEDS_CONTEXT means re-gathering cannot help
            # (gathering itself found nothing) — the run ends needs_context; a
            # POLICY_BLOCKED refusal from the repair guard ends the walk so the
            # policy outcome surfaces as canonical needs_approval, never `failed`.
            if node == "gather_context" and result.outcome is NodeOutcome.NEEDS_CONTEXT:
                status = "needs_context"
                break
            if result.outcome is NodeOutcome.POLICY_BLOCKED:
                status = "policy_blocked"
                break

            target = self._next_node(node, result.outcome, ctx, decisions, guard, events)
            if target is None:
                status = "failed"
                break
            if target == "escalation":
                status = "escalated"
            node = target

        # Terminal handling. The graph reaching its `completed` node is NOT proof a
        # mutation task was done — the completion gate (B1/ADR-A1) maps the raw graph
        # verdict onto an honest status; a no-op mutation can never report `completed`.
        final_node = node
        provider_available = bool(getattr(executor, "provider_available", False))
        if tdd_evidence.violation is not None:
            # Strict-TDD refusal: the graph never walked; the honest terminal state
            # is the dedicated violation marker (canonical `blocked`, exit 6).
            graph_status = "not_run"
            status = "tdd_violation"
            reason = ctx.block_reason or tdd_evidence.violation
        elif status in ("needs_context", "policy_blocked"):
            # Terminal states produced by the graph walk itself (RUN_STATE_CONTRACT):
            # insufficient context / policy-gate block. The completion gate would
            # misreport them as needs_executor/blocked, so they pass through.
            graph_status = status
            reason = ctx.block_reason or (
                "the flow could not build sufficient context for the task"
                if status == "needs_context"
                else "the policy gate blocked this run before it could proceed"
            )
        else:
            graph_status = status
            completion = resolve_completion(
                graph_status,
                ctx,
                mutation_required=mut_required,
                provider_available=provider_available,
                verification_required=verify_required,
            )
            status = completion.value
            reason = (
                ctx.block_reason
                if completion is not CompletionStatus.completed and ctx.block_reason
                else completion_reason(completion, mutation_required=mut_required)
            )
            if ctx.policy_approval_required and completion is not CompletionStatus.completed:
                # DOC1 §10 / RUN_STATE_CONTRACT: the policy gate demands human
                # approval before the write — surface the policy outcome as the
                # terminal state (canonical ``needs_approval``, exit 4).
                status = "policy_blocked"
                reason = ctx.block_reason or (
                    "policy requires human approval before edits can be applied"
                )

        # GREEN evidence (TDD_STRICT_CONTRACT): the post-mutation targeted-tests run
        # already executed inside local inspection — reuse its recorded command/exit.
        green = _green_evidence_from_inspection(ctx.inspection)
        if green is not None:
            tdd_evidence.green = green

        verification_outcome = ctx.inspection.verification_outcome if ctx.inspection else "not_run"
        short_circuited = tdd_evidence.violation is not None

        # Suspicious test-only edit (TDD policy): a strict run whose EVERY edit
        # lands in test files while the task required a functional change gamed
        # its own verification (e.g. rewrote the failing test to assert the buggy
        # behavior). Flag it as a violation so it can never stay `completed`.
        functional_expected = functional_change_expected(task)
        test_only_suspicious = (
            strict_tdd
            and not short_circuited
            and functional_expected
            and is_test_only_change(list(ctx.changed_files))
        )
        if test_only_suspicious:
            tdd_evidence.violation = TDD_TEST_ONLY_EDIT
            self._emit_event(
                events,
                "tdd.violation",
                final_node,
                {"violation": TDD_TEST_ONLY_EDIT, "mode": self._tdd_mode},
            )

        # Regression evidence (TDD_STRICT_CONTRACT step 7): after a proven GREEN
        # on a clean strict mutation run, execute the broader suite once and
        # record its honest command + exit code under ``tdd.regression``.
        if (
            strict_tdd
            and mut_required
            and tdd_evidence.violation is None
            and tdd_evidence.green_proven
            and bool(ctx.changed_files)
            and test_command
        ):
            tdd_evidence.regression = capture_test_run(regression_command(test_command), self.root)

        # Gate catalog + the ONE enforcement point: a run may not stay `completed`
        # when a mandatory gate failed (RUN_STATE_CONTRACT rule 1).
        gates = evaluate_oc_flow_gates(
            workspace_valid=self.root.is_dir(),
            config_valid=self._config_valid(),
            # An empty envelope is not a usable pack (needs_context runs fail this
            # gate honestly); normal executors always produce at least one item.
            context_pack_created=(
                None if short_circuited else (ctx.envelope is not None and ctx.envelope.has_items)
            ),
            executor_available=(
                None
                if (short_circuited or not mut_required)
                else status not in ("needs_executor", "needs_provider")
            ),
            tdd_red_proven_if_strict=(
                tdd_evidence.red_proven if (strict_tdd and mut_required) else None
            ),
            tdd_functional_change_if_required=(
                None
                if (short_circuited or not strict_tdd or not functional_expected)
                or not ctx.changed_files
                else not test_only_suspicious
            ),
            mutation_performed_if_required=(
                bool(ctx.changed_files) if (mut_required and not short_circuited) else None
            ),
            verification_executed=(
                (verification_outcome != "not_run")
                if (verify_required and not short_circuited)
                else None
            ),
            verification_passed=(
                (verification_outcome == "passed") if verification_outcome != "not_run" else None
            ),
        )
        status = enforce_gates(status, gates)
        if test_only_suspicious and status not in ("completed", "passed"):
            reason = VIOLATION_REASONS[TDD_TEST_ONLY_EDIT]

        # R4: post-run confidence report — emit as a RuntimeDecision so
        # decisions.json captures the ConfidenceEngine evaluation.  Real signals
        # come from the completed run context; absent signals fall back to the
        # conservative default (ConfidenceSignals default = None → disclosed).
        try:
            from opencontext_core.runtime_intelligence.confidence import (
                ConfidenceEngine,
                ConfidenceSignals,
            )

            _inspection = ctx.inspection
            _signals = ConfidenceSignals(
                inspection_confidence=(
                    1.0
                    if (_inspection and _inspection.outcome == "passed")
                    else 0.0
                    if _inspection is not None
                    else None
                ),
            )
            _cr = ConfidenceEngine().report(
                session_id=session_id,
                run_id=run_id,
                workflow="oc-flow",
                signals=_signals,
            )
            decisions.append(
                RuntimeDecision(
                    kind="confidence_report",
                    chosen=str(round(_cr.overall, 4)),
                    reason=(
                        f"ConfidenceEngine post-run report: overall={_cr.overall:.4f}, "
                        f"action={_cr.recommended_action}"
                    ),
                    confidence=_cr.overall,
                    inputs=dict(_cr.dimensions),
                )
            )
        except Exception:
            pass  # confidence emission is advisory; never interrupts the run

        # Canonical state + exit code (RUN_STATE_CONTRACT): derived once, persisted
        # in run.json and mirrored by the CLI process exit.
        from opencontext_core.models.canonical_status import exit_code_for_run, to_canonical

        canonical_status = to_canonical(status).value
        exit_code = exit_code_for_run(
            status,
            tdd_violation=tdd_evidence.violation is not None,
            verification_failed=verification_outcome == "failed",
        )

        self._persist(
            session_id,
            run_id,
            ctx,
            events,
            decisions,
            guard,
            status,
            visited,
            graph_status=graph_status,
            completion_reason=reason,
            mutation_required=mut_required,
            selection=selection,
            gates=gates,
            tdd=tdd_evidence.to_json(),
            canonical_status=canonical_status,
            exit_code=exit_code,
            started_at=started_at,
            runner_source=runner_source,
        )

        return OCFlowRunResult(
            run_id=run_id,
            session_id=session_id,
            status=status,
            final_node=final_node,
            visited=visited,
            artifacts_dir=artifacts_dir,
            total_tokens=guard.total,
            diagnosis_attempts=len(ctx.diagnosis_attempts),
            escalated=("escalation" in visited),
            decisions=summarize_decision_log(decisions),
            graph_status=graph_status,
            completion_reason=reason,
            mutation_required=mut_required,
            verified_by=list(ctx.inspection.verified_by) if ctx.inspection else [],
            verification_outcome=verification_outcome,
            workflow_selection={
                "workflow": selection.workflow,
                "reason": selection.reason,
                "signals": selection.signals,
            },
            canonical_status=canonical_status,
            exit_code=exit_code,
            tdd=tdd_evidence.to_json(),
        )

    # -- transition + decision receipt ---------------------------------------
    def _next_node(
        self,
        node: str,
        outcome: NodeOutcome,
        ctx: OCFlowContext,
        decisions: DecisionLog,
        guard: BudgetGuard,
        events: list[dict[str, Any]],
    ) -> str | None:
        """Resolve the next node from the graph, recording a decision receipt.

        The advisory Brain may recommend; the deterministic graph governs (the
        recommendation is recorded in the decision inputs, never enforced).
        """
        target = resolve_next_node(self.definition, node, outcome)

        brain_reco: str | None = None
        if self.brain_advisory:
            recommendation = self.brain.recommend(
                run_id=None,
                runtime_context={
                    "current_node": node,
                    "proposed_node": target,
                    "task": ctx.task,
                    "outcome": outcome.value,
                },
            )
            if recommendation is not None:
                brain_reco = recommendation.chosen

        if target is None:
            return None

        persona = persona_id_for_oc_flow_node(target)
        node_budget = guard.per_node.get(node, 0)
        decision = RuntimeDecision(
            kind="next_node",
            chosen=target,
            reason=(
                f"graph routes '{node}' (outcome={outcome.value}) to '{target}'"
                + (f"; brain recommended '{brain_reco}'" if brain_reco else "")
            ),
            alternatives=[
                e.to_node
                for e in self.definition.edges
                if e.from_node == node and e.to_node != target
            ],
            confidence=0.9,
            governed_by="state_machine",  # the SM governs; Brain only advises.
            inputs={
                "triggering_outcome": outcome.value,
                "lane": ctx.lane.value,
                "persona": persona,
                "budget_tokens": node_budget,
                "brain_recommendation": brain_reco,
            },
            node_id=node,
        )
        decisions.append(decision)
        self._emit_event(
            events, "decision.recorded", node, {"chosen": target, "outcome": outcome.value}
        )
        return target

    # -- events / persistence -------------------------------------------------
    def _emit_event(
        self, events: list[dict[str, Any]], event_type: str, node: str, data: dict[str, Any]
    ) -> None:
        events.append(
            {
                "type": event_type,
                "family": _NODE_EVENT_FAMILY,
                "node": node,
                "ts": datetime.now(tz=UTC).isoformat(),
                "data": data,
            }
        )

    def _config_valid(self) -> bool:
        """True when the project config resolves cleanly (defaults count as valid)."""
        try:
            from opencontext_core.config import load_config_or_defaults
            from opencontext_core.config_resolver import resolve_config_path

            load_config_or_defaults(resolve_config_path(self.root), auto_detect=False)
            return True
        except Exception:
            return False

    def _persist(
        self,
        session_id: str,
        run_id: str,
        ctx: OCFlowContext,
        events: list[dict[str, Any]],
        decisions: DecisionLog,
        guard: BudgetGuard,
        status: str,
        visited: list[str],
        *,
        graph_status: str = "completed",
        completion_reason: str = "",
        mutation_required: bool = False,
        selection: WorkflowSelection | None = None,
        gates: list[dict[str, Any]] | None = None,
        tdd: dict[str, Any] | None = None,
        canonical_status: str = "",
        exit_code: int = 0,
        started_at: str = "",
        runner_source: str | None = None,
    ) -> None:
        run_dir = self._run_dir(session_id, run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        state = {
            "schema_version": "opencontext.oc_flow.run_state.v1",
            "run_id": run_id,
            "session_id": session_id,
            "workflow": "oc-flow",
            "task": ctx.task,
            "lane": ctx.lane.value,
            "profile": ctx.profile,
            "status": status,
            "graph_status": graph_status,
            "completion_reason": completion_reason,
            "mutation_required": mutation_required,
            "verified_by": list(ctx.inspection.verified_by) if ctx.inspection else [],
            "verification_outcome": (
                ctx.inspection.verification_outcome if ctx.inspection else "not_run"
            ),
            "workflow_selection": (
                {
                    "workflow": selection.workflow,
                    "reason": selection.reason,
                    "signals": selection.signals,
                }
                if selection is not None
                else {}
            ),
            "visited": visited,
            "changed_files": list(ctx.changed_files),
            "checkpoint_id": ctx.checkpoint_id,
            "max_attempts": ctx.max_attempts,
            "diagnosis_attempts": len(ctx.diagnosis_attempts),
            "total_tokens": guard.total,
            "budget_violations": [v.model_dump() for v in guard.violations],
        }
        _dump(run_dir / "state.json", state)
        _dump(run_dir / "events.json", {"events": events})
        _dump(run_dir / "decisions.json", {"decisions": summarize_decision_log(decisions)})

        # Harness-layout evidence bundle (RUN_STATE_CONTRACT rule 1 / AC-025):
        # run.json + gates.json + verification.json (+ mutations.diff) alongside
        # the legacy state.json so both workflows persist the same manifest shape.
        finished_at = datetime.now(tz=UTC).isoformat()
        verification_outcome = str(state["verification_outcome"])
        verified_by = list(state["verified_by"])  # type: ignore[arg-type]
        verification = {
            "executed": verification_outcome != "not_run",
            "commands": verified_by,
            "outcome": verification_outcome,
            "passed": verification_outcome == "passed",
            # Additive provenance: which source chose the verification command
            # ("configured" | "project_venv" | "runtime", null when none ran).
            "runner_source": runner_source,
        }
        manifest = {
            "schema_version": "opencontext.oc_flow.run_manifest.v1",
            "run_id": run_id,
            "session_id": session_id,
            "workflow": "oc-flow",
            "task": ctx.task,
            "status": status,
            "canonical_status": canonical_status,
            "exit_code": exit_code,
            "created_at": started_at or finished_at,
            "started_at": started_at or finished_at,
            "finished_at": finished_at,
            "completion_reason": completion_reason,
            "mutation_required": mutation_required,
            "changed_files": list(ctx.changed_files),
            "verification": verification,
            "tdd": tdd,
            "context": {
                "context_engine_enabled": ctx.context_engine_enabled,
                "kg_v2_enabled": ctx.kg_v2_enabled,
                "memory_enabled": ctx.memory_enabled,
                "compression_enabled": ctx.compression_enabled,
            },
            # MEMORY_CONTRACT rule 4: every memory hit used by the run is
            # recorded ({id, type, score, used_for}) together with the count of
            # harvested candidates and their approval gate; additive fields.
            "memory": memory_block(
                ctx.memory_hits,
                new_candidates=ctx.memory_new_candidates,
                requires_approval=bool(
                    ctx.memory_approval_required and ctx.memory_new_candidates > 0
                ),
            ),
        }
        green_evidence = (tdd or {}).get("green") or {}
        verification_report = {
            "run_id": run_id,
            "commands": verified_by,
            "outcome": verification_outcome,
            "exit_code": green_evidence.get("exit_code"),
            "runner_source": runner_source,
            "summary": (
                ctx.inspection.failure_summary
                if ctx.inspection and ctx.inspection.failure_summary
                else verification_outcome
            ),
        }
        patch_text: str | None = None
        if ctx.changed_files:
            patch_path = self._artifacts_dir(session_id, run_id) / "patch.diff"
            if patch_path.is_file():
                patch_text = patch_path.read_text(encoding="utf-8")
        write_run_bundle(
            run_dir,
            manifest=manifest,
            gates=gates or [],
            verification=verification_report,
            patch_text=patch_text,
        )

    # -- resume ---------------------------------------------------------------
    def resume(self, session_id: str, run_id: str) -> ResumedRun:
        """Restore OC Flow state from persisted artifacts, or fail safe (FLOW-15).

        Restores the task contract, context envelope, patch state, receipts,
        inspection report and diagnosis attempts. If a required artifact (the task
        contract) is missing, resume fails without executing any further node.
        """
        run_dir = self._locate_run_dir(session_id, run_id)
        artifacts_dir = run_dir / "artifacts" / "oc-flow"
        if not run_dir.is_dir():
            raise OCFlowError(f"no run to resume: {session_id}/{run_id}")

        contract_path = artifacts_dir / "task-contract.json"
        if not contract_path.is_file():
            raise OCFlowError("cannot resume: required artifact task-contract.json is missing")
        contract = TaskContract.model_validate(_load(contract_path))

        envelope = None
        env_path = artifacts_dir / "context-envelope.json"
        if env_path.is_file():
            from opencontext_core.oc_flow.models import ContextEnvelope

            envelope = ContextEnvelope.model_validate(_load(env_path))

        receipts = _load(artifacts_dir / "apply-receipts.json") or {}
        patch = ""
        patch_path = artifacts_dir / "patch.diff"
        if patch_path.is_file():
            patch = patch_path.read_text(encoding="utf-8")

        inspection = None
        insp_path = artifacts_dir / "inspection-report.json"
        if insp_path.is_file():
            inspection = InspectionReport.model_validate(_load(insp_path))

        attempts: list[DiagnosisAttempt] = []
        diag_dir = artifacts_dir / "diagnosis"
        if diag_dir.is_dir():
            for attempt_file in sorted(diag_dir.glob("attempt-*.json")):
                attempts.append(DiagnosisAttempt.model_validate(_load(attempt_file)))

        state = _load(run_dir / "state.json") or {}
        return ResumedRun(
            session_id=session_id,
            run_id=run_id,
            contract=contract,
            envelope=envelope,
            patch=patch,
            apply_receipts=receipts,
            inspection=inspection,
            diagnosis_attempts=attempts,
            state=state,
        )


@dataclass
class ResumedRun:
    """Fully restored OC Flow state (FLOW-15, book §22)."""

    session_id: str
    run_id: str
    contract: TaskContract
    envelope: Any | None
    patch: str
    apply_receipts: dict[str, Any]
    inspection: InspectionReport | None
    diagnosis_attempts: list[DiagnosisAttempt]
    state: dict[str, Any]


def _dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")


def _load(path: Path) -> Any:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
