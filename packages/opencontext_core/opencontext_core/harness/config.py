"""Harness configuration — mapping workflow phases to budgets and gates."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from opencontext_core.harness.models import PrivacyProfile


@dataclass
class PhaseConfig:
    """Configuration for a single workflow phase."""

    budget_tokens: int = 6000
    gates: list[str] = field(default_factory=list)
    # First-class per-phase harness declaration (spec PR-004 REQ-05). Names the
    # harness subsystems / gate ids this phase requires. Defaults (via
    # ``__post_init__``) to the phase's declared ``gates`` so behaviour is
    # unchanged on upgrade — one source of truth, additive.
    required_harnesses: list[str] = field(default_factory=list)
    confidence_threshold: float | None = None
    # Override for ConfidenceGate's baseline complexity (0.0=trivial, 1.0=very complex).
    # If None, ConfidenceGate uses its built-in defaults per phase.
    complexity: float | None = None
    # Surgical-first explore (per-phase override; falls back to
    # :attr:`HarnessConfig.surgical_explore` when None, then True in the phase
    # itself). :attr:`surgical_coverage_floor` is the per-required-symbol
    # coverage threshold below which the explore phase widens the pack to
    # full budget. Both are real PhaseConfig attributes (previous code used
    # ``getattr(self.config, "surgical_explore", True)`` on a PhaseConfig that
    # never declared them — yielding True/1.0 by silent default and making it
    # impossible to disable surgical-from-yaml without editing code).
    surgical_explore: bool | None = None
    surgical_coverage_floor: float | None = None

    def __post_init__(self) -> None:
        # Default the first-class harness declaration to the phase's gate ids so
        # a phase that declares gates always exposes a non-empty
        # ``required_harnesses`` (spec PR-004 REQ-05) with zero behaviour change.
        if not self.required_harnesses:
            self.required_harnesses = list(self.gates)


@dataclass
class HarnessConfig:
    """Complete harness configuration loaded from .opencontext/harness.yaml.

    Defaults are designed for zero-config usage — the harness works out of the
    box without any YAML file. All values are explicitly typed and have safe
    defaults.

    Example harness.yaml:

        workflow_defaults:
            budget_mode: "warn"          # off | warn | strict
            privacy_profile: "standard"  # off | standard | restricted

        phases:
            explore:
                budget_tokens: 6000
                gates: ["project_index_exists", "context_pack_created"]

        safety:
            forbidden_paths: [".env", "secrets/"]
            forbidden_commands: ["rm -rf", "git push --force"]

    Attributes:
        budget_mode: Token budget enforcement (default: warn)
        privacy_profile: Privacy gate enforcement (default: off — opt-in)
        artifact_root: Where run artifacts are stored
    """

    version: str = "0.1"
    budget_mode: str = "warn"
    # Gate enforcement posture. "block" (default) makes a FAILED verify-phase gate
    # — and an architecture-health regression — fatal to the run regardless of
    # budget_mode; "warn" keeps the advisory posture (a gate blocks only under
    # BudgetMode.STRICT). Set via workflow_defaults.gate_policy.
    gate_policy: str = "block"
    privacy_profile: PrivacyProfile = PrivacyProfile.OFF
    # The legacy default is resolved mode-aware (paths.execution_state.runs_root):
    # user mode places run artifacts under XDG project state, local mode keeps
    # ``<root>/.opencontext/runs``. An explicit override stays root-relative.
    artifact_root: str = ".opencontext/runs"
    # TDD / approval pre-gate governance (decoupled from budget_mode).
    # tdd_mode: "ask" | "strict" | "off". Only "strict" gates apply on tests.
    tdd_mode: str = "ask"
    strict_tdd: bool = False
    # When True, ApplyPhase requires an approved human-approval gate before edits.
    approval_required_for_writes: bool = False
    # Surgical-first explore (P2): start narrow (search/locate) and widen to a full
    # context pack only when required-symbol coverage falls below the floor. Makes
    # the cheap retrieval path the harness default instead of always packing broad.
    surgical_explore: bool = True
    surgical_coverage_floor: float = 1.0
    # Cap auto-indexing of an unknown repo so a huge tree never stalls a run.
    auto_index_max_files: int = 5000
    # Overall retrieval/context envelope for a run (the explore widen budget). Was a
    # hardcoded 6000 in create_run; now configurable via workflow_defaults.
    max_context_tokens: int = 6000
    # Explicit project test command (workflow_defaults.test_command). When set it
    # wins over interpreter/pytest discovery in verification-command resolution.
    # Accepts a shell string ("make test") or an argv list in YAML.
    test_command: list[str] | None = None
    phases: dict[str, PhaseConfig] = field(
        default_factory=lambda: {
            "explore": PhaseConfig(
                budget_tokens=6000,
                gates=[
                    "project_index_exists",
                    "context_pack_created",
                    "no_secret_leakage",
                ],
            ),
            "propose": PhaseConfig(
                budget_tokens=6000,
                gates=[
                    "trace_id_created",
                    "included_sources_present",
                    "omissions_recorded",
                ],
            ),
            "spec": PhaseConfig(
                budget_tokens=3000,
                confidence_threshold=0.4,
                complexity=0.4,
                gates=["artifact_persisted"],
            ),
            "design": PhaseConfig(
                budget_tokens=4000,
                confidence_threshold=0.5,
                complexity=0.5,
                gates=["artifact_persisted"],
            ),
            "tasks": PhaseConfig(
                budget_tokens=3000,
                confidence_threshold=0.3,
                complexity=0.3,
                gates=["artifact_persisted"],
            ),
            "apply": PhaseConfig(
                budget_tokens=12000,
                confidence_threshold=0.4,
                complexity=0.8,
                gates=[
                    "provider_policy_passed",
                    "approval_required_for_writes",
                    # Red-before-green is an apply PRE-condition, not a verify check.
                    # Declared here it surfaces as an advisory signal in "ask" mode
                    # and blocks in "strict"; on verify it never ran at all.
                    "failing_test_exists",
                ],
            ),
            "verify": PhaseConfig(
                budget_tokens=4000,
                confidence_threshold=0.3,
                complexity=0.4,
                gates=[
                    "security_scan_passed",
                    "no_high_risk_exports",
                    # Architecture/code-quality enforcement (zero-config sensor).
                    # architecture_clean diffs post-apply health vs the explore
                    # snapshot; quality_standards runs the per-language tools over
                    # the changed scope. Both dispatch via _dispatch_one_gate and
                    # only FAIL the run under BudgetMode.STRICT (WARN otherwise).
                    "architecture_clean",
                    "quality_standards",
                    # tests_covered: surfaces (advisory WARNING) any changed
                    # function/method with no referencing test — structural proxy
                    # scoped to the changed files; SKIPs without a git diff / graph.
                    "tests_covered",
                    # code_economy: surfaces (advisory WARNING) any changed symbol
                    # with no caller/importer/reference — an orphan = likely dead or
                    # speculative code. Scoped to the change; SKIPs without graph.
                    "code_economy",
                    # tests_pass: the GREEN half of strict TDD — runs the configured
                    # test command and FAILS if it does not pass. Inactive (skips)
                    # unless tdd_mode is strict, so non-TDD runs are unaffected; it
                    # completes RED (failing_test_exists pre-gate) -> GREEN here.
                    "tests_pass",
                ],
            ),
            "review": PhaseConfig(
                budget_tokens=4000,
                confidence_threshold=0.3,
                complexity=0.3,
                gates=[
                    "review_artifact_created",
                ],
            ),
            "archive": PhaseConfig(
                budget_tokens=2000,
                complexity=0.1,
                # trace/memory/graph deltas all follow the artifact_persisted pattern
                gates=["artifact_persisted"],
            ),
        }
    )
    active_clients: list[str] = field(default_factory=lambda: ["opencode"])
    default_client: str = "opencode"
    orchestrator_mode: str = "multi-phase"
    forbidden_paths: list[str] = field(
        default_factory=lambda: [
            ".env",
            "secrets/",
            "private/",
            "vendor/",
            "node_modules/",
        ]
    )
    forbidden_commands: list[str] = field(
        default_factory=lambda: [
            "rm -rf",
            "git push --force",
            "curl | bash",
        ]
    )
    # CMD-1 bug-fix: until PR-005 ``forbidden_commands`` was loaded but read by no
    # execution path. When enforced, a command matching the deny-list is refused
    # before execution. Default-on; set ``False`` to restore advisory-only behaviour.
    command_enforcement: bool = True

    @classmethod
    def from_yaml_file(cls, path: Path) -> HarnessConfig:
        """Load harness config from a YAML file, falling back to defaults."""
        import yaml

        if not path.exists():
            return cls()

        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            return cls()

        if not isinstance(data, dict):
            return cls()

        config = cls()
        config.version = data.get("version", config.version)
        wf_defaults = data.get("workflow_defaults", {})
        if isinstance(wf_defaults, dict):
            config.budget_mode = wf_defaults.get("budget_mode", config.budget_mode)
            config.gate_policy = wf_defaults.get("gate_policy", config.gate_policy)
            privacy_str = wf_defaults.get("privacy_profile", "off")
            config.privacy_profile = PrivacyProfile(privacy_str)
            config.artifact_root = wf_defaults.get("artifact_root", config.artifact_root)
            config.tdd_mode = wf_defaults.get("tdd_mode", config.tdd_mode)
            config.strict_tdd = wf_defaults.get("strict_tdd", config.strict_tdd)
            config.approval_required_for_writes = wf_defaults.get(
                "approval_required_for_writes", config.approval_required_for_writes
            )
            config.surgical_explore = wf_defaults.get("surgical_explore", config.surgical_explore)
            config.surgical_coverage_floor = wf_defaults.get(
                "surgical_coverage_floor", config.surgical_coverage_floor
            )
            config.auto_index_max_files = wf_defaults.get(
                "auto_index_max_files", config.auto_index_max_files
            )
            config.max_context_tokens = wf_defaults.get(
                "max_context_tokens", config.max_context_tokens
            )
            raw_test_command = wf_defaults.get("test_command")
            if isinstance(raw_test_command, str) and raw_test_command.strip():
                import shlex

                config.test_command = shlex.split(raw_test_command)
            elif isinstance(raw_test_command, list) and raw_test_command:
                config.test_command = [str(item) for item in raw_test_command]

        phases_data = data.get("phases", {})
        # :attr:`surgical_explore` / :attr:`surgical_coverage_floor` are
        # workflow-level defaults that flow down into the ``explore`` phase
        # when the phase section does NOT override them explicitly. This keeps
        # the zero-config surface unchanged when the user only sets
        # ``workflow_defaults.surgical_explore``. Per-phase values still win
        # when explicitly declared under ``phases.<name>``. Implemented here
        # (rather than in the dataclass defaults) so the explore phase can
        # distinguish "explicitly set to True" from "fell through the default".
        global_surgical = config.surgical_explore
        global_surgical_floor = config.surgical_coverage_floor
        if isinstance(phases_data, dict):
            for phase_name, phase_cfg in phases_data.items():
                if not isinstance(phase_cfg, dict):
                    continue
                phase_surgical = phase_cfg.get("surgical_explore", global_surgical)
                phase_surgical_floor = phase_cfg.get(
                    "surgical_coverage_floor", global_surgical_floor
                )
                config.phases[phase_name] = PhaseConfig(
                    budget_tokens=phase_cfg.get("budget_tokens", 6000),
                    gates=phase_cfg.get("gates", []),
                    required_harnesses=phase_cfg.get("required_harnesses", []),
                    confidence_threshold=phase_cfg.get("confidence_threshold"),
                    complexity=phase_cfg.get("complexity"),
                    surgical_explore=phase_surgical,
                    surgical_coverage_floor=phase_surgical_floor,
                )

        agents_data = data.get("agents", {})
        if isinstance(agents_data, dict):
            config.active_clients = agents_data.get("active_clients", config.active_clients)
            config.default_client = agents_data.get("default_client", config.default_client)
            config.orchestrator_mode = agents_data.get("mode", config.orchestrator_mode)

        safety = data.get("safety", {})
        if isinstance(safety, dict):
            config.forbidden_paths = safety.get("forbidden_paths", config.forbidden_paths)
            config.forbidden_commands = safety.get("forbidden_commands", config.forbidden_commands)
            config.command_enforcement = safety.get(
                "command_enforcement", config.command_enforcement
            )

        return config
